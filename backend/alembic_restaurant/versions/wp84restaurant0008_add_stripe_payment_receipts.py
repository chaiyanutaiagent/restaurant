"""add Stripe POS payment receipts to the Restaurant boundary

Revision ID: wp84restaurant0008
Revises: p6restaurant0007
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "wp84restaurant0008"
down_revision: Union[str, None] = "p6restaurant0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payment_sessions",
        sa.Column("provider_account_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "payment_sessions",
        sa.Column("provider_mode", sa.String(length=20), nullable=True),
    )
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
    op.drop_column("payment_sessions", "provider_mode")
    op.drop_column("payment_sessions", "provider_account_id")
