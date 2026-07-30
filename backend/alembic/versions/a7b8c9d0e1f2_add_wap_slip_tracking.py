"""add wap slip tracking

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dining_sessions", sa.Column("customer_slip_printed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("dining_sessions", sa.Column("kitchen_slip_printed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("dining_sessions", sa.Column("kitchen_sent_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("dining_sessions", "kitchen_sent_at")
    op.drop_column("dining_sessions", "kitchen_slip_printed_at")
    op.drop_column("dining_sessions", "customer_slip_printed_at")
