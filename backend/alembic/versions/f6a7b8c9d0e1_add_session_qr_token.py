"""add session qr token

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-09 11:15:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dining_sessions",
        sa.Column(
            "qr_token",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
    )
    op.create_index("ix_dining_sessions_qr_token", "dining_sessions", ["qr_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_dining_sessions_qr_token", table_name="dining_sessions")
    op.drop_column("dining_sessions", "qr_token")
