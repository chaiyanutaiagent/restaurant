"""add branch receipt logo

Revision ID: 4e5f6a7b8c93
Revises: 3d4e5f6a7b82
Create Date: 2026-07-31 19:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4e5f6a7b8c93"
down_revision: Union[str, None] = "3d4e5f6a7b82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "branch_settings",
        sa.Column("receipt_logo_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("branch_settings", "receipt_logo_url")
