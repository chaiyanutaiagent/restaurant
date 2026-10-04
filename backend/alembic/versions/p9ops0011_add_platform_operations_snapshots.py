"""add sanitized Platform operations snapshots

Revision ID: p9ops0011
Revises: p8member0010
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p9ops0011"
down_revision: Union[str, None] = "p8member0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_operations_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("overall_status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("component_checks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("projector_failed_events", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("projector_loop_errors", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("disk_usage_percent", sa.Integer(), nullable=True),
        sa.Column("backup_status", sa.String(length=20), server_default=sa.text("'unknown'"), nullable=False),
        sa.Column("backup_age_hours", sa.Integer(), nullable=True),
        sa.Column("restore_status", sa.String(length=20), server_default=sa.text("'unknown'"), nullable=False),
        sa.Column("restore_drill_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alert_delivery_status", sa.String(length=30), server_default=sa.text("'unknown'"), nullable=False),
        sa.Column("alert_codes", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("evidence_sha256", sa.String(length=64), nullable=False),
        sa.Column("captured_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("overall_status IN ('ok', 'degraded', 'critical')", name="ck_platform_operations_snapshots_overall_status_valid"),
        sa.CheckConstraint("source IN ('operator_runtime', 'scheduled_runtime', 'resilience_import')", name="ck_platform_operations_snapshots_source_valid"),
        sa.CheckConstraint("backup_status IN ('unknown', 'current', 'stale', 'failed')", name="ck_platform_operations_snapshots_backup_status_valid"),
        sa.CheckConstraint("restore_status IN ('unknown', 'passed', 'stale', 'failed')", name="ck_platform_operations_snapshots_restore_status_valid"),
        sa.CheckConstraint("alert_delivery_status IN ('unknown', 'not_configured', 'healthy', 'failed')", name="ck_platform_operations_snapshots_alert_delivery_status_valid"),
        sa.CheckConstraint("disk_usage_percent IS NULL OR (disk_usage_percent >= 0 AND disk_usage_percent <= 100)", name="ck_platform_operations_snapshots_disk_usage_percent_valid"),
        sa.CheckConstraint("backup_age_hours IS NULL OR backup_age_hours >= 0", name="ck_platform_operations_snapshots_backup_age_hours_valid"),
        sa.ForeignKeyConstraint(["captured_by"], ["platform_operators.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evidence_sha256", name="uq_platform_operations_snapshots_evidence_sha256"),
    )
    op.create_index("ix_platform_operations_captured_at", "platform_operations_snapshots", ["captured_at"])
    op.create_index("ix_platform_operations_status", "platform_operations_snapshots", ["overall_status", "captured_at"])


def downgrade() -> None:
    op.drop_index("ix_platform_operations_status", table_name="platform_operations_snapshots")
    op.drop_index("ix_platform_operations_captured_at", table_name="platform_operations_snapshots")
    op.drop_table("platform_operations_snapshots")
