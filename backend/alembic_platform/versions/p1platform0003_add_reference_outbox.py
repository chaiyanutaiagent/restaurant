"""add Platform reference outbox

Revision ID: p1platform0003
Revises: p1platform0002
Create Date: 2026-08-01 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p1platform0003"
down_revision: Union[str, None] = "p1platform0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reference_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_type", sa.String(length=40), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.CheckConstraint(
            "aggregate_type IN ('company', 'brand', 'branch', 'brand_branch', 'user')",
            name="ck_reference_outbox_supported_aggregate",
        ),
        sa.CheckConstraint(
            "schema_version = 1",
            name="ck_reference_outbox_schema_version",
        ),
    )
    op.create_index(
        "ix_reference_outbox_pending",
        "reference_outbox",
        ["available_at", "occurred_at"],
        unique=False,
        postgresql_where=sa.text("processed_at IS NULL"),
    )
    op.create_index(
        "ix_reference_outbox_aggregate",
        "reference_outbox",
        ["aggregate_type", "aggregate_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_reference_outbox_aggregate", table_name="reference_outbox")
    op.drop_index("ix_reference_outbox_pending", table_name="reference_outbox")
    op.drop_table("reference_outbox")

