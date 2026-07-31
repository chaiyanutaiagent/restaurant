"""initialize restaurant database boundary

Revision ID: p1restaurant0001
Revises:
Create Date: 2026-08-01 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p1restaurant0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "database_boundary_metadata",
        sa.Column("boundary_name", sa.String(length=40), primary_key=True),
        sa.Column("schema_contract_version", sa.Integer(), nullable=False),
        sa.Column(
            "initialized_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.execute(
        "INSERT INTO database_boundary_metadata "
        "(boundary_name, schema_contract_version) VALUES ('restaurant', 1)"
    )


def downgrade() -> None:
    op.drop_table("database_boundary_metadata")
