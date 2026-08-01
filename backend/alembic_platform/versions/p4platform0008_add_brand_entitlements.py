"""add phase 4 Brand module entitlements

Revision ID: p4platform0008
Revises: p3platform0007
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p4platform0008"
down_revision: Union[str, None] = "p3platform0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brand_module_entitlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_key", sa.String(length=100), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "brand_id", "module_key", name="uq_brand_module_entitlements_scope_module"),
    )
    op.create_index("ix_brand_module_entitlements_brand_id", "brand_module_entitlements", ["brand_id"])
    op.create_index("ix_brand_module_entitlements_company_enabled", "brand_module_entitlements", ["company_id", "is_enabled"])
    op.create_index("ix_brand_module_entitlements_company_id", "brand_module_entitlements", ["company_id"])
    op.create_index("ix_brand_module_entitlements_module_key", "brand_module_entitlements", ["module_key"])


def downgrade() -> None:
    op.drop_table("brand_module_entitlements")
