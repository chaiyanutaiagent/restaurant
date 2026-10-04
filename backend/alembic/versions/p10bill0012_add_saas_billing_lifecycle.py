"""add provider-neutral SaaS billing lifecycle

Revision ID: p10bill0012
Revises: p9ops0011
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p10bill0012"
down_revision: Union[str, None] = "p9ops0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
STARTER_PLAN_ID = "00000000-0000-4000-8000-000000000601"


def upgrade() -> None:
    op.create_table(
        "saas_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'THB'"), nullable=False),
        sa.Column("billing_interval", sa.String(length=10), server_default=sa.text("'month'"), nullable=False),
        sa.Column("unit_amount_satang", sa.BigInteger(), nullable=True),
        sa.Column("feature_flags", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("plan_limits", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("is_public", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("billing_interval IN ('month', 'year')", name="ck_saas_plans_billing_interval_valid"),
        sa.CheckConstraint("unit_amount_satang IS NULL OR unit_amount_satang >= 0", name="ck_saas_plans_unit_amount_nonnegative"),
        sa.CheckConstraint("char_length(currency) = 3", name="ck_saas_plans_currency_length"),
        sa.ForeignKeyConstraint(["created_by"], ["platform_operators.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_saas_plans_code"),
    )
    op.create_index("ix_saas_plans_public_active", "saas_plans", ["is_public", "is_active"])
    op.create_table(
        "saas_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'incomplete'"), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('incomplete', 'trialing', 'active', 'past_due', 'paused', 'cancelled')", name="ck_saas_subscriptions_status_valid"),
        sa.CheckConstraint("current_period_end IS NULL OR current_period_start IS NULL OR current_period_end > current_period_start", name="ck_saas_subscriptions_period_valid"),
        sa.CheckConstraint("trial_ends_at IS NULL OR trial_started_at IS NULL OR trial_ends_at > trial_started_at", name="ck_saas_subscriptions_trial_valid"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["saas_plans.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["platform_operators.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", name="uq_saas_subscriptions_company_id"),
    )
    op.create_index("ix_saas_subscriptions_status_period", "saas_subscriptions", ["status", "current_period_end"])
    op.create_table(
        "saas_invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_number", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'THB'"), nullable=False),
        sa.Column("subtotal_satang", sa.BigInteger(), nullable=False),
        sa.Column("tax_satang", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_satang", sa.BigInteger(), nullable=False),
        sa.Column("paid_satang", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("memo", sa.String(length=500), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'open', 'paid', 'void', 'uncollectible')", name="ck_saas_invoices_status_valid"),
        sa.CheckConstraint("subtotal_satang >= 0 AND tax_satang >= 0 AND total_satang >= 0 AND paid_satang >= 0", name="ck_saas_invoices_amounts_nonnegative"),
        sa.CheckConstraint("subtotal_satang + tax_satang = total_satang", name="ck_saas_invoices_total_arithmetic"),
        sa.CheckConstraint("paid_satang <= total_satang", name="ck_saas_invoices_paid_within_total"),
        sa.CheckConstraint("char_length(currency) = 3", name="ck_saas_invoices_currency_length"),
        sa.ForeignKeyConstraint(["subscription_id"], ["saas_subscriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["platform_operators.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_number", name="uq_saas_invoices_invoice_number"),
    )
    op.create_index("ix_saas_invoices_company_status", "saas_invoices", ["company_id", "status", "created_at"])
    op.create_table(
        "saas_billing_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_key", sa.String(length=200), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount_satang", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_status", sa.String(length=20), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("event_type IN ('invoice.opened', 'invoice.paid', 'invoice.failed', 'invoice.voided', 'subscription.activated', 'subscription.past_due', 'subscription.paused', 'subscription.cancelled')", name="ck_saas_billing_events_event_type_valid"),
        sa.CheckConstraint("amount_satang IS NULL OR amount_satang >= 0", name="ck_saas_billing_events_amount_nonnegative"),
        sa.CheckConstraint("result_status IN ('applied', 'ignored')", name="ck_saas_billing_events_result_status_valid"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["saas_subscriptions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invoice_id"], ["saas_invoices.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key", name="uq_saas_billing_events_event_key"),
    )
    op.create_index("ix_saas_billing_events_company_created", "saas_billing_events", ["company_id", "created_at"])
    op.execute(
        sa.text(
            "INSERT INTO saas_plans (id, code, name, description, currency, billing_interval, unit_amount_satang, feature_flags, plan_limits, is_public, is_active) "
            "VALUES (:id, 'starter', 'Starter', 'Price decision pending', 'THB', 'month', NULL, "
            "'{\"restaurant\": true, \"retail_pos\": false, \"takeaway\": false}'::jsonb, "
            "'{\"brands\": 1, \"branches\": 1, \"users\": 10, \"devices\": 3}'::jsonb, false, true)"
        ).bindparams(id=STARTER_PLAN_ID)
    )
    op.execute(
        sa.text(
            "INSERT INTO saas_subscriptions (id, company_id, plan_id, status, current_period_start, current_period_end, trial_started_at, trial_ends_at) "
            "SELECT gen_random_uuid(), company_id, :plan_id, "
            "CASE status WHEN 'pending_verification' THEN 'incomplete' WHEN 'trial_active' THEN 'trialing' "
            "WHEN 'active' THEN 'active' WHEN 'cancelled' THEN 'cancelled' ELSE 'paused' END, "
            "trial_started_at, trial_ends_at, trial_started_at, trial_ends_at FROM saas_tenant_memberships"
        ).bindparams(plan_id=STARTER_PLAN_ID)
    )


def downgrade() -> None:
    op.drop_index("ix_saas_billing_events_company_created", table_name="saas_billing_events")
    op.drop_table("saas_billing_events")
    op.drop_index("ix_saas_invoices_company_status", table_name="saas_invoices")
    op.drop_table("saas_invoices")
    op.drop_index("ix_saas_subscriptions_status_period", table_name="saas_subscriptions")
    op.drop_table("saas_subscriptions")
    op.drop_index("ix_saas_plans_public_active", table_name="saas_plans")
    op.drop_table("saas_plans")
