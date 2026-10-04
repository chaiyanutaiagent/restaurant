"""scope Takeaway stock-location codes to a branch

Revision ID: p6takeaway0008
Revises: p6takeaway0007
Create Date: 2026-09-17 16:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "p6takeaway0008"
down_revision: Union[str, None] = "p6takeaway0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_takeaway_stock_location_code",
        "takeaway_stock_locations",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_takeaway_stock_location_code",
        "takeaway_stock_locations",
        ["company_id", "branch_id", "code"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_takeaway_stock_location_code",
        "takeaway_stock_locations",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_takeaway_stock_location_code",
        "takeaway_stock_locations",
        ["company_id", "code"],
    )
