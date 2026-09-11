"""add Platform Tenant usage snapshots

Revision ID: p7platform0011
Revises: p6platform0010
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p7platform0011"
down_revision: Union[str, None] = "p6platform0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_tenant_usage_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("captured_on", sa.Date(), nullable=False),
        sa.Column("plan_code", sa.String(length=50), nullable=False),
        sa.Column("feature_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("plan_limits", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("usage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("limit_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("attention_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("onboarding_completed_steps", sa.Integer(), nullable=False),
        sa.Column("onboarding_total_steps", sa.Integer(), nullable=False),
        sa.Column("captured_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["captured_by"], ["platform_operators.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "captured_on",
            name="uq_platform_tenant_usage_snapshots_company_captured_on",
        ),
    )
    op.create_index(
        "ix_platform_usage_snapshots_captured_on",
        "platform_tenant_usage_snapshots",
        ["captured_on"],
    )
    op.create_index(
        "ix_platform_usage_snapshots_company_created",
        "platform_tenant_usage_snapshots",
        ["company_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_usage_snapshots_company_created",
        table_name="platform_tenant_usage_snapshots",
    )
    op.drop_index(
        "ix_platform_usage_snapshots_captured_on",
        table_name="platform_tenant_usage_snapshots",
    )
    op.drop_table("platform_tenant_usage_snapshots")
