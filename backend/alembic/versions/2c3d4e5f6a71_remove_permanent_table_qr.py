"""remove permanent dining table qr token

Revision ID: 2c3d4e5f6a71
Revises: 1b2c3d4e5f60
Create Date: 2026-07-30 16:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "2c3d4e5f6a71"
down_revision: str | None = "1b2c3d4e5f60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("dining_tables", "qr_token")


def downgrade() -> None:
    op.add_column(
        "dining_tables",
        sa.Column(
            "qr_token",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
    )
    op.create_unique_constraint(
        "uq_dining_tables_qr_token",
        "dining_tables",
        ["qr_token"],
    )
