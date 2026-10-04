"""add server-backed POS hold drafts

Revision ID: wp44hold0020
Revises: wp43price0019
Create Date: 2026-09-20 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "wp44hold0020"
down_revision: Union[str, None] = "wp43price0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "branch_settings",
        sa.Column(
            "pos_hold_draft_ttl_minutes",
            sa.Integer(),
            server_default=sa.text("120"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_branch_settings_pos_hold_draft_ttl_range"),
        "branch_settings",
        "pos_hold_draft_ttl_minutes >= 15 AND pos_hold_draft_ttl_minutes <= 1440",
    )

    op.create_table(
        "pos_hold_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("origin_shift_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignee_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("origin_device_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("origin_device_code", sa.String(length=100), nullable=True),
        sa.Column("parent_draft_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("converted_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("draft_no", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("source_type", sa.String(length=40), server_default=sa.text("'walk_in'"), nullable=False),
        sa.Column("table_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("queue_label", sa.String(length=80), nullable=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("customer_display", sa.String(length=160), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("content_json", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("pricing_context", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("pricing_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("last_revalidation", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claimed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claimed_device_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resumed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resumed_device_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'claimed', 'resumed', 'expired', 'converted', 'cancelled')",
            name=op.f("ck_pos_hold_drafts_status"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_pos_hold_drafts_version")),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["cancelled_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["claimed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["converted_order_id"], ["sale_orders.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["stock_locations.id"]),
        sa.ForeignKeyConstraint(["origin_shift_id"], ["cashier_shifts.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["parent_draft_id"], ["pos_hold_drafts.id"]),
        sa.ForeignKeyConstraint(["resumed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "draft_no", name="uq_pos_hold_drafts_number"),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "idempotency_key",
            name="uq_pos_hold_drafts_idempotency",
        ),
    )
    for name, columns in (
        ("ix_pos_hold_drafts_company_id", ["company_id"]),
        ("ix_pos_hold_drafts_brand_id", ["brand_id"]),
        ("ix_pos_hold_drafts_branch_id", ["branch_id"]),
        ("ix_pos_hold_drafts_location_id", ["location_id"]),
        ("ix_pos_hold_drafts_origin_shift_id", ["origin_shift_id"]),
        ("ix_pos_hold_drafts_owner_user_id", ["owner_user_id"]),
        ("ix_pos_hold_drafts_assignee_user_id", ["assignee_user_id"]),
        ("ix_pos_hold_drafts_origin_device_id", ["origin_device_id"]),
        ("ix_pos_hold_drafts_parent_draft_id", ["parent_draft_id"]),
        ("ix_pos_hold_drafts_converted_order_id", ["converted_order_id"]),
        ("ix_pos_hold_drafts_customer_id", ["customer_id"]),
        ("ix_pos_hold_drafts_claim_id", ["claim_id"]),
        ("ix_pos_hold_drafts_branch_status_updated", ["company_id", "branch_id", "status", "updated_at"]),
        ("ix_pos_hold_drafts_owner", ["company_id", "branch_id", "owner_user_id"]),
        ("ix_pos_hold_drafts_expiry", ["status", "expires_at"]),
    ):
        op.create_index(name, "pos_hold_drafts", columns)

    op.create_table(
        "pos_hold_draft_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("draft_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("shift_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("from_version", sa.Integer(), nullable=True),
        sa.Column("to_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSON(astext_type=sa.Text()), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["draft_id"], ["pos_hold_drafts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "action",
            "idempotency_key",
            name="uq_pos_hold_draft_audits_idempotency",
        ),
    )
    for name, columns in (
        ("ix_pos_hold_draft_audits_draft_id", ["draft_id"]),
        ("ix_pos_hold_draft_audits_company_id", ["company_id"]),
        ("ix_pos_hold_draft_audits_branch_id", ["branch_id"]),
        ("ix_pos_hold_draft_audits_actor_user_id", ["actor_user_id"]),
        ("ix_pos_hold_draft_audits_draft", ["draft_id", "created_at"]),
        ("ix_pos_hold_draft_audits_scope", ["company_id", "branch_id", "created_at"]),
    ):
        op.create_index(name, "pos_hold_draft_audits", columns)

    op.execute(
        """
        CREATE FUNCTION prevent_pos_hold_draft_audit_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'pos_hold_draft_audits is append-only' USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_pos_hold_draft_audits_append_only
        BEFORE UPDATE OR DELETE ON pos_hold_draft_audits
        FOR EACH ROW EXECUTE FUNCTION prevent_pos_hold_draft_audit_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_pos_hold_draft_audits_append_only ON pos_hold_draft_audits")
    op.execute("DROP FUNCTION IF EXISTS prevent_pos_hold_draft_audit_mutation()")
    for name in (
        "ix_pos_hold_draft_audits_scope",
        "ix_pos_hold_draft_audits_draft",
        "ix_pos_hold_draft_audits_actor_user_id",
        "ix_pos_hold_draft_audits_branch_id",
        "ix_pos_hold_draft_audits_company_id",
        "ix_pos_hold_draft_audits_draft_id",
    ):
        op.drop_index(name, table_name="pos_hold_draft_audits")
    op.drop_table("pos_hold_draft_audits")
    for name in (
        "ix_pos_hold_drafts_expiry",
        "ix_pos_hold_drafts_owner",
        "ix_pos_hold_drafts_branch_status_updated",
        "ix_pos_hold_drafts_claim_id",
        "ix_pos_hold_drafts_customer_id",
        "ix_pos_hold_drafts_converted_order_id",
        "ix_pos_hold_drafts_parent_draft_id",
        "ix_pos_hold_drafts_origin_device_id",
        "ix_pos_hold_drafts_assignee_user_id",
        "ix_pos_hold_drafts_owner_user_id",
        "ix_pos_hold_drafts_origin_shift_id",
        "ix_pos_hold_drafts_location_id",
        "ix_pos_hold_drafts_branch_id",
        "ix_pos_hold_drafts_brand_id",
        "ix_pos_hold_drafts_company_id",
    ):
        op.drop_index(name, table_name="pos_hold_drafts")
    op.drop_table("pos_hold_drafts")
    op.drop_constraint(op.f("ck_branch_settings_pos_hold_draft_ttl_range"), "branch_settings", type_="check")
    op.drop_column("branch_settings", "pos_hold_draft_ttl_minutes")
