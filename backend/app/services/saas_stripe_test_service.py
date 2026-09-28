from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.saas_billing import SaasInvoice, SaasSubscription
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
            select(SaasInvoice).where(
                SaasInvoice.id == invoice_id,
                SaasInvoice.company_id == company_id,
            )
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
            idempotency_key=f"saas-promptpay-{invoice.id}-{invoice.total_satang}",
            description=f"Foodchainservice SaaS {invoice.invoice_number}",
        )
        return SaasStripePromptPaySessionRead(
            company_id=company_id,
            invoice_id=invoice.id,
            payment_intent_id=intent.id,
            status=intent.status,
            amount_satang=intent.amount_satang,
            qr_payload=intent.qr_payload,
            redirect_url=intent.hosted_instructions_url,
            expires_at=intent.expires_at,
        )

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
        internal_type = {
            "payment_intent.succeeded": "invoice.paid",
        }.get(event_type)
        if internal_type is None:
            return []
        obj = event.get("data", {}).get("object", {})
        metadata = obj.get("metadata") if isinstance(obj, dict) and isinstance(obj.get("metadata"), dict) else {}
        if str(metadata.get("context") or "") != "saas_billing":
            return []
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
        amount_satang = obj.get("amount_received") if internal_type == "invoice.paid" else None
        if internal_type == "invoice.paid" and amount_satang != invoice.total_satang:
            raise HTTPException(status_code=422, detail="Stripe SaaS paid amount mismatch")
        currency = str(obj.get("currency") or "").upper()
        if currency != invoice.currency:
            raise HTTPException(status_code=422, detail="Stripe SaaS currency mismatch")
        occurred_at = datetime.fromtimestamp(
            event.get("created") if isinstance(event.get("created"), int) else int(datetime.now(timezone.utc).timestamp()),
            tz=timezone.utc,
        )
        event_id = str(event.get("id") or "")
        if not event_id:
            raise HTTPException(status_code=400, detail="Stripe event ID is missing")

        billing = SaasBillingService(self.db, operator_id=None)
        invoice_event = await billing.apply_event(
            SaasBillingEventImport(
                event_key=f"stripe:{event_id}:invoice",
                event_type=internal_type,
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
        )
        result = [invoice_event]
        if internal_type == "invoice.paid":
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
            )
            result.append(activation)
        return result
