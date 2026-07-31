"""add Restaurant reference projection ledger

Revision ID: p1restaurant0003
Revises: p1restaurant0002
Create Date: 2026-08-01 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p1restaurant0003"
down_revision: Union[str, None] = "p1restaurant0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_projection_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_type", sa.String(length=40), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("source_occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "aggregate_type IN ('company', 'brand', 'branch', 'brand_branch', 'user')",
            name="ck_platform_projection_events_supported_aggregate",
        ),
        sa.CheckConstraint(
            "schema_version = 1",
            name="ck_platform_projection_events_schema_version",
        ),
    )
    op.create_index(
        "ix_platform_projection_events_aggregate",
        "platform_projection_events",
        ["aggregate_type", "aggregate_id", "applied_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_projection_events_aggregate",
        table_name="platform_projection_events",
    )
    op.drop_table("platform_projection_events")

