from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class SaasPlan(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "saas_plans"
    __table_args__ = (
        CheckConstraint("billing_interval IN ('month', 'year')", name="billing_interval_valid"),
        CheckConstraint("unit_amount_satang IS NULL OR unit_amount_satang >= 0", name="unit_amount_nonnegative"),
        CheckConstraint("char_length(currency) = 3", name="currency_length"),
        Index("ix_saas_plans_public_active", "is_public", "is_active"),
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'THB'"))
    billing_interval: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'month'"))
    unit_amount_satang: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    feature_flags: Mapped[dict[str, bool]] = mapped_column(JSON, nullable=False, server_default=text("'{}'::json"))
    plan_limits: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, server_default=text("'{}'::json"))
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("platform_operators.id", ondelete="SET NULL"), nullable=True)


class SaasSubscription(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "saas_subscriptions"
    __table_args__ = (
        CheckConstraint("status IN ('incomplete', 'trialing', 'active', 'past_due', 'paused', 'cancelled')", name="status_valid"),
        CheckConstraint("current_period_end IS NULL OR current_period_start IS NULL OR current_period_end > current_period_start", name="period_valid"),
        CheckConstraint("trial_ends_at IS NULL OR trial_started_at IS NULL OR trial_ends_at > trial_started_at", name="trial_valid"),
        Index("ix_saas_subscriptions_status_period", "status", "current_period_end"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("saas_plans.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'incomplete'"))
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("platform_operators.id", ondelete="SET NULL"), nullable=True)


class SaasInvoice(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "saas_invoices"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'open', 'paid', 'void', 'uncollectible')", name="status_valid"),
        CheckConstraint("subtotal_satang >= 0 AND tax_satang >= 0 AND total_satang >= 0 AND paid_satang >= 0", name="amounts_nonnegative"),
        CheckConstraint("subtotal_satang + tax_satang = total_satang", name="total_arithmetic"),
        CheckConstraint("paid_satang <= total_satang", name="paid_within_total"),
        CheckConstraint("char_length(currency) = 3", name="currency_length"),
        Index("ix_saas_invoices_company_status", "company_id", "status", "created_at"),
    )

    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("saas_subscriptions.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'draft'"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'THB'"))
    subtotal_satang: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_satang: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    total_satang: Mapped[int] = mapped_column(BigInteger, nullable=False)
    paid_satang: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    memo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("platform_operators.id", ondelete="SET NULL"), nullable=True)


class SaasBillingEvent(UUIDMixin, Base):
    __tablename__ = "saas_billing_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('invoice.opened', 'invoice.paid', 'invoice.failed', 'invoice.voided', 'subscription.activated', 'subscription.past_due', 'subscription.paused', 'subscription.cancelled')", name="event_type_valid"),
        CheckConstraint("amount_satang IS NULL OR amount_satang >= 0", name="amount_nonnegative"),
        CheckConstraint("result_status IN ('applied', 'ignored')", name="result_status_valid"),
        Index("ix_saas_billing_events_company_created", "company_id", "created_at"),
    )

    event_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("saas_subscriptions.id", ondelete="SET NULL"), nullable=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("saas_invoices.id", ondelete="SET NULL"), nullable=True)
    amount_satang: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result_status: Mapped[str] = mapped_column(String(20), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
