"""add replenishment policies

Revision ID: f96a2b3c4d51
Revises: e85f1a2b3c40
Create Date: 2026-07-22 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f96a2b3c4d51"
down_revision: Union[str, None] = "e85f1a2b3c40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "branch_replenishment_policies",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("brand_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("safety_stock_percent", sa.Numeric(7, 4), server_default=sa.text("10"), nullable=False),
        sa.Column("safety_stock_qty", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("pack_size", sa.Numeric(15, 4), server_default=sa.text("1"), nullable=False),
        sa.Column("lead_time_days", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("forecast_method", sa.String(length=30), server_default=sa.text("'auto'"), nullable=False),
        sa.Column("minimum_order_qty", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("lead_time_days >= 1", name="ck_replenishment_lead_time_positive"),
        sa.CheckConstraint("minimum_order_qty >= 0", name="ck_replenishment_minimum_order_nonnegative"),
        sa.CheckConstraint("pack_size > 0", name="ck_replenishment_pack_size_positive"),
        sa.CheckConstraint("safety_stock_percent >= 0", name="ck_replenishment_safety_percent_nonnegative"),
        sa.CheckConstraint("safety_stock_qty >= 0", name="ck_replenishment_safety_qty_nonnegative"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "brand_id",
            "branch_id",
            "product_id",
            name="uq_branch_replenishment_policy_product",
        ),
    )
    op.create_index(
        "ix_branch_replenishment_policies_company_id",
        "branch_replenishment_policies",
        ["company_id"],
    )
    op.create_index(
        "ix_branch_replenishment_policies_brand_id",
        "branch_replenishment_policies",
        ["brand_id"],
    )
    op.create_index(
        "ix_branch_replenishment_policies_branch_id",
        "branch_replenishment_policies",
        ["branch_id"],
    )
    op.create_index(
        "ix_branch_replenishment_policies_product_id",
        "branch_replenishment_policies",
        ["product_id"],
    )
    op.create_index(
        "ix_branch_replenishment_policies_company_brand_branch",
        "branch_replenishment_policies",
        ["company_id", "brand_id", "branch_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_branch_replenishment_policies_company_brand_branch",
        table_name="branch_replenishment_policies",
    )
    op.drop_index("ix_branch_replenishment_policies_product_id", table_name="branch_replenishment_policies")
    op.drop_index("ix_branch_replenishment_policies_branch_id", table_name="branch_replenishment_policies")
    op.drop_index("ix_branch_replenishment_policies_brand_id", table_name="branch_replenishment_policies")
    op.drop_index("ix_branch_replenishment_policies_company_id", table_name="branch_replenishment_policies")
    op.drop_table("branch_replenishment_policies")
