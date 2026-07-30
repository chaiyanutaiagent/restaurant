"""add partial refund tracking

Revision ID: 9f8e7d6c5b4a
Revises: 8c1d2e3f4a5b
Create Date: 2026-05-24 19:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9f8e7d6c5b4a"
down_revision = "8c1d2e3f4a5b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sale_orders",
        sa.Column("refund_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "sale_order_items",
        sa.Column("refunded_qty", sa.Numeric(15, 4), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "sale_order_items",
        sa.Column("refunded_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("sale_order_items", "refunded_amount")
    op.drop_column("sale_order_items", "refunded_qty")
    op.drop_column("sale_orders", "refund_amount")
