"""add Stripe POS payment sessions to the Retail boundary

Revision ID: wp84retail0008
Revises: p13retail0007
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "wp84retail0008"
down_revision: Union[str, None] = "p13retail0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_sessions",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_ref", sa.String(length=100), nullable=False),
        sa.Column("gateway", sa.String(length=20), nullable=False),
        sa.Column("method", sa.String(length=30), nullable=False),
        sa.Column("amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'THB'"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("reference_type", sa.String(length=50), nullable=True),
        sa.Column("reference_id", sa.String(length=100), nullable=True),
        sa.Column("gateway_ref", sa.String(length=255), nullable=True),
        sa.Column("gateway_status", sa.String(length=50), nullable=True),
        sa.Column("provider_account_id", sa.String(length=100), nullable=True),
        sa.Column("provider_mode", sa.String(length=20), nullable=True),
        sa.Column("gateway_payload", sa.JSON(), nullable=True),
        sa.Column("qr_payload", sa.Text(), nullable=True),
        sa.Column("redirect_url", sa.String(length=500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_ref", name="uq_payment_sessions_session_ref"),
    )
    for name, columns in (
        ("ix_payment_sessions_branch_id", ["branch_id"]),
        ("ix_payment_sessions_company_id", ["company_id"]),
        ("ix_payment_sessions_company_id_session_ref", ["company_id", "session_ref"]),
        ("ix_payment_sessions_gateway_ref", ["gateway_ref"]),
        ("ix_payment_sessions_status", ["status"]),
    ):
        op.create_index(name, "payment_sessions", columns)

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
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(
            ["payment_session_id"], ["payment_sessions.id"], ondelete="CASCADE"
        ),
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


def downgrade() -> None:
    op.drop_index(
        "ix_payment_provider_events_session_created",
        table_name="payment_provider_events",
    )
    op.drop_index(
        "ix_payment_provider_events_company_id",
        table_name="payment_provider_events",
    )
    op.drop_table("payment_provider_events")
    for name in (
        "ix_payment_sessions_status",
        "ix_payment_sessions_gateway_ref",
        "ix_payment_sessions_company_id_session_ref",
        "ix_payment_sessions_company_id",
        "ix_payment_sessions_branch_id",
    ):
        op.drop_index(name, table_name="payment_sessions")
    op.drop_table("payment_sessions")
