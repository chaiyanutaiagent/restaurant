"""add Takeaway catalog sales content

Revision ID: p6takeaway0009
Revises: p6takeaway0008
Create Date: 2026-09-29 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p6takeaway0009"
down_revision: Union[str, None] = "p6takeaway0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("takeaway_catalog_items", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("takeaway_catalog_items", sa.Column("image_url", sa.String(1000), nullable=True))
    op.add_column("takeaway_catalog_items", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("takeaway_catalog_items", sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("takeaway_catalog_items", "is_featured")
    op.drop_column("takeaway_catalog_items", "sort_order")
    op.drop_column("takeaway_catalog_items", "image_url")
    op.drop_column("takeaway_catalog_items", "description")
