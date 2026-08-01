"""add Platform persistent device refresh credentials

Revision ID: p3platform0007
Revises: p3platform0006
Create Date: 2026-08-01 12:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p3platform0007"
down_revision: Union[str, None] = "p3platform0006"
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
    op.execute(
        "UPDATE database_boundary_metadata SET schema_contract_version = 5 "
        "WHERE boundary_name = 'platform_core'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE database_boundary_metadata SET schema_contract_version = 4 "
        "WHERE boundary_name = 'platform_core'"
    )
    op.drop_column("device_registrations", "refresh_credential_issued_at")
    op.drop_column("device_registrations", "refresh_credential_hash")
