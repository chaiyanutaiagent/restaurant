"""add sale recipe stock posting

Revision ID: e85f1a2b3c40
Revises: c74e8f219a60
Create Date: 2026-07-22 20:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e85f1a2b3c40"
down_revision: Union[str, None] = "c74e8f219a60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sale_orders",
        sa.Column("recipe_stock_status", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "sale_orders",
        sa.Column("recipe_stock_warnings", sa.Text(), nullable=True),
    )
    op.add_column(
        "sale_orders",
        sa.Column("recipe_stock_posted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sale_orders",
        sa.Column("recipe_stock_reversed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sale_orders", "recipe_stock_reversed_at")
    op.drop_column("sale_orders", "recipe_stock_posted_at")
    op.drop_column("sale_orders", "recipe_stock_warnings")
    op.drop_column("sale_orders", "recipe_stock_status")
