"""add immutable Takeaway cutover runs

Revision ID: p6takeaway0007
Revises: p6takeaway0006
Create Date: 2026-09-17 14:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p6takeaway0007"
down_revision: Union[str, None] = "p6takeaway0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "takeaway_cutover_runs",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("brand_id", sa.UUID(), nullable=False),
        sa.Column("batch_id", sa.UUID(), nullable=True),
        sa.Column("execution_key", sa.String(180), nullable=False),
        sa.Column("export_id", sa.UUID(), nullable=False),
        sa.Column("source_snapshot", sa.String(200), nullable=False),
        sa.Column("manifest_digest", sa.String(64), nullable=False),
        sa.Column("mapping_digest", sa.String(64), nullable=False),
        sa.Column("preview_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("approved_by", sa.UUID(), nullable=False),
        sa.Column("approval_reference", sa.String(300), nullable=False),
        sa.Column("backup_reference", sa.String(500), nullable=False),
        sa.Column("rollback_reference", sa.String(500), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reconciliation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rollback_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('completed', 'failed', 'rollback_requested', 'rolled_back')",
            name="ck_takeaway_cutover_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "execution_key", name="uq_takeaway_cutover_execution_key"),
    )
    op.create_index("ix_takeaway_cutover_runs_batch_id", "takeaway_cutover_runs", ["batch_id"])
    op.create_index("ix_takeaway_cutover_scope", "takeaway_cutover_runs", ["company_id", "brand_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_takeaway_cutover_scope", table_name="takeaway_cutover_runs")
    op.drop_index("ix_takeaway_cutover_runs_batch_id", table_name="takeaway_cutover_runs")
    op.drop_table("takeaway_cutover_runs")
