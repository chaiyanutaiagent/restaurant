"""add_brands

Revision ID: ac34de56fa78
Revises: ab23cd45ef67
Create Date: 2026-07-05 01:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID


revision: str = "ac34de56fa78"
down_revision: Union[str, None] = "ab23cd45ef67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brands",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("storefront_mode", sa.String(50), nullable=False, server_default=sa.text("'food_stall'")),
        sa.Column("theme_config", JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("company_id", "slug", name="uq_brands_company_slug"),
    )
    op.create_index("ix_brands_company_id", "brands", ["company_id"])
    op.create_index("ix_brands_company_active", "brands", ["company_id", "is_active"])

    op.create_table(
        "brand_branches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("branch_type", sa.String(30), nullable=False, server_default=sa.text("'company_owned'")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("brand_id", "branch_id", name="uq_brand_branches_brand_branch"),
    )
    op.create_index("ix_brand_branches_company_id", "brand_branches", ["company_id"])
    op.create_index("ix_brand_branches_brand_id", "brand_branches", ["brand_id"])
    op.create_index("ix_brand_branches_branch_id", "brand_branches", ["branch_id"])
    op.create_index("ix_brand_branches_company_brand", "brand_branches", ["company_id", "brand_id"])

    op.add_column("products", sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=True))
    op.create_index("ix_products_brand_id", "products", ["brand_id"])
    op.add_column("recipes", sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=True))
    op.create_index("ix_recipes_brand_id", "recipes", ["brand_id"])
    op.add_column("wap_shift_closures", sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=True))
    op.create_index("ix_wap_shift_closures_brand_id", "wap_shift_closures", ["brand_id"])
    op.add_column("central_orders", sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=True))
    op.create_index("ix_central_orders_brand_id", "central_orders", ["brand_id"])

    op.create_table(
        "credit_accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("credit_limit", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("balance", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("reserved_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("brand_id", "branch_id", name="uq_credit_accounts_brand_branch"),
    )
    op.create_index("ix_credit_accounts_company_id", "credit_accounts", ["company_id"])
    op.create_index("ix_credit_accounts_brand_id", "credit_accounts", ["brand_id"])
    op.create_index("ix_credit_accounts_branch_id", "credit_accounts", ["branch_id"])
    op.create_index("ix_credit_accounts_company_brand", "credit_accounts", ["company_id", "brand_id"])

    op.create_table(
        "credit_ledgers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("credit_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("entry_type", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(15, 2), nullable=False),
        sa.Column("reserved_after", sa.Numeric(15, 2), nullable=False),
        sa.Column("reference_type", sa.String(50), nullable=True),
        sa.Column("reference_id", sa.String(100), nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_credit_ledgers_account_id", "credit_ledgers", ["account_id"])
    op.create_index("ix_credit_ledgers_company_id", "credit_ledgers", ["company_id"])
    op.create_index("ix_credit_ledgers_brand_id", "credit_ledgers", ["brand_id"])
    op.create_index("ix_credit_ledgers_branch_id", "credit_ledgers", ["branch_id"])
    op.create_index("ix_credit_ledgers_created_by", "credit_ledgers", ["created_by"])
    op.create_index("ix_credit_ledgers_account_created", "credit_ledgers", ["account_id", "created_at"])
    op.create_index("ix_credit_ledgers_reference", "credit_ledgers", ["reference_type", "reference_id"])


def downgrade() -> None:
    op.drop_table("credit_ledgers")
    op.drop_table("credit_accounts")
    op.drop_index("ix_central_orders_brand_id", table_name="central_orders")
    op.drop_column("central_orders", "brand_id")
    op.drop_index("ix_wap_shift_closures_brand_id", table_name="wap_shift_closures")
    op.drop_column("wap_shift_closures", "brand_id")
    op.drop_index("ix_recipes_brand_id", table_name="recipes")
    op.drop_column("recipes", "brand_id")
    op.drop_index("ix_products_brand_id", table_name="products")
    op.drop_column("products", "brand_id")
    op.drop_table("brand_branches")
    op.drop_table("brands")
