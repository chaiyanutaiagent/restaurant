"""add_pos_tables

Revision ID: 6b1f7c2d4e5a
Revises: 3d9a6f7e91ab
Create Date: 2026-05-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6b1f7c2d4e5a"
down_revision: Union[str, None] = "3d9a6f7e91ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("cashier_shifts"):
        op.create_table(
            "cashier_shifts",
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("branch_id", sa.UUID(), nullable=False),
            sa.Column("location_id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("shift_number", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=20), server_default=sa.text("'open'"), nullable=False),
            sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("opening_cash", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
            sa.Column("closing_cash", sa.Numeric(15, 2), nullable=True),
            sa.Column("expected_cash", sa.Numeric(15, 2), nullable=True),
            sa.Column("cash_difference", sa.Numeric(15, 2), nullable=True),
            sa.Column("total_sales", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
            sa.Column("total_orders", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("total_voids", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_cashier_shifts_branch_id_branches")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_cashier_shifts_company_id_companies")),
            sa.ForeignKeyConstraint(["location_id"], ["stock_locations.id"], name=op.f("fk_cashier_shifts_location_id_stock_locations")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_cashier_shifts_user_id_users")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_cashier_shifts")),
        )
        op.create_index(op.f("ix_cashier_shifts_branch_id"), "cashier_shifts", ["branch_id"], unique=False)
        op.create_index(op.f("ix_cashier_shifts_company_id"), "cashier_shifts", ["company_id"], unique=False)
        op.create_index(op.f("ix_cashier_shifts_location_id"), "cashier_shifts", ["location_id"], unique=False)
        op.create_index(op.f("ix_cashier_shifts_user_id"), "cashier_shifts", ["user_id"], unique=False)
        op.create_index(
            "ix_cashier_shifts_user_branch_open_unique",
            "cashier_shifts",
            ["user_id", "branch_id"],
            unique=True,
            postgresql_where=sa.text("status = 'open'"),
        )

    if not inspector.has_table("sale_orders"):
        op.create_table(
            "sale_orders",
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("branch_id", sa.UUID(), nullable=False),
            sa.Column("location_id", sa.UUID(), nullable=False),
            sa.Column("shift_id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("order_number", sa.String(length=30), nullable=False),
            sa.Column("status", sa.String(length=20), server_default=sa.text("'completed'"), nullable=False),
            sa.Column("customer_name", sa.String(length=255), nullable=True),
            sa.Column("customer_phone", sa.String(length=20), nullable=True),
            sa.Column("customer_tax_id", sa.String(length=20), nullable=True),
            sa.Column("subtotal", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
            sa.Column("discount_amount", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
            sa.Column("discount_type", sa.String(length=10), server_default=sa.text("'amount'"), nullable=False),
            sa.Column("vat_amount", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
            sa.Column("vat_rate", sa.Numeric(5, 2), server_default=sa.text("7.00"), nullable=False),
            sa.Column("total_amount", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
            sa.Column("paid_amount", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
            sa.Column("change_amount", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
            sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("voided_by", sa.UUID(), nullable=True),
            sa.Column("void_reason", sa.Text(), nullable=True),
            sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_offline", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("client_order_id", sa.String(length=100), nullable=True),
            sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_sale_orders_branch_id_branches")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_sale_orders_company_id_companies")),
            sa.ForeignKeyConstraint(["location_id"], ["stock_locations.id"], name=op.f("fk_sale_orders_location_id_stock_locations")),
            sa.ForeignKeyConstraint(["shift_id"], ["cashier_shifts.id"], name=op.f("fk_sale_orders_shift_id_cashier_shifts")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_sale_orders_user_id_users")),
            sa.ForeignKeyConstraint(["voided_by"], ["users.id"], name=op.f("fk_sale_orders_voided_by_users")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_sale_orders")),
            sa.UniqueConstraint("order_number", name=op.f("uq_sale_orders_order_number")),
        )
        op.create_index(op.f("ix_sale_orders_branch_id"), "sale_orders", ["branch_id"], unique=False)
        op.create_index(op.f("ix_sale_orders_company_id"), "sale_orders", ["company_id"], unique=False)
        op.create_index(op.f("ix_sale_orders_location_id"), "sale_orders", ["location_id"], unique=False)
        op.create_index(op.f("ix_sale_orders_shift_id"), "sale_orders", ["shift_id"], unique=False)
        op.create_index(op.f("ix_sale_orders_user_id"), "sale_orders", ["user_id"], unique=False)
        op.create_index("ix_sale_orders_company_id_order_number", "sale_orders", ["company_id", "order_number"], unique=False)
        op.create_index("ix_sale_orders_status", "sale_orders", ["status"], unique=False)
        op.create_index("ix_sale_orders_created_at", "sale_orders", ["created_at"], unique=False)

    if not inspector.has_table("sale_order_items"):
        op.create_table(
            "sale_order_items",
            sa.Column("order_id", sa.UUID(), nullable=False),
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("product_id", sa.UUID(), nullable=False),
            sa.Column("variant_id", sa.UUID(), nullable=True),
            sa.Column("product_name", sa.String(length=500), nullable=False),
            sa.Column("variant_name", sa.String(length=255), nullable=True),
            sa.Column("sku", sa.String(length=100), nullable=False),
            sa.Column("unit_code", sa.String(length=20), nullable=True),
            sa.Column("qty", sa.Numeric(15, 4), nullable=False),
            sa.Column("unit_price", sa.Numeric(15, 4), nullable=False),
            sa.Column("original_price", sa.Numeric(15, 4), nullable=False),
            sa.Column("discount_amount", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
            sa.Column("discount_type", sa.String(length=10), server_default=sa.text("'amount'"), nullable=False),
            sa.Column("vat_type", sa.String(length=20), nullable=False),
            sa.Column("vat_rate", sa.Numeric(5, 2), server_default=sa.text("7.00"), nullable=False),
            sa.Column("vat_amount", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
            sa.Column("subtotal", sa.Numeric(15, 4), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_sale_order_items_company_id_companies")),
            sa.ForeignKeyConstraint(["order_id"], ["sale_orders.id"], name=op.f("fk_sale_order_items_order_id_sale_orders")),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_sale_order_items_product_id_products")),
            sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"], name=op.f("fk_sale_order_items_variant_id_product_variants")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_sale_order_items")),
        )
        op.create_index(op.f("ix_sale_order_items_company_id"), "sale_order_items", ["company_id"], unique=False)
        op.create_index(op.f("ix_sale_order_items_order_id"), "sale_order_items", ["order_id"], unique=False)
        op.create_index(op.f("ix_sale_order_items_product_id"), "sale_order_items", ["product_id"], unique=False)
        op.create_index(op.f("ix_sale_order_items_variant_id"), "sale_order_items", ["variant_id"], unique=False)

    if not inspector.has_table("payments"):
        op.create_table(
            "payments",
            sa.Column("order_id", sa.UUID(), nullable=False),
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("payment_method", sa.String(length=30), nullable=False),
            sa.Column("amount", sa.Numeric(15, 2), nullable=False),
            sa.Column("reference_no", sa.String(length=100), nullable=True),
            sa.Column("paid_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("note", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_payments_company_id_companies")),
            sa.ForeignKeyConstraint(["order_id"], ["sale_orders.id"], name=op.f("fk_payments_order_id_sale_orders")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        )
        op.create_index(op.f("ix_payments_company_id"), "payments", ["company_id"], unique=False)
        op.create_index(op.f("ix_payments_order_id"), "payments", ["order_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_payments_order_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_company_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_index(op.f("ix_sale_order_items_variant_id"), table_name="sale_order_items")
    op.drop_index(op.f("ix_sale_order_items_product_id"), table_name="sale_order_items")
    op.drop_index(op.f("ix_sale_order_items_order_id"), table_name="sale_order_items")
    op.drop_index(op.f("ix_sale_order_items_company_id"), table_name="sale_order_items")
    op.drop_table("sale_order_items")
    op.drop_index("ix_sale_orders_created_at", table_name="sale_orders")
    op.drop_index("ix_sale_orders_status", table_name="sale_orders")
    op.drop_index("ix_sale_orders_company_id_order_number", table_name="sale_orders")
    op.drop_index(op.f("ix_sale_orders_user_id"), table_name="sale_orders")
    op.drop_index(op.f("ix_sale_orders_shift_id"), table_name="sale_orders")
    op.drop_index(op.f("ix_sale_orders_location_id"), table_name="sale_orders")
    op.drop_index(op.f("ix_sale_orders_company_id"), table_name="sale_orders")
    op.drop_index(op.f("ix_sale_orders_branch_id"), table_name="sale_orders")
    op.drop_table("sale_orders")
    op.drop_index("ix_cashier_shifts_user_branch_open_unique", table_name="cashier_shifts")
    op.drop_index(op.f("ix_cashier_shifts_user_id"), table_name="cashier_shifts")
    op.drop_index(op.f("ix_cashier_shifts_location_id"), table_name="cashier_shifts")
    op.drop_index(op.f("ix_cashier_shifts_company_id"), table_name="cashier_shifts")
    op.drop_index(op.f("ix_cashier_shifts_branch_id"), table_name="cashier_shifts")
    op.drop_table("cashier_shifts")
