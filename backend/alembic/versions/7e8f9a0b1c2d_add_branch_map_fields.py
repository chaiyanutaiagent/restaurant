"""add branch map fields

Revision ID: 7e8f9a0b1c2d
Revises: 1440f535ece8
Create Date: 2026-05-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7e8f9a0b1c2d"
down_revision = "1440f535ece8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("branches", sa.Column("landmark", sa.Text(), nullable=True))
    op.add_column("branches", sa.Column("latitude", sa.Numeric(10, 7), nullable=True))
    op.add_column("branches", sa.Column("longitude", sa.Numeric(10, 7), nullable=True))
    op.add_column("branches", sa.Column("google_maps_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("branches", "google_maps_url")
    op.drop_column("branches", "longitude")
    op.drop_column("branches", "latitude")
    op.drop_column("branches", "landmark")
