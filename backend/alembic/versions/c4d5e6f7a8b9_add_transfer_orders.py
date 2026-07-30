"""add_transfer_orders

Revision ID: c4d5e6f7a8b9
Revises: b7c9d1e2f3a4
Create Date: 2026-05-14 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b7c9d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("transfer_orders"):
        op.create_table(
            "transfer_orders",
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("to_number", sa.String(length=30), nullable=False),
            sa.Column("status", sa.String(length=20), server_default=sa.text("'draft'"), nullable=False),
            sa.Column("from_branch_id", sa.UUID(), nullable=False),
            sa.Column("to_branch_id", sa.UUID(), nullable=False),
            sa.Column("from_location_id", sa.UUID(), nullable=False),
            sa.Column("to_location_id", sa.UUID(), nullable=False),
            sa.Column("requested_by", sa.UUID(), nullable=False),
            sa.Column("approved_by", sa.UUID(), nullable=True),
            sa.Column("received_by", sa.UUID(), nullable=True),
            sa.Column("request_date", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False),
            sa.Column("expected_date", sa.Date(), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancel_reason", sa.Text(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.CheckConstraint("from_location_id <> to_location_id", name="ck_transfer_orders_locations_different"),
            sa.ForeignKeyConstraint(["approved_by"], ["users.id"], name=op.f("fk_transfer_orders_approved_by_users")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_transfer_orders_company_id_companies")),
            sa.ForeignKeyConstraint(["from_branch_id"], ["branches.id"], name=op.f("fk_transfer_orders_from_branch_id_branches")),
            sa.ForeignKeyConstraint(["from_location_id"], ["stock_locations.id"], name=op.f("fk_transfer_orders_from_location_id_stock_locations")),
            sa.ForeignKeyConstraint(["received_by"], ["users.id"], name=op.f("fk_transfer_orders_received_by_users")),
            sa.ForeignKeyConstraint(["requested_by"], ["users.id"], name=op.f("fk_transfer_orders_requested_by_users")),
            sa.ForeignKeyConstraint(["to_branch_id"], ["branches.id"], name=op.f("fk_transfer_orders_to_branch_id_branches")),
            sa.ForeignKeyConstraint(["to_location_id"], ["stock_locations.id"], name=op.f("fk_transfer_orders_to_location_id_stock_locations")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_transfer_orders")),
            sa.UniqueConstraint("to_number", name=op.f("uq_transfer_orders_to_number")),
        )
        op.create_index(op.f("ix_transfer_orders_company_id"), "transfer_orders", ["company_id"], unique=False)
        op.create_index(op.f("ix_transfer_orders_to_number"), "transfer_orders", ["to_number"], unique=False)
        op.create_index(op.f("ix_transfer_orders_from_branch_id"), "transfer_orders", ["from_branch_id"], unique=False)
        op.create_index(op.f("ix_transfer_orders_to_branch_id"), "transfer_orders", ["to_branch_id"], unique=False)
        op.create_index(op.f("ix_transfer_orders_from_location_id"), "transfer_orders", ["from_location_id"], unique=False)
        op.create_index(op.f("ix_transfer_orders_to_location_id"), "transfer_orders", ["to_location_id"], unique=False)
        op.create_index("ix_transfer_orders_company_id_to_number", "transfer_orders", ["company_id", "to_number"], unique=False)
        op.create_index("ix_transfer_orders_status", "transfer_orders", ["status"], unique=False)

    if not inspector.has_table("transfer_order_items"):
        op.create_table(
            "transfer_order_items",
            sa.Column("to_id", sa.UUID(), nullable=False),
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("product_id", sa.UUID(), nullable=False),
            sa.Column("variant_id", sa.UUID(), nullable=True),
            sa.Column("product_name", sa.String(length=500), nullable=False),
            sa.Column("sku", sa.String(length=100), nullable=False),
            sa.Column("unit_code", sa.String(length=20), nullable=True),
            sa.Column("qty_requested", sa.Numeric(15, 4), nullable=False),
            sa.Column("qty_approved", sa.Numeric(15, 4), nullable=True),
            sa.Column("qty_sent", sa.Numeric(15, 4), nullable=True),
            sa.Column("qty_received", sa.Numeric(15, 4), nullable=True),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_transfer_order_items_company_id_companies")),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_transfer_order_items_product_id_products")),
            sa.ForeignKeyConstraint(["to_id"], ["transfer_orders.id"], name=op.f("fk_transfer_order_items_to_id_transfer_orders")),
            sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"], name=op.f("fk_transfer_order_items_variant_id_product_variants")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_transfer_order_items")),
        )
        op.create_index(op.f("ix_transfer_order_items_to_id"), "transfer_order_items", ["to_id"], unique=False)
        op.create_index(op.f("ix_transfer_order_items_company_id"), "transfer_order_items", ["company_id"], unique=False)
        op.create_index(op.f("ix_transfer_order_items_product_id"), "transfer_order_items", ["product_id"], unique=False)
        op.create_index(op.f("ix_transfer_order_items_variant_id"), "transfer_order_items", ["variant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_transfer_order_items_variant_id"), table_name="transfer_order_items")
    op.drop_index(op.f("ix_transfer_order_items_product_id"), table_name="transfer_order_items")
    op.drop_index(op.f("ix_transfer_order_items_company_id"), table_name="transfer_order_items")
    op.drop_index(op.f("ix_transfer_order_items_to_id"), table_name="transfer_order_items")
    op.drop_table("transfer_order_items")
    op.drop_index("ix_transfer_orders_status", table_name="transfer_orders")
    op.drop_index("ix_transfer_orders_company_id_to_number", table_name="transfer_orders")
    op.drop_index(op.f("ix_transfer_orders_to_location_id"), table_name="transfer_orders")
    op.drop_index(op.f("ix_transfer_orders_from_location_id"), table_name="transfer_orders")
    op.drop_index(op.f("ix_transfer_orders_to_branch_id"), table_name="transfer_orders")
    op.drop_index(op.f("ix_transfer_orders_from_branch_id"), table_name="transfer_orders")
    op.drop_index(op.f("ix_transfer_orders_to_number"), table_name="transfer_orders")
    op.drop_index(op.f("ix_transfer_orders_company_id"), table_name="transfer_orders")
    op.drop_table("transfer_orders")
