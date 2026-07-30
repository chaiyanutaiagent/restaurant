"""add_fb_settings

Revision ID: e1f2a3b4c5d6
Revises: ab12cd34ef56
Create Date: 2026-05-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "ab12cd34ef56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("branch_settings", sa.Column("fb_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("branch_settings", sa.Column("fb_service_mode", sa.String(20), nullable=False, server_default=sa.text("'quick_service'")))
    op.add_column("branch_settings", sa.Column("fb_table_qr_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("branch_settings", sa.Column("fb_bill_at_table", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("branch_settings", sa.Column("fb_queue_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("branch_settings", sa.Column("fb_queue_reset", sa.String(20), nullable=False, server_default=sa.text("'daily'")))
    op.add_column("branch_settings", sa.Column("fb_queue_prefix", sa.String(10), nullable=False, server_default=sa.text("''")))
    op.add_column("branch_settings", sa.Column("fb_pickup_display_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("branch_settings", sa.Column("fb_line_notify_token", sa.String(255), nullable=True))
    op.add_column("branch_settings", sa.Column("fb_line_mode", sa.String(20), nullable=False, server_default=sa.text("'group'")))
    op.add_column("branch_settings", sa.Column("fb_kitchen_stations", sa.JSON(), nullable=True))
    op.add_column("branch_settings", sa.Column("fb_setup_completed", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("branch_settings", "fb_setup_completed")
    op.drop_column("branch_settings", "fb_kitchen_stations")
    op.drop_column("branch_settings", "fb_line_mode")
    op.drop_column("branch_settings", "fb_line_notify_token")
    op.drop_column("branch_settings", "fb_pickup_display_enabled")
    op.drop_column("branch_settings", "fb_queue_prefix")
    op.drop_column("branch_settings", "fb_queue_reset")
    op.drop_column("branch_settings", "fb_queue_enabled")
    op.drop_column("branch_settings", "fb_bill_at_table")
    op.drop_column("branch_settings", "fb_table_qr_enabled")
    op.drop_column("branch_settings", "fb_service_mode")
    op.drop_column("branch_settings", "fb_enabled")
