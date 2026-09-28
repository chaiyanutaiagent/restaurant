"""add Stripe payment attempt account snapshots and durable event receipts

Revision ID: wp84stripe0027
Revises: wp65govern0026
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "wp84stripe0027"
down_revision: Union[str, None] = "wp65govern0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payment_sessions", sa.Column("provider_account_id", sa.String(length=100), nullable=True))
    op.add_column("payment_sessions", sa.Column("provider_mode", sa.String(length=20), nullable=True))
    op.create_table(
        "payment_provider_events",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_account_id", sa.String(length=100), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("result_status", sa.String(length=20), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["payment_session_id"], ["payment_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_account_id",
            "event_id",
            name="uq_payment_provider_events_account_event",
        ),
    )
    op.create_index(
        "ix_payment_provider_events_company_id",
        "payment_provider_events",
        ["company_id"],
    )
    op.create_index(
        "ix_payment_provider_events_session_created",
        "payment_provider_events",
        ["payment_session_id", "created_at"],
    )
    op.create_table(
        "saas_collection_attempts",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_no", sa.BigInteger(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_mode", sa.String(length=20), nullable=False),
        sa.Column("provider_account_id", sa.String(length=100), nullable=False),
        sa.Column("provider_payment_intent_id", sa.String(length=255), nullable=False),
        sa.Column("amount_satang", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("qr_payload", sa.Text(), nullable=True),
        sa.Column("redirect_url", sa.String(length=500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("attempt_no > 0", name="ck_saas_collection_attempts_attempt_no_positive"),
        sa.CheckConstraint("amount_satang > 0", name="ck_saas_collection_attempts_amount_positive"),
        sa.CheckConstraint("char_length(currency) = 3", name="ck_saas_collection_attempts_currency_length"),
        sa.CheckConstraint(
            "status IN ('requires_action', 'processing', 'paid', 'failed', 'cancelled', 'expired')",
            name="ck_saas_collection_attempts_status_valid",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_id"], ["saas_invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["saas_subscriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_saas_collection_attempts_idempotency_key"),
        sa.UniqueConstraint(
            "invoice_id",
            "attempt_no",
            name="uq_saas_collection_attempts_invoice_attempt",
        ),
        sa.UniqueConstraint(
            "provider_account_id",
            "provider_payment_intent_id",
            name="uq_saas_collection_attempts_account_intent",
        ),
    )
    op.create_index(
        "ix_saas_collection_attempts_company_id",
        "saas_collection_attempts",
        ["company_id"],
    )
    op.create_index(
        "ix_saas_collection_attempts_invoice_status",
        "saas_collection_attempts",
        ["invoice_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_saas_collection_attempts_invoice_status", table_name="saas_collection_attempts")
    op.drop_index("ix_saas_collection_attempts_company_id", table_name="saas_collection_attempts")
    op.drop_table("saas_collection_attempts")
    op.drop_index("ix_payment_provider_events_session_created", table_name="payment_provider_events")
    op.drop_index("ix_payment_provider_events_company_id", table_name="payment_provider_events")
    op.drop_table("payment_provider_events")
    op.drop_column("payment_sessions", "provider_mode")
    op.drop_column("payment_sessions", "provider_account_id")
