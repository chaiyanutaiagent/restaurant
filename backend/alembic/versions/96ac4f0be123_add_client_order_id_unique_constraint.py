"""add_client_order_id_unique_constraint

Revision ID: 96ac4f0be123
Revises: 6b1f7c2d4e5a
Create Date: 2026-05-14 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "96ac4f0be123"
down_revision: Union[str, None] = "6b1f7c2d4e5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    unique_constraints = {item["name"] for item in inspector.get_unique_constraints("sale_orders")}
    if "uq_sale_orders_client_order_id" not in unique_constraints:
        op.create_unique_constraint(
            "uq_sale_orders_client_order_id",
            "sale_orders",
            ["company_id", "client_order_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    unique_constraints = {item["name"] for item in inspector.get_unique_constraints("sale_orders")}
    if "uq_sale_orders_client_order_id" in unique_constraints:
        op.drop_constraint("uq_sale_orders_client_order_id", "sale_orders", type_="unique")
