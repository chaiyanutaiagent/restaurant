"""add_purchase_management

Revision ID: b7c9d1e2f3a4
Revises: 96ac4f0be123
Create Date: 2026-05-14 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c9d1e2f3a4"
down_revision: Union[str, None] = "96ac4f0be123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("suppliers"):
        op.create_table(
            "suppliers",
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("code", sa.String(length=20), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("name_en", sa.String(length=255), nullable=True),
            sa.Column("tax_id", sa.String(length=20), nullable=True),
            sa.Column("branch_code", sa.String(length=10), nullable=True),
            sa.Column("address", sa.Text(), nullable=True),
            sa.Column("address_en", sa.Text(), nullable=True),
            sa.Column("phone", sa.String(length=20), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("contact_person", sa.String(length=255), nullable=True),
            sa.Column("payment_term_days", sa.Integer(), server_default=sa.text("30"), nullable=False),
            sa.Column("wht_rate", sa.Numeric(5, 2), server_default=sa.text("3.00"), nullable=False),
            sa.Column("wht_type", sa.String(length=50), nullable=True),
            sa.Column("credit_limit", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
            sa.Column("bank_name", sa.String(length=100), nullable=True),
            sa.Column("bank_account", sa.String(length=30), nullable=True),
            sa.Column("bank_account_name", sa.String(length=255), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_suppliers_company_id_companies")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_suppliers")),
            sa.UniqueConstraint("company_id", "code", name="uq_suppliers_company_id_code"),
        )
        op.create_index(op.f("ix_suppliers_company_id"), "suppliers", ["company_id"], unique=False)

    if not inspector.has_table("purchase_orders"):
        op.create_table(
            "purchase_orders",
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("branch_id", sa.UUID(), nullable=False),
            sa.Column("supplier_id", sa.UUID(), nullable=False),
            sa.Column("created_by", sa.UUID(), nullable=False),
            sa.Column("approved_by", sa.UUID(), nullable=True),
            sa.Column("po_number", sa.String(length=30), nullable=False),
            sa.Column("status", sa.String(length=20), server_default=sa.text("'draft'"), nullable=False),
            sa.Column("order_date", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False),
            sa.Column("expected_date", sa.Date(), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancel_reason", sa.Text(), nullable=True),
            sa.Column("subtotal", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
            sa.Column("discount_amount", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
            sa.Column("vat_amount", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
            sa.Column("wht_amount", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
            sa.Column("total_amount", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
            sa.Column("paid_amount", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
            sa.Column("remaining_amount", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
            sa.Column("vat_type", sa.String(length=20), server_default=sa.text("'excluded'"), nullable=False),
            sa.Column("vat_rate", sa.Numeric(5, 2), server_default=sa.text("7.00"), nullable=False),
            sa.Column("wht_rate", sa.Numeric(5, 2), server_default=sa.text("3.00"), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("internal_note", sa.Text(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["approved_by"], ["users.id"], name=op.f("fk_purchase_orders_approved_by_users")),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_purchase_orders_branch_id_branches")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_purchase_orders_company_id_companies")),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_purchase_orders_created_by_users")),
            sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name=op.f("fk_purchase_orders_supplier_id_suppliers")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_orders")),
            sa.UniqueConstraint("po_number", name=op.f("uq_purchase_orders_po_number")),
        )
        op.create_index(op.f("ix_purchase_orders_branch_id"), "purchase_orders", ["branch_id"], unique=False)
        op.create_index(op.f("ix_purchase_orders_company_id"), "purchase_orders", ["company_id"], unique=False)
        op.create_index(op.f("ix_purchase_orders_supplier_id"), "purchase_orders", ["supplier_id"], unique=False)
        op.create_index("ix_purchase_orders_company_id_po_number", "purchase_orders", ["company_id", "po_number"], unique=False)
        op.create_index("ix_purchase_orders_status", "purchase_orders", ["status"], unique=False)
        op.create_index("ix_purchase_orders_order_date", "purchase_orders", ["order_date"], unique=False)

    if not inspector.has_table("purchase_order_items"):
        op.create_table(
            "purchase_order_items",
            sa.Column("po_id", sa.UUID(), nullable=False),
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("product_id", sa.UUID(), nullable=False),
            sa.Column("variant_id", sa.UUID(), nullable=True),
            sa.Column("product_name", sa.String(length=500), nullable=False),
            sa.Column("sku", sa.String(length=100), nullable=False),
            sa.Column("unit_code", sa.String(length=20), nullable=True),
            sa.Column("qty_ordered", sa.Numeric(15, 4), nullable=False),
            sa.Column("qty_received", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
            sa.Column("unit_cost", sa.Numeric(15, 4), nullable=False),
            sa.Column("discount_amount", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
            sa.Column("vat_type", sa.String(length=20), server_default=sa.text("'excluded'"), nullable=False),
            sa.Column("vat_rate", sa.Numeric(5, 2), server_default=sa.text("7.00"), nullable=False),
            sa.Column("vat_amount", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
            sa.Column("subtotal", sa.Numeric(15, 4), nullable=False),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_purchase_order_items_company_id_companies")),
            sa.ForeignKeyConstraint(["po_id"], ["purchase_orders.id"], name=op.f("fk_purchase_order_items_po_id_purchase_orders")),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_purchase_order_items_product_id_products")),
            sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"], name=op.f("fk_purchase_order_items_variant_id_product_variants")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_order_items")),
        )
        op.create_index(op.f("ix_purchase_order_items_company_id"), "purchase_order_items", ["company_id"], unique=False)
        op.create_index(op.f("ix_purchase_order_items_po_id"), "purchase_order_items", ["po_id"], unique=False)
        op.create_index(op.f("ix_purchase_order_items_product_id"), "purchase_order_items", ["product_id"], unique=False)
        op.create_index(op.f("ix_purchase_order_items_variant_id"), "purchase_order_items", ["variant_id"], unique=False)

    if not inspector.has_table("goods_receipts"):
        op.create_table(
            "goods_receipts",
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("branch_id", sa.UUID(), nullable=False),
            sa.Column("po_id", sa.UUID(), nullable=False),
            sa.Column("location_id", sa.UUID(), nullable=False),
            sa.Column("received_by", sa.UUID(), nullable=False),
            sa.Column("gr_number", sa.String(length=30), nullable=False),
            sa.Column("received_date", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_goods_receipts_branch_id_branches")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_goods_receipts_company_id_companies")),
            sa.ForeignKeyConstraint(["location_id"], ["stock_locations.id"], name=op.f("fk_goods_receipts_location_id_stock_locations")),
            sa.ForeignKeyConstraint(["po_id"], ["purchase_orders.id"], name=op.f("fk_goods_receipts_po_id_purchase_orders")),
            sa.ForeignKeyConstraint(["received_by"], ["users.id"], name=op.f("fk_goods_receipts_received_by_users")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_goods_receipts")),
            sa.UniqueConstraint("gr_number", name=op.f("uq_goods_receipts_gr_number")),
        )
        op.create_index(op.f("ix_goods_receipts_company_id"), "goods_receipts", ["company_id"], unique=False)
        op.create_index(op.f("ix_goods_receipts_po_id"), "goods_receipts", ["po_id"], unique=False)
        op.create_index("ix_goods_receipts_company_id_gr_number", "goods_receipts", ["company_id", "gr_number"], unique=False)

    if not inspector.has_table("goods_receipt_items"):
        op.create_table(
            "goods_receipt_items",
            sa.Column("gr_id", sa.UUID(), nullable=False),
            sa.Column("po_item_id", sa.UUID(), nullable=False),
            sa.Column("product_id", sa.UUID(), nullable=False),
            sa.Column("variant_id", sa.UUID(), nullable=True),
            sa.Column("qty_received", sa.Numeric(15, 4), nullable=False),
            sa.Column("unit_cost", sa.Numeric(15, 4), nullable=False),
            sa.Column("note", sa.String(length=500), nullable=True),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["gr_id"], ["goods_receipts.id"], name=op.f("fk_goods_receipt_items_gr_id_goods_receipts")),
            sa.ForeignKeyConstraint(["po_item_id"], ["purchase_order_items.id"], name=op.f("fk_goods_receipt_items_po_item_id_purchase_order_items")),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_goods_receipt_items_product_id_products")),
            sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"], name=op.f("fk_goods_receipt_items_variant_id_product_variants")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_goods_receipt_items")),
        )
        op.create_index(op.f("ix_goods_receipt_items_gr_id"), "goods_receipt_items", ["gr_id"], unique=False)
        op.create_index(op.f("ix_goods_receipt_items_po_item_id"), "goods_receipt_items", ["po_item_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_goods_receipt_items_po_item_id"), table_name="goods_receipt_items")
    op.drop_index(op.f("ix_goods_receipt_items_gr_id"), table_name="goods_receipt_items")
    op.drop_table("goods_receipt_items")
    op.drop_index("ix_goods_receipts_company_id_gr_number", table_name="goods_receipts")
    op.drop_index(op.f("ix_goods_receipts_po_id"), table_name="goods_receipts")
    op.drop_index(op.f("ix_goods_receipts_company_id"), table_name="goods_receipts")
    op.drop_table("goods_receipts")
    op.drop_index(op.f("ix_purchase_order_items_variant_id"), table_name="purchase_order_items")
    op.drop_index(op.f("ix_purchase_order_items_product_id"), table_name="purchase_order_items")
    op.drop_index(op.f("ix_purchase_order_items_po_id"), table_name="purchase_order_items")
    op.drop_index(op.f("ix_purchase_order_items_company_id"), table_name="purchase_order_items")
    op.drop_table("purchase_order_items")
    op.drop_index("ix_purchase_orders_order_date", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_status", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_company_id_po_number", table_name="purchase_orders")
    op.drop_index(op.f("ix_purchase_orders_supplier_id"), table_name="purchase_orders")
    op.drop_index(op.f("ix_purchase_orders_company_id"), table_name="purchase_orders")
    op.drop_index(op.f("ix_purchase_orders_branch_id"), table_name="purchase_orders")
    op.drop_table("purchase_orders")
    op.drop_index(op.f("ix_suppliers_company_id"), table_name="suppliers")
    op.drop_table("suppliers")
