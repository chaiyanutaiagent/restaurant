"""add_wap_shift_closures

Revision ID: aa01bb02cc03
Revises: a7b8c9d0e1f2
Create Date: 2026-07-05 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "aa01bb02cc03"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wap_shift_closures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("closed_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("business_date", sa.String(10), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("total_orders", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("total_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_wap_shift_closures_company_id", "wap_shift_closures", ["company_id"])
    op.create_index("ix_wap_shift_closures_branch_id", "wap_shift_closures", ["branch_id"])
    op.create_index("ix_wap_shift_closures_closed_by", "wap_shift_closures", ["closed_by"])
    op.create_index("ix_wap_shift_closures_branch_date", "wap_shift_closures", ["branch_id", "business_date"])

    op.create_table(
        "wap_shift_closure_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("closure_id", UUID(as_uuid=True), sa.ForeignKey("wap_shift_closures.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("item_type", sa.String(30), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("sku", sa.String(100), nullable=False),
        sa.Column("product_name", sa.String(500), nullable=False),
        sa.Column("qty", sa.Numeric(15, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("unit", sa.String(30), nullable=False, server_default=sa.text("'ชิ้น'")),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_wap_shift_closure_items_company_id", "wap_shift_closure_items", ["company_id"])
    op.create_index("ix_wap_shift_closure_items_branch_id", "wap_shift_closure_items", ["branch_id"])
    op.create_index("ix_wap_shift_closure_items_closure_type", "wap_shift_closure_items", ["closure_id", "item_type"])


def downgrade() -> None:
    op.drop_table("wap_shift_closure_items")
    op.drop_table("wap_shift_closures")
