"""add_qs_qr_token

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-31 04:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "branch_settings",
        sa.Column("fb_qs_qr_token", UUID(as_uuid=True), nullable=True, unique=True),
    )


def downgrade() -> None:
    op.drop_column("branch_settings", "fb_qs_qr_token")
