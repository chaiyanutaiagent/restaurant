"""add WP50 cashier shift operations contract

Revision ID: wp50shift0024
Revises: wp47offline0023
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "wp50shift0024"
down_revision: Union[str, None] = "wp47offline0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_approval_grant_usages_supported_action"), "approval_grant_usages", type_="check")
    op.create_check_constraint(
        op.f("ck_approval_grant_usages_supported_action"),
        "approval_grant_usages",
        "action IN ('pos.discount.override','pos.price.override','pos.sale.void','pos.refund.create','inventory.stock.adjust','fb.order.cancel_after_kitchen','fb.order.cancel.reopen','pos.cash_movement.approve','pos.shift.variance.approve')",
    )
    op.add_column("cashier_shifts", sa.Column("shift_type", sa.String(length=30), nullable=False, server_default=sa.text("'staff_cashier'")))
    op.add_column("cashier_shifts", sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")))
    op.add_column("cashier_shifts", sa.Column("open_idempotency_key", sa.String(length=100), nullable=True))
    op.add_column("cashier_shifts", sa.Column("open_request_hash", sa.String(length=64), nullable=True))
    op.add_column("cashier_shifts", sa.Column("close_idempotency_key", sa.String(length=100), nullable=True))
    op.add_column("cashier_shifts", sa.Column("close_request_hash", sa.String(length=64), nullable=True))
    op.add_column("cashier_shifts", sa.Column("close_reason_code", sa.String(length=40), nullable=True))
    op.add_column("cashier_shifts", sa.Column("cash_count_json", postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column("cashier_shifts", sa.Column("opened_device_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("cashier_shifts", sa.Column("opened_device_code", sa.String(length=100), nullable=True))
    op.add_column("cashier_shifts", sa.Column("closed_device_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("cashier_shifts", sa.Column("closed_device_code", sa.String(length=100), nullable=True))
    op.add_column("cashier_shifts", sa.Column("closed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("cashier_shifts", sa.Column("approval_evidence", postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column("cashier_shifts", sa.Column("close_snapshot_json", postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.create_foreign_key(op.f("fk_cashier_shifts_closed_by_user_id_users"), "cashier_shifts", "users", ["closed_by_user_id"], ["id"])
    op.create_check_constraint(op.f("ck_cashier_shifts_cashier_shift_type_supported"), "cashier_shifts", "shift_type IN ('staff_cashier', 'operational_cashless')")
    op.create_check_constraint(op.f("ck_cashier_shifts_cashier_shift_version_positive"), "cashier_shifts", "version >= 1")
    op.create_index(
        "uq_cashier_shifts_open_idempotency",
        "cashier_shifts",
        ["company_id", "branch_id", "open_idempotency_key"],
        unique=True,
        postgresql_where=sa.text("open_idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "uq_cashier_shifts_close_idempotency",
        "cashier_shifts",
        ["company_id", "branch_id", "close_idempotency_key"],
        unique=True,
        postgresql_where=sa.text("close_idempotency_key IS NOT NULL"),
    )

    op.add_column("branch_settings", sa.Column("pos_cash_movement_approval_threshold", sa.Numeric(15, 2), nullable=False, server_default=sa.text("1000")))
    op.add_column("branch_settings", sa.Column("pos_shift_variance_soft_threshold", sa.Numeric(15, 2), nullable=False, server_default=sa.text("100")))
    op.add_column("branch_settings", sa.Column("pos_shift_variance_approval_threshold", sa.Numeric(15, 2), nullable=False, server_default=sa.text("500")))
    op.create_check_constraint(op.f("ck_branch_settings_pos_cash_movement_approval_threshold_nonnegative"), "branch_settings", "pos_cash_movement_approval_threshold >= 0")
    op.create_check_constraint(op.f("ck_branch_settings_pos_shift_variance_thresholds_nonnegative"), "branch_settings", "pos_shift_variance_soft_threshold >= 0 AND pos_shift_variance_approval_threshold >= pos_shift_variance_soft_threshold")

    op.create_table(
        "pos_cash_movements",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shift_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approver_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("device_code", sa.String(length=100), nullable=True),
        sa.Column("movement_type", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("reason_code", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'posted'")),
        sa.Column("shift_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("approval_evidence", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("journal_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("movement_type IN ('cash_in', 'cash_out')", name=op.f("ck_pos_cash_movements_cash_movement_type_supported")),
        sa.CheckConstraint("amount > 0", name=op.f("ck_pos_cash_movements_cash_movement_amount_positive")),
        sa.CheckConstraint("status = 'posted'", name=op.f("ck_pos_cash_movements_cash_movement_status_supported")),
        sa.CheckConstraint("shift_version >= 1", name=op.f("ck_pos_cash_movements_cash_movement_shift_version_positive")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_pos_cash_movements_branch_id_branches")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_pos_cash_movements_company_id_companies")),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"], name=op.f("fk_pos_cash_movements_journal_entry_id_journal_entries")),
        sa.ForeignKeyConstraint(["location_id"], ["stock_locations.id"], name=op.f("fk_pos_cash_movements_location_id_stock_locations")),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"], name=op.f("fk_pos_cash_movements_requester_id_users")),
        sa.ForeignKeyConstraint(["approver_id"], ["users.id"], name=op.f("fk_pos_cash_movements_approver_id_users")),
        sa.ForeignKeyConstraint(["shift_id"], ["cashier_shifts.id"], name=op.f("fk_pos_cash_movements_shift_id_cashier_shifts")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pos_cash_movements")),
        sa.UniqueConstraint("company_id", "branch_id", "idempotency_key", name="uq_pos_cash_movements_idempotency"),
    )
    op.create_index("ix_pos_cash_movements_shift_posted", "pos_cash_movements", ["shift_id", "posted_at"], unique=False)
    op.create_index(op.f("ix_pos_cash_movements_company_id"), "pos_cash_movements", ["company_id"], unique=False)
    op.create_index(op.f("ix_pos_cash_movements_branch_id"), "pos_cash_movements", ["branch_id"], unique=False)
    op.create_index(op.f("ix_pos_cash_movements_shift_id"), "pos_cash_movements", ["shift_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_pos_cash_movements_shift_id"), table_name="pos_cash_movements")
    op.drop_index(op.f("ix_pos_cash_movements_branch_id"), table_name="pos_cash_movements")
    op.drop_index(op.f("ix_pos_cash_movements_company_id"), table_name="pos_cash_movements")
    op.drop_index("ix_pos_cash_movements_shift_posted", table_name="pos_cash_movements")
    op.drop_table("pos_cash_movements")
    op.drop_constraint(op.f("ck_branch_settings_pos_shift_variance_thresholds_nonnegative"), "branch_settings", type_="check")
    op.drop_constraint(op.f("ck_branch_settings_pos_cash_movement_approval_threshold_nonnegative"), "branch_settings", type_="check")
    op.drop_column("branch_settings", "pos_shift_variance_approval_threshold")
    op.drop_column("branch_settings", "pos_shift_variance_soft_threshold")
    op.drop_column("branch_settings", "pos_cash_movement_approval_threshold")
    op.drop_index("uq_cashier_shifts_close_idempotency", table_name="cashier_shifts")
    op.drop_index("uq_cashier_shifts_open_idempotency", table_name="cashier_shifts")
    op.drop_constraint(op.f("ck_cashier_shifts_cashier_shift_version_positive"), "cashier_shifts", type_="check")
    op.drop_constraint(op.f("ck_cashier_shifts_cashier_shift_type_supported"), "cashier_shifts", type_="check")
    op.drop_constraint(op.f("fk_cashier_shifts_closed_by_user_id_users"), "cashier_shifts", type_="foreignkey")
    for column in (
        "close_snapshot_json", "approval_evidence", "closed_by_user_id", "closed_device_code", "closed_device_id",
        "opened_device_code", "opened_device_id", "cash_count_json", "close_reason_code",
        "close_request_hash", "close_idempotency_key", "open_request_hash", "open_idempotency_key",
        "version", "shift_type",
    ):
        op.drop_column("cashier_shifts", column)
    op.drop_constraint(op.f("ck_approval_grant_usages_supported_action"), "approval_grant_usages", type_="check")
    op.create_check_constraint(
        op.f("ck_approval_grant_usages_supported_action"),
        "approval_grant_usages",
        "action IN ('pos.discount.override','pos.price.override','pos.sale.void','pos.refund.create','inventory.stock.adjust','fb.order.cancel_after_kitchen','fb.order.cancel.reopen')",
    )
