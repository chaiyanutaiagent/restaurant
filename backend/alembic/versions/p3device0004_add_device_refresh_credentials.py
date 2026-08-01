"""add persistent device refresh credentials

Revision ID: p3device0004
Revises: p3device0003
Create Date: 2026-08-01 12:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p3device0004"
down_revision: Union[str, None] = "p3device0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "device_registrations",
        sa.Column("refresh_credential_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "device_registrations",
        sa.Column("refresh_credential_issued_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("device_registrations", "refresh_credential_issued_at")
    op.drop_column("device_registrations", "refresh_credential_hash")
