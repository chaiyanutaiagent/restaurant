"""add bounded offline sync receipts and physical UAT evidence

Revision ID: wp47offline0023
Revises: wp46refund0022
Create Date: 2026-09-21 00:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "wp47offline0023"
down_revision: Union[str, None] = "wp46refund0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _append_only(table_name: str) -> None:
    function_name = f"prevent_{table_name}_mutation"
    op.execute(f"""
        CREATE FUNCTION {function_name}() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION '{table_name} is append-only' USING ERRCODE = '55000'; END; $$
    """)
    op.execute(f"""
        CREATE TRIGGER trg_{table_name}_append_only BEFORE UPDATE OR DELETE ON {table_name}
        FOR EACH ROW EXECUTE FUNCTION {function_name}()
    """)


def upgrade() -> None:
    op.create_table(
        "offline_pos_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shift_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sale_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("operation_type", sa.String(30), nullable=False),
        sa.Column("client_operation_id", sa.String(100), nullable=False),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("server_request_hash", sa.String(64), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("station_key", sa.String(100), nullable=False),
        sa.Column("price_snapshot_version", sa.String(120), nullable=False),
        sa.Column("created_at_device", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(30), server_default=sa.text("'pending_sync'"), nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("schema_version = 'offline-pos-v1'", name="ck_offline_pos_operations_schema"),
        sa.CheckConstraint("operation_type IN ('cash_sale','hold_draft')", name="ck_offline_pos_operations_type"),
        sa.CheckConstraint("sequence_no > 0", name="ck_offline_pos_operations_sequence"),
        sa.CheckConstraint("status IN ('pending_sync','syncing','server_acknowledged','reconciled','needs_review','rejected','quarantined','unknown','purged')", name="ck_offline_pos_operations_status"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["shift_id"], ["cashier_shifts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["sale_order_id"], ["sale_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "branch_id", "client_operation_id", name="uq_offline_pos_operations_client_operation"),
        sa.UniqueConstraint("company_id", "branch_id", "idempotency_key", name="uq_offline_pos_operations_idempotency"),
        sa.UniqueConstraint("company_id", "branch_id", "device_id", "shift_id", "sequence_no", name="uq_offline_pos_operations_device_sequence"),
    )
    for name, columns in (
        ("ix_offline_pos_operations_company_id", ["company_id"]),
        ("ix_offline_pos_operations_brand_id", ["brand_id"]),
        ("ix_offline_pos_operations_branch_id", ["branch_id"]),
        ("ix_offline_pos_operations_device_id", ["device_id"]),
        ("ix_offline_pos_operations_shift_id", ["shift_id"]),
        ("ix_offline_pos_operations_user_id", ["user_id"]),
        ("ix_offline_pos_operations_sale_order_id", ["sale_order_id"]),
        ("ix_offline_pos_operations_status", ["status"]),
        ("ix_offline_pos_operations_scope_status", ["company_id", "branch_id", "status", "created_at"]),
    ):
        op.create_index(name, "offline_pos_operations", columns)

    op.create_table(
        "offline_pos_operation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_key", sa.String(180), nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("from_state", sa.String(30), nullable=True),
        sa.Column("to_state", sa.String(30), nullable=False),
        sa.Column("evidence", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["operation_id"], ["offline_pos_operations.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_id", "event_key", name="uq_offline_pos_operation_events_key"),
    )
    op.create_index("ix_offline_pos_operation_events_operation_id", "offline_pos_operation_events", ["operation_id"])
    op.create_index("ix_offline_pos_operation_events_company_id", "offline_pos_operation_events", ["company_id"])
    op.create_index("ix_offline_pos_operation_events_branch_id", "offline_pos_operation_events", ["branch_id"])

    op.create_table(
        "physical_uat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("release_commit", sa.String(64), nullable=False),
        sa.Column("environment", sa.String(20), server_default=sa.text("'uat'"), nullable=False),
        sa.Column("status", sa.String(30), server_default=sa.text("'in_progress'"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("technical_approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("technical_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("business_approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("business_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("device_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("environment_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("environment = 'uat'", name="ck_physical_uat_sessions_environment"),
        sa.CheckConstraint("status IN ('in_progress','not_ready','ready_for_signoff','uat_approved')", name="ck_physical_uat_sessions_status"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["technical_approved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["business_approved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_physical_uat_sessions_company_id", ["company_id"]),
        ("ix_physical_uat_sessions_branch_id", ["branch_id"]),
        ("ix_physical_uat_sessions_device_id", ["device_id"]),
        ("ix_physical_uat_sessions_release_commit", ["release_commit"]),
        ("ix_physical_uat_sessions_status", ["status"]),
    ):
        op.create_index(name, "physical_uat_sessions", columns)

    op.create_table(
        "physical_uat_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("check_key", sa.String(80), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("required", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("result", sa.String(20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence_reference", sa.String(500), nullable=True),
        sa.Column("defect_id", sa.String(100), nullable=True),
        sa.Column("defect_severity", sa.String(10), nullable=True),
        sa.Column("tested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("source IN ('automatic','manual')", name="ck_physical_uat_checks_source"),
        sa.CheckConstraint("result IN ('pending','pass','fail','na')", name="ck_physical_uat_checks_result"),
        sa.CheckConstraint("defect_severity IS NULL OR defect_severity IN ('P0','P1','P2','P3')", name="ck_physical_uat_checks_defect_severity"),
        sa.ForeignKeyConstraint(["session_id"], ["physical_uat_sessions.id"]),
        sa.ForeignKeyConstraint(["tested_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "check_key", name="uq_physical_uat_checks_session_key"),
    )
    op.create_index("ix_physical_uat_checks_session_id", "physical_uat_checks", ["session_id"])

    op.create_table(
        "physical_uat_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_key", sa.String(180), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("evidence", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["physical_uat_sessions.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "event_key", name="uq_physical_uat_audits_event_key"),
    )
    op.create_index("ix_physical_uat_audits_session_id", "physical_uat_audits", ["session_id"])
    op.create_index("ix_physical_uat_audits_company_id", "physical_uat_audits", ["company_id"])
    op.create_index("ix_physical_uat_audits_branch_id", "physical_uat_audits", ["branch_id"])

    _append_only("offline_pos_operation_events")
    _append_only("physical_uat_audits")


def downgrade() -> None:
    for table_name in ("physical_uat_audits", "offline_pos_operation_events"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name}")
        op.execute(f"DROP FUNCTION IF EXISTS prevent_{table_name}_mutation()")
    op.drop_table("physical_uat_audits")
    op.drop_table("physical_uat_checks")
    op.drop_table("physical_uat_sessions")
    op.drop_table("offline_pos_operation_events")
    op.drop_table("offline_pos_operations")
