"""record control plane snapshot rehearsal

Revision ID: p1platform0002
Revises: p1platform0001
Create Date: 2026-08-01 01:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p1platform0002"
down_revision: Union[str, None] = "p1platform0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "database_cutover_metadata",
        sa.Column("scope_id", sa.String(length=60), primary_key=True),
        sa.Column("source_database", sa.String(length=80), nullable=False),
        sa.Column("source_migration_head", sa.String(length=80), nullable=False),
        sa.Column("snapshot_role", sa.String(length=80), nullable=False),
        sa.Column("is_system_of_record", sa.Boolean(), nullable=False),
        sa.Column(
            "snapshot_recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.execute(
        "INSERT INTO database_cutover_metadata "
        "(scope_id, source_database, source_migration_head, snapshot_role, is_system_of_record) "
        "VALUES ('P1-DATA-CUTOVER-04', 'restaurant_pos_db', '6b7c8d9e0f12', "
        "'control_plane_snapshot', false)"
    )


def downgrade() -> None:
    op.drop_table("database_cutover_metadata")
