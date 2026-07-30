"""add transfer receiving fields

Revision ID: c74e8f219a60
Revises: b63d8e02f415
Create Date: 2026-07-22 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c74e8f219a60"
down_revision: Union[str, None] = "b63d8e02f415"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transfer_orders",
        sa.Column("last_received_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "transfer_orders",
        sa.Column(
            "has_discrepancy",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "transfer_orders",
        sa.Column("discrepancy_note", sa.Text(), nullable=True),
    )
    op.add_column(
        "transfer_orders",
        sa.Column(
            "destination_posted_at_ship",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "transfer_order_items",
        sa.Column(
            "unit_cost",
            sa.Numeric(15, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "transfer_order_items",
        sa.Column(
            "qty_discrepancy",
            sa.Numeric(15, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.execute(
        """
        UPDATE transfer_orders
        SET destination_posted_at_ship = true
        WHERE status = 'in_transit'
        """
    )
    op.execute(
        """
        UPDATE transfer_orders
        SET last_received_at = completed_at
        WHERE completed_at IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE transfer_order_items AS item
        SET qty_discrepancy = GREATEST(
            COALESCE(item.qty_sent, 0) - COALESCE(item.qty_received, 0),
            0
        )
        FROM transfer_orders AS transfer
        WHERE transfer.id = item.to_id
          AND transfer.status = 'completed'
        """
    )
    op.execute(
        """
        UPDATE transfer_orders AS transfer
        SET has_discrepancy = EXISTS (
            SELECT 1
            FROM transfer_order_items AS item
            WHERE item.to_id = transfer.id
              AND item.qty_discrepancy > 0
        )
        WHERE transfer.status = 'completed'
        """
    )


def downgrade() -> None:
    op.drop_column("transfer_order_items", "qty_discrepancy")
    op.drop_column("transfer_order_items", "unit_cost")
    op.drop_column("transfer_orders", "discrepancy_note")
    op.drop_column("transfer_orders", "destination_posted_at_ship")
    op.drop_column("transfer_orders", "has_discrepancy")
    op.drop_column("transfer_orders", "last_received_at")
