"""add Takeaway store operation parity fields

Revision ID: p6takeaway0005
Revises: p6takeaway0004
Create Date: 2026-09-16 19:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p6takeaway0005"
down_revision: Union[str, None] = "p6takeaway0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "takeaway_receipts",
        sa.Column("print_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "takeaway_receipts",
        sa.Column("last_printed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "takeaway_receipts",
        sa.Column("last_printed_copy", sa.String(length=20), nullable=True),
    )
    op.create_check_constraint(
        "ck_takeaway_receipt_print_copy",
        "takeaway_receipts",
        "last_printed_copy IS NULL OR last_printed_copy IN ('customer', 'merchant')",
    )

    op.add_column(
        "takeaway_central_orders",
        sa.Column("idempotency_key", sa.String(length=180), nullable=True),
    )
    op.execute(
        "UPDATE takeaway_central_orders "
        "SET idempotency_key = 'legacy-central-order:' || id::text "
        "WHERE idempotency_key IS NULL"
    )
    op.alter_column("takeaway_central_orders", "idempotency_key", nullable=False)
    op.create_unique_constraint(
        "uq_takeaway_central_order_idempotency",
        "takeaway_central_orders",
        ["branch_id", "idempotency_key"],
    )

    op.add_column(
        "takeaway_stock_movements",
        sa.Column("note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("takeaway_stock_movements", "note")
    op.drop_constraint(
        "uq_takeaway_central_order_idempotency",
        "takeaway_central_orders",
        type_="unique",
    )
    op.drop_column("takeaway_central_orders", "idempotency_key")
    op.drop_constraint(
        "ck_takeaway_receipt_print_copy",
        "takeaway_receipts",
        type_="check",
    )
    op.drop_column("takeaway_receipts", "last_printed_copy")
    op.drop_column("takeaway_receipts", "last_printed_at")
    op.drop_column("takeaway_receipts", "print_count")
