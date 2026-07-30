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
from app.models.payment_gateway import NotificationLog, PaymentGatewayConfig, PaymentSession
from app.models.pos import Payment, SaleOrder
from app.schemas.payment_gateway import CreateOmiseRequest, CreatePromptPayRequest
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
    ) -> PaymentSession:
        config = await self.get_config(company_id)
        if not config.promptpay_target:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PromptPay target is not configured")

        qr_payload = generate_promptpay_payload(config.promptpay_target, q2(amount))
        session_ref = f"PS{int(time.time())}{secrets.token_urlsafe(4)}"
        session = await self._create_session(
            company_id=company_id,
            branch_id=branch_id,
            gateway="promptpay",
            method="qr",
            amount=q2(amount),
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
        elif session.gateway == "promptpay" and session.created_at <= now - timedelta(seconds=15):
            session.status = "completed"
            session.gateway_status = "mock_received"
            session.completed_at = now
            await self._mark_reference_paid(session)

        await self.db.commit()
        return await self.get_session(session_id, company_id)

    async def confirm_payment(
        self,
        session_id: uuid.UUID,
        company_id: uuid.UUID,
        gateway_ref: str | None = None,
    ) -> PaymentSession:
        session = await self.get_session(session_id, company_id)
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
