from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.saas_billing import SaasCollectionAttempt, SaasInvoice, SaasSubscription
from app.schemas.saas_billing import (
    SaasBillingEventImport,
    SaasBillingEventRead,
    SaasStripePromptPaySessionRead,
)
from app.services.saas_billing_service import SaasBillingService
from app.services.stripe_test_gateway import StripeTestClient


class SaasStripeTestService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _require_enabled() -> None:
        if (
            settings.saas_stripe_mode != "test"
            or settings.saas_billing_provider != "stripe_test"
            or settings.saas_billing_live_charging_enabled
            or not settings.saas_stripe_account_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="SaaS Stripe Test Mode collection is not enabled",
            )

    async def create_invoice_promptpay_session(
        self,
        *,
        company_id: uuid.UUID,
        invoice_id: uuid.UUID,
    ) -> SaasStripePromptPaySessionRead:
        self._require_enabled()
        invoice = await self.db.scalar(
            select(SaasInvoice)
            .where(
                SaasInvoice.id == invoice_id,
                SaasInvoice.company_id == company_id,
            )
            .with_for_update()
        )
        if invoice is None:
            raise HTTPException(status_code=404, detail="SaaS invoice not found")
        if invoice.status != "open":
            raise HTTPException(status_code=409, detail="Only an open SaaS invoice can be collected")
        if invoice.currency != "THB" or invoice.total_satang <= 0:
            raise HTTPException(status_code=422, detail="Stripe PromptPay requires a positive THB invoice")
        subscription = await self.db.scalar(
            select(SaasSubscription).where(
                SaasSubscription.id == invoice.subscription_id,
                SaasSubscription.company_id == company_id,
            )
        )
        if subscription is None:
            raise HTTPException(status_code=409, detail="SaaS invoice subscription is invalid")

        now = datetime.now(timezone.utc)
        active_attempt = await self.db.scalar(
            select(SaasCollectionAttempt)
            .where(
                SaasCollectionAttempt.invoice_id == invoice.id,
                SaasCollectionAttempt.provider_account_id == settings.saas_stripe_account_id,
                SaasCollectionAttempt.status.in_(("requires_action", "processing")),
            )
            .order_by(SaasCollectionAttempt.attempt_no.desc())
            .with_for_update()
        )
        if active_attempt is not None:
            if active_attempt.expires_at is None or active_attempt.expires_at > now:
                return self._read_attempt(active_attempt)
            active_attempt.status = "expired"
        attempt_no = int(
            (
                await self.db.scalar(
                    select(func.max(SaasCollectionAttempt.attempt_no)).where(
                        SaasCollectionAttempt.invoice_id == invoice.id
                    )
                )
            )
            or 0
        ) + 1
        idempotency_key = f"saas-promptpay-{invoice.id}-{attempt_no}-{invoice.total_satang}"

        client = StripeTestClient(
            secret_key=settings.saas_stripe_secret_key or "",
            api_base_url=settings.saas_stripe_api_base_url,
        )
        intent = await client.create_promptpay_intent(
            amount_satang=invoice.total_satang,
            metadata={
                "context": "saas_billing",
                "company_id": str(company_id),
                "internal_invoice_id": str(invoice.id),
                "internal_subscription_id": str(subscription.id),
                "invoice_number": invoice.invoice_number,
            },
            idempotency_key=idempotency_key,
            description=f"Foodchainservice SaaS {invoice.invoice_number}",
        )
        if intent.status not in {"requires_action", "processing"}:
            raise HTTPException(status_code=502, detail="Stripe PromptPay returned an unexpected initial status")
        attempt = SaasCollectionAttempt(
            company_id=company_id,
            subscription_id=subscription.id,
            invoice_id=invoice.id,
            attempt_no=attempt_no,
            idempotency_key=idempotency_key,
            provider="stripe",
            provider_mode="test",
            provider_account_id=settings.saas_stripe_account_id,
            provider_payment_intent_id=intent.id,
            amount_satang=intent.amount_satang,
            currency=intent.currency,
            status=intent.status,
            qr_payload=intent.qr_payload,
            redirect_url=intent.hosted_instructions_url,
            expires_at=intent.expires_at or now + timedelta(minutes=15),
        )
        self.db.add(attempt)
        await self.db.commit()
        await self.db.refresh(attempt)
        return self._read_attempt(attempt)

    async def apply_webhook_event(
        self,
        event: dict,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> list[SaasBillingEventRead]:
        self._require_enabled()
        if event.get("livemode") is not False:
            raise HTTPException(status_code=422, detail="Stripe SaaS event is not from Test Mode")
        event_type = str(event.get("type") or "")
        if event_type not in {
            "payment_intent.processing",
            "payment_intent.succeeded",
            "payment_intent.payment_failed",
            "payment_intent.canceled",
        }:
            return []
        obj = event.get("data", {}).get("object", {})
        if not isinstance(obj, dict):
            raise HTTPException(status_code=400, detail="Stripe SaaS PaymentIntent is invalid")
        intent_id = str(obj.get("id") or "")
        if not intent_id:
            raise HTTPException(status_code=400, detail="Stripe SaaS PaymentIntent ID is missing")
        attempt = await self.db.scalar(
            select(SaasCollectionAttempt)
            .where(
                SaasCollectionAttempt.provider_account_id == settings.saas_stripe_account_id,
                SaasCollectionAttempt.provider_payment_intent_id == intent_id,
            )
            .with_for_update()
        )
        if attempt is None:
            raise HTTPException(status_code=404, detail="Stripe SaaS collection attempt was not found")
        if attempt.provider_mode != "test":
            raise HTTPException(status_code=422, detail="Stripe SaaS provider snapshot is invalid")
        event_account = str(event.get("account") or "")
        if event_account and event_account != attempt.provider_account_id:
            raise HTTPException(status_code=422, detail="Stripe SaaS account mismatch")
        metadata = obj.get("metadata") if isinstance(obj, dict) and isinstance(obj.get("metadata"), dict) else {}
        expected_metadata = {
            "context": "saas_billing",
            "company_id": str(attempt.company_id),
            "internal_invoice_id": str(attempt.invoice_id),
            "internal_subscription_id": str(attempt.subscription_id),
        }
        if any(str(metadata.get(key) or "") != value for key, value in expected_metadata.items()):
            raise HTTPException(status_code=422, detail="Stripe SaaS metadata mismatch")
        try:
            company_id = uuid.UUID(str(metadata.get("company_id") or ""))
            invoice_id = uuid.UUID(str(metadata.get("internal_invoice_id") or ""))
            subscription_id = uuid.UUID(str(metadata.get("internal_subscription_id") or ""))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Stripe SaaS metadata is invalid") from exc

        invoice = await self.db.scalar(
            select(SaasInvoice).where(
                SaasInvoice.id == invoice_id,
                SaasInvoice.company_id == company_id,
                SaasInvoice.subscription_id == subscription_id,
            )
        )
        if invoice is None:
            raise HTTPException(status_code=404, detail="Stripe SaaS invoice mapping was not found")
        if obj.get("amount") != attempt.amount_satang or attempt.amount_satang != invoice.total_satang:
            raise HTTPException(status_code=422, detail="Stripe SaaS amount mismatch")
        amount_satang = obj.get("amount_received") if event_type == "payment_intent.succeeded" else None
        if event_type == "payment_intent.succeeded" and amount_satang != invoice.total_satang:
            raise HTTPException(status_code=422, detail="Stripe SaaS paid amount mismatch")
        currency = str(obj.get("currency") or "").upper()
        if currency != invoice.currency or currency != attempt.currency:
            raise HTTPException(status_code=422, detail="Stripe SaaS currency mismatch")
        occurred_at = datetime.fromtimestamp(
            event.get("created") if isinstance(event.get("created"), int) else int(datetime.now(timezone.utc).timestamp()),
            tz=timezone.utc,
        )
        event_id = str(event.get("id") or "")
        if not event_id:
            raise HTTPException(status_code=400, detail="Stripe event ID is missing")

        if event_type != "payment_intent.succeeded":
            attempt.status = {
                "payment_intent.processing": "processing",
                "payment_intent.payment_failed": "failed",
                "payment_intent.canceled": "cancelled",
            }[event_type]
            if attempt.status in {"failed", "cancelled"}:
                attempt.completed_at = occurred_at
            await self.db.commit()
            return []

        billing = SaasBillingService(self.db, operator_id=None)
        invoice_event = await billing.apply_event(
            SaasBillingEventImport(
                event_key=f"stripe:{event_id}:invoice",
                event_type="invoice.paid",
                source="stripe.test",
                company_id=company_id,
                invoice_id=invoice_id,
                amount_satang=amount_satang,
                currency=currency,
                occurred_at=occurred_at,
                reason="Verified Stripe Test Mode webhook",
            ),
            ip_address=ip_address,
            user_agent=user_agent,
            commit=False,
        )
        result = [invoice_event]
        activation = await billing.apply_event(
            SaasBillingEventImport(
                event_key=f"stripe:{event_id}:subscription",
                event_type="subscription.activated",
                source="stripe.test",
                company_id=company_id,
                occurred_at=occurred_at,
                reason="Verified Stripe Test Mode invoice payment",
            ),
            ip_address=ip_address,
            user_agent=user_agent,
            commit=False,
        )
        result.append(activation)
        attempt.status = "paid"
        attempt.completed_at = occurred_at
        await self.db.commit()
        return result

    @staticmethod
    def _read_attempt(attempt: SaasCollectionAttempt) -> SaasStripePromptPaySessionRead:
        return SaasStripePromptPaySessionRead(
            collection_attempt_id=attempt.id,
            attempt_no=int(attempt.attempt_no),
            company_id=attempt.company_id,
            invoice_id=attempt.invoice_id,
            payment_intent_id=attempt.provider_payment_intent_id,
            status=attempt.status,
            amount_satang=int(attempt.amount_satang),
            currency=attempt.currency,
            qr_payload=attempt.qr_payload,
            redirect_url=attempt.redirect_url,
            expires_at=attempt.expires_at,
        )
