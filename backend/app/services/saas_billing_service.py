from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.audit import AuditLog
from app.models.company import Company
from app.models.platform import PlatformTenantProfile
from app.models.saas_billing import SaasBillingEvent, SaasInvoice, SaasPlan, SaasSubscription
from app.schemas.saas_billing import (
    SaasBillingEventImport,
    SaasBillingEventRead,
    SaasBillingOverviewRead,
    SaasBillingSummaryRead,
    SaasInvoiceCreate,
    SaasInvoiceRead,
    SaasPlanRead,
    SaasPlanUpsert,
    SaasSubscriptionRead,
    SaasSubscriptionUpdate,
)


async def ensure_starter_subscription(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    subscription_status: str = "incomplete",
    trial_started_at: datetime | None = None,
    trial_ends_at: datetime | None = None,
) -> SaasSubscription:
    existing = await db.scalar(
        select(SaasSubscription).where(SaasSubscription.company_id == company_id)
    )
    if existing is not None:
        return existing
    plan = await db.scalar(select(SaasPlan).where(SaasPlan.code == "starter"))
    if plan is None:
        raise RuntimeError("Starter SaaS plan is missing")
    row = SaasSubscription(
        company_id=company_id,
        plan_id=plan.id,
        status=subscription_status,
        trial_started_at=trial_started_at,
        trial_ends_at=trial_ends_at,
        current_period_start=trial_started_at,
        current_period_end=trial_ends_at,
    )
    db.add(row)
    await db.flush()
    return row


def _event_digest(data: SaasBillingEventImport) -> str:
    canonical = json.dumps(
        data.model_dump(mode="json", exclude={"reason"}),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SaasBillingService:
    def __init__(self, db: AsyncSession, *, operator_id: uuid.UUID | None):
        self.db = db
        self.operator_id = operator_id

    async def list_plans(self) -> list[SaasPlanRead]:
        rows = list(await self.db.scalars(select(SaasPlan).order_by(SaasPlan.code)))
        return [SaasPlanRead.model_validate(row) for row in rows]

    async def overview(self) -> SaasBillingOverviewRead:
        plans = await self.list_plans()
        subscription_rows = (
            await self.db.execute(
                select(SaasSubscription.status, func.count(SaasSubscription.id)).group_by(
                    SaasSubscription.status
                )
            )
        ).all()
        invoice_rows = (
            await self.db.execute(
                select(SaasInvoice.status, func.count(SaasInvoice.id)).group_by(
                    SaasInvoice.status
                )
            )
        ).all()
        return SaasBillingOverviewRead(
            provider=settings.saas_billing_provider,
            live_charging_enabled=settings.saas_billing_live_charging_enabled,
            collection_available=(
                settings.saas_billing_provider != "unconfigured"
                and settings.saas_billing_live_charging_enabled
            ),
            plans=plans,
            subscription_counts={key: count for key, count in subscription_rows},
            invoice_counts={key: count for key, count in invoice_rows},
        )

    async def upsert_plan(
        self,
        data: SaasPlanUpsert,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SaasPlanRead:
        row = await self.db.scalar(select(SaasPlan).where(SaasPlan.code == data.code))
        old_value = None
        values = data.model_dump(exclude={"reason"})
        if row is None:
            row = SaasPlan(**values, created_by=self.operator_id)
            self.db.add(row)
            action = "platform.billing.plan.create"
        else:
            old_value = {
                "unit_amount_satang": row.unit_amount_satang,
                "is_public": row.is_public,
                "is_active": row.is_active,
            }
            for key, value in values.items():
                setattr(row, key, value)
            action = "platform.billing.plan.update"
        await self.db.flush()
        self._audit(
            action=action,
            company_id=None,
            resource="SaasPlan",
            resource_id=row.id,
            reason=data.reason,
            old_value=old_value,
            new_value={
                "code": row.code,
                "currency": row.currency,
                "billing_interval": row.billing_interval,
                "unit_amount_satang": row.unit_amount_satang,
                "is_public": row.is_public,
                "is_active": row.is_active,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        await self.db.refresh(row)
        return SaasPlanRead.model_validate(row)

    async def summary(self, company_id: uuid.UUID) -> SaasBillingSummaryRead:
        if await self.db.get(Company, company_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        subscription = await self.db.scalar(
            select(SaasSubscription).where(SaasSubscription.company_id == company_id)
        )
        plan = await self.db.get(SaasPlan, subscription.plan_id) if subscription else None
        invoices = list(
            await self.db.scalars(
                select(SaasInvoice)
                .where(SaasInvoice.company_id == company_id)
                .order_by(SaasInvoice.created_at.desc())
                .limit(100)
            )
        )
        return SaasBillingSummaryRead(
            company_id=company_id,
            provider=settings.saas_billing_provider,
            live_charging_enabled=settings.saas_billing_live_charging_enabled,
            collection_available=(
                settings.saas_billing_provider != "unconfigured"
                and settings.saas_billing_live_charging_enabled
            ),
            plan=SaasPlanRead.model_validate(plan) if plan else None,
            subscription=(
                SaasSubscriptionRead.model_validate(subscription) if subscription else None
            ),
            invoices=[SaasInvoiceRead.model_validate(invoice) for invoice in invoices],
        )

    async def update_subscription(
        self,
        company_id: uuid.UUID,
        data: SaasSubscriptionUpdate,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SaasBillingSummaryRead:
        company = await self.db.get(Company, company_id)
        plan = await self.db.scalar(
            select(SaasPlan).where(SaasPlan.code == data.plan_code, SaasPlan.is_active.is_(True))
        )
        if company is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active SaaS plan not found")
        subscription = await self.db.scalar(
            select(SaasSubscription)
            .where(SaasSubscription.company_id == company_id)
            .with_for_update()
        )
        old_value = None
        if subscription is None:
            subscription = SaasSubscription(company_id=company_id, plan_id=plan.id)
            self.db.add(subscription)
        else:
            old_value = {
                "plan_id": str(subscription.plan_id),
                "status": subscription.status,
                "cancel_at_period_end": subscription.cancel_at_period_end,
            }
        subscription.plan_id = plan.id
        subscription.status = data.status
        subscription.current_period_start = data.current_period_start
        subscription.current_period_end = data.current_period_end
        subscription.cancel_at_period_end = data.cancel_at_period_end
        subscription.cancelled_at = (
            datetime.now(timezone.utc) if data.status == "cancelled" else None
        )
        subscription.updated_by = self.operator_id
        profile = await self.db.scalar(
            select(PlatformTenantProfile).where(PlatformTenantProfile.company_id == company_id)
        )
        if profile is None:
            profile = PlatformTenantProfile(
                company_id=company_id,
                plan_code=plan.code,
                feature_flags=dict(plan.feature_flags),
                plan_limits=dict(plan.plan_limits),
                created_by=self.operator_id,
            )
            self.db.add(profile)
        else:
            profile.plan_code = plan.code
            # WP2 separates plan inclusion from the Company's explicit module
            # switches. A plan change must preserve manual module decisions.
            profile.plan_limits = dict(plan.plan_limits)
        await self.db.flush()
        self._audit(
            action="platform.billing.subscription.update",
            company_id=company_id,
            resource="SaasSubscription",
            resource_id=subscription.id,
            reason=data.reason,
            old_value=old_value,
            new_value={
                "plan_code": plan.code,
                "status": subscription.status,
                "cancel_at_period_end": subscription.cancel_at_period_end,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        return await self.summary(company_id)

    async def create_invoice(
        self,
        company_id: uuid.UUID,
        data: SaasInvoiceCreate,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SaasInvoiceRead:
        subscription = await self.db.scalar(
            select(SaasSubscription).where(SaasSubscription.company_id == company_id)
        )
        if subscription is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Subscription is required")
        invoice_number = data.invoice_number or (
            f"SINV-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:10].upper()}"
        )
        row = SaasInvoice(
            subscription_id=subscription.id,
            company_id=company_id,
            invoice_number=invoice_number,
            status=data.status,
            currency=data.currency,
            subtotal_satang=data.subtotal_satang,
            tax_satang=data.tax_satang,
            total_satang=data.subtotal_satang + data.tax_satang,
            paid_satang=0,
            period_start=data.period_start,
            period_end=data.period_end,
            due_at=data.due_at,
            memo=data.memo,
            created_by=self.operator_id,
        )
        self.db.add(row)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invoice number already exists") from exc
        self._audit(
            action="platform.billing.invoice.create",
            company_id=company_id,
            resource="SaasInvoice",
            resource_id=row.id,
            reason=data.reason,
            old_value=None,
            new_value={
                "invoice_number": row.invoice_number,
                "status": row.status,
                "currency": row.currency,
                "total_satang": row.total_satang,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        return SaasInvoiceRead.model_validate(row)

    async def apply_event(
        self,
        data: SaasBillingEventImport,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SaasBillingEventRead:
        digest = _event_digest(data)
        existing = await self.db.scalar(
            select(SaasBillingEvent).where(SaasBillingEvent.event_key == data.event_key)
        )
        if existing is not None:
            if existing.payload_sha256 != digest:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Billing event key was already used with different normalized data",
                )
            return SaasBillingEventRead.model_validate(existing)
        subscription = await self.db.scalar(
            select(SaasSubscription)
            .where(SaasSubscription.company_id == data.company_id)
            .with_for_update()
        )
        if subscription is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
        invoice = None
        if data.invoice_id is not None:
            invoice = await self.db.scalar(
                select(SaasInvoice)
                .where(
                    SaasInvoice.id == data.invoice_id,
                    SaasInvoice.company_id == data.company_id,
                )
                .with_for_update()
            )
        if data.event_type.startswith("invoice.") and invoice is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
        applied = self._apply_transition(data, subscription, invoice)
        now = datetime.now(timezone.utc)
        row = SaasBillingEvent(
            event_key=data.event_key,
            event_type=data.event_type,
            source=data.source,
            company_id=data.company_id,
            subscription_id=subscription.id,
            invoice_id=invoice.id if invoice else None,
            amount_satang=data.amount_satang,
            currency=data.currency,
            occurred_at=data.occurred_at,
            processed_at=now,
            result_status="applied" if applied else "ignored",
            payload_sha256=digest,
        )
        self.db.add(row)
        await self.db.flush()
        self._audit(
            action="platform.billing.event.apply",
            company_id=data.company_id,
            resource="SaasBillingEvent",
            resource_id=row.id,
            reason=data.reason,
            old_value=None,
            new_value={
                "event_key": row.event_key,
                "event_type": row.event_type,
                "source": row.source,
                "result_status": row.result_status,
                "payload_sha256": digest,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        return SaasBillingEventRead.model_validate(row)

    @staticmethod
    def _apply_transition(
        data: SaasBillingEventImport,
        subscription: SaasSubscription,
        invoice: SaasInvoice | None,
    ) -> bool:
        if invoice is not None:
            target = {
                "invoice.opened": "open",
                "invoice.failed": "uncollectible",
                "invoice.voided": "void",
                "invoice.paid": "paid",
            }.get(data.event_type)
            if target is not None:
                allowed_from = {
                    "invoice.opened": {"draft", "open"},
                    "invoice.paid": {"open", "paid"},
                    "invoice.failed": {"open", "uncollectible"},
                    "invoice.voided": {"draft", "open", "void"},
                }[data.event_type]
                if invoice.status not in allowed_from:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Invalid invoice transition from {invoice.status}",
                    )
                if data.currency is not None and data.currency != invoice.currency:
                    raise HTTPException(status_code=422, detail="Invoice event currency mismatch")
                if data.event_type == "invoice.paid":
                    amount = data.amount_satang if data.amount_satang is not None else invoice.total_satang
                    if amount != invoice.total_satang:
                        raise HTTPException(status_code=422, detail="Paid event amount must equal invoice total")
                    invoice.paid_satang = amount
                    invoice.paid_at = data.occurred_at
                if invoice.status == target:
                    return False
                invoice.status = target
                return True
        target_status = {
            "subscription.activated": "active",
            "subscription.past_due": "past_due",
            "subscription.paused": "paused",
            "subscription.cancelled": "cancelled",
        }.get(data.event_type)
        if target_status is None or subscription.status == target_status:
            return False
        allowed_from = {
            "subscription.activated": {"incomplete", "trialing", "active", "past_due", "paused"},
            "subscription.past_due": {"active", "past_due"},
            "subscription.paused": {"trialing", "active", "past_due", "paused"},
            "subscription.cancelled": {"incomplete", "trialing", "active", "past_due", "paused", "cancelled"},
        }[data.event_type]
        if subscription.status not in allowed_from:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Invalid subscription transition from {subscription.status}",
            )
        subscription.status = target_status
        if target_status == "cancelled":
            subscription.cancelled_at = data.occurred_at
        return True

    def _audit(
        self,
        *,
        action: str,
        company_id: uuid.UUID | None,
        resource: str,
        resource_id: uuid.UUID,
        reason: str,
        old_value: dict | None,
        new_value: dict,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        self.db.add(
            AuditLog(
                company_id=company_id,
                user_id=self.operator_id,
                action=action,
                resource=resource,
                resource_id=str(resource_id),
                old_value=old_value,
                new_value={**new_value, "reason": reason},
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
