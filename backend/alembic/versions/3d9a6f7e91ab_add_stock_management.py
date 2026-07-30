"""add_stock_management

Revision ID: 3d9a6f7e91ab
Revises: 8f4b6a7c1234
Create Date: 2026-05-13 23:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3d9a6f7e91ab"
down_revision: Union[str, None] = "8f4b6a7c1234"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("stock_locations"):
        op.create_table(
            "stock_locations",
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("branch_id", sa.UUID(), nullable=False),
            sa.Column("code", sa.String(length=20), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.String(length=500), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_stock_locations_branch_id_branches")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_stock_locations_company_id_companies")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_locations")),
            sa.UniqueConstraint("branch_id", "code", name="uq_stock_locations_branch_id_code"),
        )
        op.create_index(op.f("ix_stock_locations_branch_id"), "stock_locations", ["branch_id"], unique=False)
        op.create_index(op.f("ix_stock_locations_company_id"), "stock_locations", ["company_id"], unique=False)

    if not inspector.has_table("stock_balances"):
        op.create_table(
            "stock_balances",
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("branch_id", sa.UUID(), nullable=False),
            sa.Column("location_id", sa.UUID(), nullable=False),
            sa.Column("product_id", sa.UUID(), nullable=False),
            sa.Column("variant_id", sa.UUID(), nullable=True),
            sa.Column("qty_on_hand", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
            sa.Column("qty_reserved", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
            sa.Column("cost_per_unit", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
            sa.Column("last_movement_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_stock_balances_branch_id_branches")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_stock_balances_company_id_companies")),
            sa.ForeignKeyConstraint(["location_id"], ["stock_locations.id"], name=op.f("fk_stock_balances_location_id_stock_locations")),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_stock_balances_product_id_products")),
            sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"], name=op.f("fk_stock_balances_variant_id_product_variants")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_balances")),
            sa.UniqueConstraint("location_id", "product_id", "variant_id", name="uq_stock_balances_location_product_variant"),
        )
        op.create_index(op.f("ix_stock_balances_branch_id"), "stock_balances", ["branch_id"], unique=False)
        op.create_index(op.f("ix_stock_balances_company_id"), "stock_balances", ["company_id"], unique=False)
        op.create_index(op.f("ix_stock_balances_location_id"), "stock_balances", ["location_id"], unique=False)
        op.create_index(op.f("ix_stock_balances_product_id"), "stock_balances", ["product_id"], unique=False)
        op.create_index(op.f("ix_stock_balances_variant_id"), "stock_balances", ["variant_id"], unique=False)

    if not inspector.has_table("stock_movements"):
        op.create_table(
            "stock_movements",
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("branch_id", sa.UUID(), nullable=False),
            sa.Column("location_id", sa.UUID(), nullable=False),
            sa.Column("product_id", sa.UUID(), nullable=False),
            sa.Column("variant_id", sa.UUID(), nullable=True),
            sa.Column("movement_type", sa.String(length=30), nullable=False),
            sa.Column("qty", sa.Numeric(15, 4), nullable=False),
            sa.Column("qty_before", sa.Numeric(15, 4), nullable=False),
            sa.Column("qty_after", sa.Numeric(15, 4), nullable=False),
            sa.Column("cost_per_unit", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
            sa.Column("reference_type", sa.String(length=50), nullable=True),
            sa.Column("reference_id", sa.String(length=100), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_stock_movements_branch_id_branches")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_stock_movements_company_id_companies")),
            sa.ForeignKeyConstraint(["location_id"], ["stock_locations.id"], name=op.f("fk_stock_movements_location_id_stock_locations")),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_stock_movements_product_id_products")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_stock_movements_user_id_users")),
            sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"], name=op.f("fk_stock_movements_variant_id_product_variants")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_movements")),
        )
        op.create_index(op.f("ix_stock_movements_branch_id"), "stock_movements", ["branch_id"], unique=False)
        op.create_index(op.f("ix_stock_movements_company_id"), "stock_movements", ["company_id"], unique=False)
        op.create_index(op.f("ix_stock_movements_created_at"), "stock_movements", ["created_at"], unique=False)
        op.create_index(op.f("ix_stock_movements_location_id"), "stock_movements", ["location_id"], unique=False)
        op.create_index(op.f("ix_stock_movements_product_id"), "stock_movements", ["product_id"], unique=False)
        op.create_index(op.f("ix_stock_movements_user_id"), "stock_movements", ["user_id"], unique=False)
        op.create_index(op.f("ix_stock_movements_variant_id"), "stock_movements", ["variant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_stock_movements_variant_id"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_user_id"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_product_id"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_location_id"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_created_at"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_company_id"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_branch_id"), table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_index(op.f("ix_stock_balances_variant_id"), table_name="stock_balances")
    op.drop_index(op.f("ix_stock_balances_product_id"), table_name="stock_balances")
    op.drop_index(op.f("ix_stock_balances_location_id"), table_name="stock_balances")
    op.drop_index(op.f("ix_stock_balances_company_id"), table_name="stock_balances")
    op.drop_index(op.f("ix_stock_balances_branch_id"), table_name="stock_balances")
    op.drop_table("stock_balances")
    op.drop_index(op.f("ix_stock_locations_company_id"), table_name="stock_locations")
    op.drop_index(op.f("ix_stock_locations_branch_id"), table_name="stock_locations")
    op.drop_table("stock_locations")
