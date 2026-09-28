from __future__ import annotations

from base64 import urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import secrets
import time
import uuid

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.branch import Branch
from app.models.payment_gateway import NotificationLog, PaymentGatewayConfig, PaymentSession
from app.models.pos import Payment, SaleOrder
from app.schemas.payment_gateway import CreateOmiseRequest, CreatePromptPayRequest
from app.services.stripe_test_gateway import StripeTestClient, baht_to_satang
from app.utils.promptpay import generate_promptpay_payload

TWOPLACES = Decimal("0.01")
SENSITIVE_FIELDS = {
    "omise_secret_key",
    "twoc2p_secret_key",
    "scb_api_key",
    "scb_api_secret",
    "line_notify_token",
    "smtp_password",
}


def q2(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


class PaymentGatewayService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_config(self, company_id: uuid.UUID) -> PaymentGatewayConfig:
        config = await self.db.scalar(
            select(PaymentGatewayConfig).where(PaymentGatewayConfig.company_id == company_id)
        )
        if config is None:
            config = PaymentGatewayConfig(company_id=company_id)
            self.db.add(config)
            await self.db.commit()
            await self.db.refresh(config)
        return config

    async def get_config_decrypted(self, company_id: uuid.UUID) -> PaymentGatewayConfig:
        config = await self.get_config(company_id)
        self.db.expunge(config)
        self._decrypt_config_fields(config)
        return config

    async def update_config(self, company_id: uuid.UUID, data: dict) -> PaymentGatewayConfig:
        config = await self.get_config(company_id)
        updates = {key: value for key, value in data.items() if value is not None}
        for field, value in updates.items():
            if field in SENSITIVE_FIELDS:
                setattr(config, field, self._encrypt(str(value)))
            else:
                setattr(config, field, value)
        await self.db.commit()
        await self.db.refresh(config)
        return config

    async def create_promptpay_session(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        amount: Decimal,
        reference_type: str | None = None,
        reference_id: str | None = None,
        user_id: uuid.UUID | None = None,
        idempotency_key: str | None = None,
    ) -> PaymentSession:
        normalized_amount = q2(amount)
        if normalized_amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="PromptPay amount must be greater than zero",
            )
        branch = await self.db.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.company_id == company_id,
                Branch.is_active.is_(True),
                Branch.deleted_at.is_(None),
            )
        )
        if branch is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Active branch not found for Company",
            )

        if settings.stripe_pos_mode == "test":
            if reference_type != "SaleOrder" or not reference_id or not idempotency_key:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Stripe POS requires SaleOrder reference and idempotency key",
                )
            try:
                order_id = uuid.UUID(reference_id)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="SaleOrder reference is invalid") from exc
            order = await self.db.scalar(
                select(SaleOrder)
                .where(
                    SaleOrder.id == order_id,
                    SaleOrder.company_id == company_id,
                    SaleOrder.branch_id == branch_id,
                )
                .with_for_update()
            )
            if order is None:
                raise HTTPException(status_code=404, detail="SaleOrder not found for Stripe POS context")
            if q2(order.total_amount) != normalized_amount:
                raise HTTPException(status_code=422, detail="Stripe POS amount must equal SaleOrder total")
            existing_reference = await self.db.scalar(
                select(PaymentSession).where(
                    PaymentSession.company_id == company_id,
                    PaymentSession.branch_id == branch_id,
                    PaymentSession.gateway == "stripe_promptpay",
                    PaymentSession.reference_type == reference_type,
                    PaymentSession.reference_id == reference_id,
                    PaymentSession.status.in_(("pending", "completed")),
                )
            )
            if existing_reference is not None:
                if q2(existing_reference.amount) != normalized_amount:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Stripe POS SaleOrder already has a different active amount",
                    )
                return existing_reference
            idempotency_digest = hashlib.sha256(
                f"{company_id}:{idempotency_key}".encode("utf-8")
            ).hexdigest()
            session_ref = f"PSS{idempotency_digest[:32].upper()}"
            existing = await self.db.scalar(
                select(PaymentSession).where(
                    PaymentSession.company_id == company_id,
                    PaymentSession.session_ref == session_ref,
                )
            )
            if existing is not None:
                same_request = (
                    existing.branch_id == branch_id
                    and existing.reference_type == reference_type
                    and existing.reference_id == reference_id
                    and q2(existing.amount) == normalized_amount
                )
                if not same_request:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Stripe POS idempotency key was reused with different data",
                    )
                return existing
            client = StripeTestClient(
                secret_key=settings.stripe_pos_secret_key or "",
                api_base_url=settings.stripe_pos_api_base_url,
                connected_account_id=settings.stripe_pos_connected_account_id,
            )
            intent = await client.create_promptpay_intent(
                amount_satang=baht_to_satang(normalized_amount),
                metadata={
                    "context": "pos",
                    "company_id": str(company_id),
                    "branch_id": str(branch_id),
                    "session_ref": session_ref,
                    "reference_type": reference_type or "",
                    "reference_id": reference_id or "",
                },
                idempotency_key=f"pos-promptpay-{idempotency_digest}",
                description=f"POS PromptPay {session_ref}",
            )
            return await self._create_session(
                company_id=company_id,
                branch_id=branch_id,
                gateway="stripe_promptpay",
                method="qr",
                amount=normalized_amount,
                session_ref=session_ref,
                gateway_ref=intent.id,
                gateway_status=intent.status,
                gateway_payload={"provider": "stripe", "mode": "test", "event_ids": []},
                qr_payload=intent.qr_payload,
                redirect_url=intent.hosted_instructions_url,
                reference_type=reference_type,
                reference_id=reference_id,
                user_id=user_id,
                expires_at=intent.expires_at,
            )

        session_ref = f"PS{int(time.time())}{secrets.token_urlsafe(4)}"
        config = await self.get_config(company_id)
        if not config.promptpay_target:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PromptPay target is not configured")

        qr_payload = generate_promptpay_payload(config.promptpay_target, normalized_amount)
        session = await self._create_session(
            company_id=company_id,
            branch_id=branch_id,
            gateway="promptpay",
            method="qr",
            amount=normalized_amount,
            session_ref=session_ref,
            qr_payload=qr_payload,
            reference_type=reference_type,
            reference_id=reference_id,
            user_id=user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        return session

    async def create_omise_session(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        amount: Decimal,
        method: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> PaymentSession:
        session_ref = f"PS{int(time.time())}{secrets.token_urlsafe(4)}"
        mock_gateway_ref = f"chrg_test_{secrets.token_urlsafe(16)}"
        return await self._create_session(
            company_id=company_id,
            branch_id=branch_id,
            gateway="omise",
            method=method,
            amount=q2(amount),
            session_ref=session_ref,
            gateway_ref=mock_gateway_ref,
            gateway_status="pending",
            reference_type=reference_type,
            reference_id=reference_id,
            user_id=user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )

    async def check_payment_status(self, session_id: uuid.UUID, company_id: uuid.UUID) -> PaymentSession:
        session = await self.get_session(session_id, company_id)
        now = datetime.now(timezone.utc)
        if session.status in {"completed", "failed", "cancelled", "expired"}:
            return session

        if session.expires_at and now > session.expires_at and session.status == "pending":
            session.status = "expired"
        await self.db.commit()
        return await self.get_session(session_id, company_id)

    async def handle_stripe_promptpay_event(self, event: dict) -> PaymentSession | None:
        if event.get("livemode") is not False:
            raise HTTPException(status_code=422, detail="Stripe POS event is not from Test Mode")
        expected_account = settings.stripe_pos_connected_account_id
        if expected_account and str(event.get("account") or "") != expected_account:
            raise HTTPException(status_code=422, detail="Stripe POS connected account mismatch")
        event_type = str(event.get("type") or "")
        if event_type not in {
            "payment_intent.processing",
            "payment_intent.succeeded",
            "payment_intent.payment_failed",
            "payment_intent.canceled",
        }:
            return None
        event_id = str(event.get("id") or "")
        obj = event.get("data", {}).get("object", {})
        if not event_id or not isinstance(obj, dict):
            raise HTTPException(status_code=400, detail="Stripe PaymentIntent event is invalid")
        intent_id = str(obj.get("id") or "")
        metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        session = await self.db.scalar(
            select(PaymentSession)
            .where(
                PaymentSession.gateway == "stripe_promptpay",
                PaymentSession.gateway_ref == intent_id,
            )
            .with_for_update()
        )
        if session is None:
            return None
        expected_metadata = {
            "context": "pos",
            "company_id": str(session.company_id),
            "branch_id": str(session.branch_id),
            "session_ref": session.session_ref,
        }
        if any(str(metadata.get(key) or "") != value for key, value in expected_metadata.items()):
            raise HTTPException(status_code=422, detail="Stripe POS metadata mismatch")
        expected_amount = baht_to_satang(session.amount)
        if obj.get("amount") != expected_amount:
            raise HTTPException(status_code=422, detail="Stripe POS amount mismatch")
        if event_type == "payment_intent.succeeded" and obj.get("amount_received") != expected_amount:
            raise HTTPException(status_code=422, detail="Stripe POS received amount mismatch")
        if str(obj.get("currency") or "").lower() != session.currency.lower():
            raise HTTPException(status_code=422, detail="Stripe POS currency mismatch")

        provider_data = dict(session.gateway_payload or {})
        event_ids = list(provider_data.get("event_ids") or [])
        if event_id in event_ids:
            return session
        event_ids.append(event_id)
        provider_data.update(
            {
                "provider": "stripe",
                "mode": "test",
                "last_event_type": event_type,
                "event_ids": event_ids[-20:],
            }
        )
        session.gateway_payload = provider_data
        session.gateway_status = str(obj.get("status") or event_type.rsplit(".", 1)[-1])[:50]
        now = datetime.now(timezone.utc)
        if event_type == "payment_intent.succeeded":
            session.status = "completed"
            session.completed_at = now
            await self._mark_reference_paid(session)
        elif session.status != "completed":
            if event_type == "payment_intent.payment_failed":
                session.status = "failed"
                session.failed_at = now
            elif event_type == "payment_intent.canceled":
                session.status = "cancelled"
                session.failed_at = now
            else:
                session.status = "pending"
        await self.db.commit()
        return await self.get_session(session.id, session.company_id)

    async def confirm_payment(
        self,
        session_id: uuid.UUID,
        company_id: uuid.UUID,
        gateway_ref: str | None = None,
    ) -> PaymentSession:
        session = await self.get_session(session_id, company_id)
        if session.gateway == "stripe_promptpay":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Stripe PromptPay can be confirmed only by a verified Stripe webhook",
            )
        session.status = "completed"
        session.gateway_status = "confirmed"
        session.completed_at = datetime.now(timezone.utc)
        if gateway_ref:
            session.gateway_ref = gateway_ref
        await self._mark_reference_paid(session)
        await self.db.commit()
        return await self.get_session(session_id, company_id)

    async def handle_gateway_callback(
        self,
        company_id: uuid.UUID,
        gateway: str,
        payload: dict,
    ) -> PaymentSession | None:
        gateway_ref = str(payload.get("gateway_ref") or payload.get("id") or payload.get("transaction_id") or "")
        session_ref = str(payload.get("session_ref") or payload.get("reference") or "")
        if not gateway_ref and not session_ref:
            return None

        session = await self.db.scalar(
            select(PaymentSession).where(
                PaymentSession.company_id == company_id,
                PaymentSession.gateway == gateway,
                or_(
                    PaymentSession.gateway_ref == gateway_ref,
                    PaymentSession.session_ref == session_ref,
                ),
            )
        )
        if session is None:
            return None

        gateway_status = str(payload.get("status") or "completed")
        session.gateway_status = gateway_status
        session.gateway_payload = payload
        if gateway_status.lower() in {"successful", "succeeded", "paid", "completed"}:
            session.status = "completed"
            session.completed_at = datetime.now(timezone.utc)
            await self._mark_reference_paid(session)
        elif gateway_status.lower() in {"failed", "expired", "cancelled"}:
            session.status = gateway_status.lower()
            session.failed_at = datetime.now(timezone.utc)

        await self.db.commit()
        return await self.get_session(session.id, company_id)

    async def list_sessions(
        self,
        company_id: uuid.UUID,
        status_value: str | None = None,
        gateway: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[PaymentSession], int]:
        filters = [PaymentSession.company_id == company_id]
        if status_value:
            filters.append(PaymentSession.status == status_value)
        if gateway:
            filters.append(PaymentSession.gateway == gateway)

        total = int((await self.db.scalar(select(func.count(PaymentSession.id)).where(*filters))) or 0)
        rows = (
            await self.db.scalars(
                select(PaymentSession)
                .where(*filters)
                .order_by(PaymentSession.created_at.desc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        ).all()
        return rows, total

    async def list_notification_logs(
        self,
        company_id: uuid.UUID,
        page: int = 1,
        limit: int = 50,
    ) -> tuple[list[NotificationLog], int]:
        total = int((await self.db.scalar(select(func.count(NotificationLog.id)).where(NotificationLog.company_id == company_id))) or 0)
        rows = (
            await self.db.scalars(
                select(NotificationLog)
                .where(NotificationLog.company_id == company_id)
                .order_by(NotificationLog.sent_at.desc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        ).all()
        return rows, total

    async def get_session(self, session_id: uuid.UUID, company_id: uuid.UUID) -> PaymentSession:
        session = await self.db.scalar(
            select(PaymentSession).where(
                PaymentSession.id == session_id,
                PaymentSession.company_id == company_id,
            )
        )
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment session not found")
        return session

    async def _create_session(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        gateway: str,
        method: str,
        amount: Decimal,
        session_ref: str,
        gateway_ref: str | None = None,
        gateway_status: str | None = None,
        gateway_payload: dict | None = None,
        qr_payload: str | None = None,
        redirect_url: str | None = None,
        reference_type: str | None = None,
        reference_id: str | None = None,
        user_id: uuid.UUID | None = None,
        expires_at: datetime | None = None,
    ) -> PaymentSession:
        session = PaymentSession(
            company_id=company_id,
            branch_id=branch_id,
            session_ref=session_ref,
            gateway=gateway,
            method=method,
            amount=q2(amount),
            currency="THB",
            status="pending",
            reference_type=reference_type,
            reference_id=reference_id,
            gateway_ref=gateway_ref,
            gateway_status=gateway_status,
            gateway_payload=gateway_payload,
            qr_payload=qr_payload,
            redirect_url=redirect_url,
            expires_at=expires_at,
            created_by=user_id,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def _mark_reference_paid(self, session: PaymentSession) -> None:
        if session.reference_type != "SaleOrder" or not session.reference_id:
            return
        try:
            order_id = uuid.UUID(session.reference_id)
        except ValueError:
            return
        order = await self.db.get(SaleOrder, order_id)
        if order is None:
            return
        if order.company_id != session.company_id or order.branch_id != session.branch_id:
            raise HTTPException(status_code=422, detail="Payment session SaleOrder context mismatch")
        if q2(order.total_amount) != q2(session.amount):
            raise HTTPException(status_code=422, detail="Payment session amount must equal SaleOrder total")
        order.paid_amount = q2(order.total_amount)
        existing_payment = await self.db.scalar(
            select(Payment.id).where(
                Payment.order_id == order.id,
                Payment.company_id == order.company_id,
                Payment.payment_method == session.gateway,
            )
        )
        if existing_payment is None:
            self.db.add(
                Payment(
                    order_id=order.id,
                    company_id=order.company_id,
                    payment_method=session.gateway,
                    amount=q2(session.amount),
                    reference_no=session.gateway_ref or session.session_ref,
                    currency=session.currency,
                    provider_name=session.gateway,
                    provider_payment_ref=session.gateway_ref or session.session_ref,
                    settlement_state="captured",
                )
            )

    def _fernet(self) -> Fernet:
        digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
        return Fernet(urlsafe_b64encode(digest))

    def _encrypt(self, value: str) -> str:
        return self._fernet().encrypt(value.encode("utf-8")).decode("utf-8")

    def _decrypt(self, value: str | None) -> str | None:
        if not value:
            return value
        try:
            return self._fernet().decrypt(value.encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError):
            return value

    def _decrypt_config_fields(self, config: PaymentGatewayConfig) -> None:
        for field in SENSITIVE_FIELDS:
            setattr(config, field, self._decrypt(getattr(config, field)))
