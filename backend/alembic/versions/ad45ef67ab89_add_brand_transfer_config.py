"""add_brand_transfer_config

Revision ID: ad45ef67ab89
Revises: ac34de56fa78
Create Date: 2026-07-05 01:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "ad45ef67ab89"
down_revision: Union[str, None] = "ac34de56fa78"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("brands", sa.Column("central_branch_id", UUID(as_uuid=True), sa.ForeignKey("branches.id"), nullable=True))
    op.add_column("brands", sa.Column("central_location_id", UUID(as_uuid=True), sa.ForeignKey("stock_locations.id"), nullable=True))
    op.create_index("ix_brands_central_branch_id", "brands", ["central_branch_id"])
    op.create_index("ix_brands_central_location_id", "brands", ["central_location_id"])

    op.add_column("brand_branches", sa.Column("store_location_id", UUID(as_uuid=True), sa.ForeignKey("stock_locations.id"), nullable=True))
    op.create_index("ix_brand_branches_store_location_id", "brand_branches", ["store_location_id"])

    op.add_column("central_orders", sa.Column("transfer_order_id", UUID(as_uuid=True), sa.ForeignKey("transfer_orders.id"), nullable=True))
    op.create_index("ix_central_orders_transfer_order_id", "central_orders", ["transfer_order_id"])


def downgrade() -> None:
    op.drop_index("ix_central_orders_transfer_order_id", table_name="central_orders")
    op.drop_column("central_orders", "transfer_order_id")
    op.drop_index("ix_brand_branches_store_location_id", table_name="brand_branches")
    op.drop_column("brand_branches", "store_location_id")
    op.drop_index("ix_brands_central_location_id", table_name="brands")
    op.drop_index("ix_brands_central_branch_id", table_name="brands")
    op.drop_column("brands", "central_location_id")
    op.drop_column("brands", "central_branch_id")
