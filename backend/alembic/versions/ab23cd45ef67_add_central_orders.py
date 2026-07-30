"""add_central_orders

Revision ID: ab23cd45ef67
Revises: aa01bb02cc03
Create Date: 2026-07-05 00:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "ab23cd45ef67"
down_revision: Union[str, None] = "aa01bb02cc03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "central_orders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("shift_closure_id", UUID(as_uuid=True), sa.ForeignKey("wap_shift_closures.id"), nullable=False),
        sa.Column("order_number", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'submitted'")),
        sa.Column("business_date", sa.String(10), nullable=False),
        sa.Column("submitted_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("packed_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("shipped_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("received_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("packed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credit_reserved_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("credit_captured_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("credit_released_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_central_orders_company_id", "central_orders", ["company_id"])
    op.create_index("ix_central_orders_branch_id", "central_orders", ["branch_id"])
    op.create_index("ix_central_orders_shift_closure_id", "central_orders", ["shift_closure_id"])
    op.create_index("ix_central_orders_submitted_by", "central_orders", ["submitted_by"])
    op.create_index("ix_central_orders_approved_by", "central_orders", ["approved_by"])
    op.create_index("ix_central_orders_packed_by", "central_orders", ["packed_by"])
    op.create_index("ix_central_orders_shipped_by", "central_orders", ["shipped_by"])
    op.create_index("ix_central_orders_received_by", "central_orders", ["received_by"])
    op.create_index("ix_central_orders_company_status", "central_orders", ["company_id", "status"])
    op.create_index("ix_central_orders_branch_status", "central_orders", ["branch_id", "status"])
    op.create_unique_constraint("uq_central_orders_shift_closure", "central_orders", ["shift_closure_id"])
    op.create_unique_constraint("uq_central_orders_order_number", "central_orders", ["order_number"])

    op.create_table(
        "central_order_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("order_id", UUID(as_uuid=True), sa.ForeignKey("central_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("sku", sa.String(100), nullable=False),
        sa.Column("product_name", sa.String(500), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False, server_default=sa.text("'ชิ้น'")),
        sa.Column("unit_cost", sa.Numeric(15, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("system_qty", sa.Numeric(15, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("requested_qty", sa.Numeric(15, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("approved_qty", sa.Numeric(15, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("shipped_qty", sa.Numeric(15, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("received_qty", sa.Numeric(15, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("requested_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("approved_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("shipped_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_central_order_items_order_id", "central_order_items", ["order_id"])
    op.create_index("ix_central_order_items_company_id", "central_order_items", ["company_id"])
    op.create_index("ix_central_order_items_branch_id", "central_order_items", ["branch_id"])
    op.create_index("ix_central_order_items_product_id", "central_order_items", ["product_id"])


def downgrade() -> None:
    op.drop_table("central_order_items")
    op.drop_table("central_orders")
