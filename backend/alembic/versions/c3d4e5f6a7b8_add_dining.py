"""add_dining

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-31 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dining_tables",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("capacity", sa.Integer, nullable=False, server_default=sa.text("4")),
        sa.Column("qr_token", UUID(as_uuid=True), nullable=False, unique=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("table_type", sa.String(20), nullable=False, server_default=sa.text("'dine_in'")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'available'")),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_dining_tables_branch_id", "dining_tables", ["branch_id"])

    op.create_table(
        "dining_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("table_id", UUID(as_uuid=True), sa.ForeignKey("dining_tables.id"), nullable=True),
        sa.Column("shift_id", UUID(as_uuid=True), sa.ForeignKey("cashier_shifts.id"), nullable=True),
        sa.Column("opened_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("queue_number", sa.Integer, nullable=True),
        sa.Column("queue_date", sa.String(10), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'open'")),
        sa.Column("guest_count", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("customer_name", sa.String(255), nullable=True),
        sa.Column("customer_phone", sa.String(20), nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("sale_order_id", UUID(as_uuid=True), sa.ForeignKey("sale_orders.id"), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_dining_sessions_branch_id", "dining_sessions", ["branch_id"])
    op.create_index("ix_dining_sessions_table_id", "dining_sessions", ["table_id"])

    op.create_table(
        "dining_orders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("dining_sessions.id"), nullable=False),
        sa.Column("order_number", sa.String(50), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default=sa.text("'qr_self'")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_dining_orders_session_id", "dining_orders", ["session_id"])

    op.create_table(
        "dining_order_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("order_id", UUID(as_uuid=True), sa.ForeignKey("dining_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("product_name", sa.String(500), nullable=False),
        sa.Column("qty", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("unit_price", sa.Numeric(15, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("special_request", sa.String(500), nullable=True),
        sa.Column("station", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_dining_order_items_order_id", "dining_order_items", ["order_id"])

    op.create_table(
        "kitchen_tickets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("dining_sessions.id"), nullable=False),
        sa.Column("order_item_id", UUID(as_uuid=True), sa.ForeignKey("dining_order_items.id"), nullable=False, unique=True),
        sa.Column("product_name", sa.String(500), nullable=False),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("special_request", sa.String(500), nullable=True),
        sa.Column("station", sa.String(50), nullable=True),
        sa.Column("queue_number", sa.Integer, nullable=True),
        sa.Column("table_name", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_kitchen_tickets_branch_status", "kitchen_tickets", ["branch_id", "status"])
    op.create_index("ix_kitchen_tickets_session_id", "kitchen_tickets", ["session_id"])


def downgrade() -> None:
    op.drop_table("kitchen_tickets")
    op.drop_table("dining_order_items")
    op.drop_table("dining_orders")
    op.drop_table("dining_sessions")
    op.drop_table("dining_tables")
