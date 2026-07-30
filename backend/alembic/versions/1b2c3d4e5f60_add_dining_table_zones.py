"""add dining table zones

Revision ID: 1b2c3d4e5f60
Revises: 0a7b3c4d5e62
Create Date: 2026-07-29 20:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1b2c3d4e5f60"
down_revision: Union[str, None] = "0a7b3c4d5e62"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dining_tables",
        sa.Column(
            "zone",
            sa.String(length=100),
            server_default=sa.text("'โซนทั่วไป'"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_dining_tables_branch_zone",
        "dining_tables",
        ["branch_id", "zone"],
    )


def downgrade() -> None:
    op.drop_index("ix_dining_tables_branch_zone", table_name="dining_tables")
    op.drop_column("dining_tables", "zone")
