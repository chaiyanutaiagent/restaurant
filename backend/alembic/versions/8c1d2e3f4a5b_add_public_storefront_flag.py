"""add public storefront flag

Revision ID: 8c1d2e3f4a5b
Revises: 7e8f9a0b1c2d
Create Date: 2026-05-24 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8c1d2e3f4a5b"
down_revision = "7e8f9a0b1c2d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "branch_settings",
        sa.Column("public_storefront_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("branch_settings", "public_storefront_enabled")
