"""add branch PromptPay QR image

Revision ID: 3d4e5f6a7b82
Revises: 2c3d4e5f6a71
Create Date: 2026-07-31 19:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3d4e5f6a7b82"
down_revision: Union[str, None] = "2c3d4e5f6a71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "branch_settings",
        sa.Column("promptpay_qr_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("branch_settings", "promptpay_qr_url")
