"""add manager approval sessions and operational limits

Revision ID: p2approval0002
Revises: p2scope0001
Create Date: 2026-08-01 09:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p2approval0002"
down_revision: Union[str, None] = "p2scope0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SUPPORTED_ACTIONS = (
    "pos.discount.override",
    "pos.sale.void",
    "pos.refund.create",
    "inventory.stock.adjust",
)


def _create_manager_pin_credentials() -> None:
    op.create_table(
        "manager_pin_credentials",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pin_hash", sa.String(length=255), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pin_set_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "failed_attempts >= 0",
            name=op.f("ck_manager_pin_credentials_failed_attempts_nonnegative"),
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_manager_pin_credentials_user_id"),
    )
    op.create_index(
        "ix_manager_pin_credentials_company_id",
        "manager_pin_credentials",
        ["company_id"],
    )


def _create_approval_grant_usages() -> None:
    actions_sql = ", ".join(f"'{action}'" for action in SUPPORTED_ACTIONS)
    op.create_table(
        "approval_grant_usages",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approver_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=True),
        sa.Column("resource_id", sa.String(length=100), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "consumed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            f"action IN ({actions_sql})",
            name=op.f("ck_approval_grant_usages_supported_action"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("grant_id", name="uq_approval_grant_usages_grant_id"),
    )
    op.create_index(
        "ix_approval_grant_usages_company_branch_consumed",
        "approval_grant_usages",
        ["company_id", "branch_id", "consumed_at"],
    )


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("original_payment_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_payments_original_payment_id_payments",
        "payments",
        "payments",
        ["original_payment_id"],
        ["id"],
    )
    op.create_index(
        "ix_payments_original_payment_id",
        "payments",
        ["original_payment_id"],
    )
    op.execute(
        "UPDATE branch_settings "
        "SET pos_max_discount_pct = GREATEST(0, LEAST(100, pos_max_discount_pct))"
    )
    op.add_column(
        "branch_settings",
        sa.Column(
            "pos_cashier_discount_limit_pct",
            sa.Numeric(precision=5, scale=2),
            server_default=sa.text("10"),
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE branch_settings "
        "SET pos_cashier_discount_limit_pct = LEAST(10, pos_max_discount_pct)"
    )
    op.add_column(
        "branch_settings",
        sa.Column(
            "stock_adjust_approval_threshold_qty",
            sa.Numeric(precision=12, scale=4),
            server_default=sa.text("10"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_branch_settings_pos_max_discount_range"),
        "branch_settings",
        "pos_max_discount_pct >= 0 AND pos_max_discount_pct <= 100",
    )
    op.create_check_constraint(
        op.f("ck_branch_settings_pos_cashier_discount_limit_range"),
        "branch_settings",
        "pos_cashier_discount_limit_pct >= 0 AND pos_cashier_discount_limit_pct <= 100",
    )
    op.create_check_constraint(
        op.f("ck_branch_settings_pos_cashier_discount_limit_within_max"),
        "branch_settings",
        "pos_cashier_discount_limit_pct <= pos_max_discount_pct",
    )
    op.create_check_constraint(
        op.f("ck_branch_settings_stock_adjust_approval_threshold_nonnegative"),
        "branch_settings",
        "stock_adjust_approval_threshold_qty >= 0",
    )
    _create_manager_pin_credentials()
    _create_approval_grant_usages()


def downgrade() -> None:
    op.drop_index(
        "ix_approval_grant_usages_company_branch_consumed",
        table_name="approval_grant_usages",
    )
    op.drop_table("approval_grant_usages")
    op.drop_index(
        "ix_manager_pin_credentials_company_id",
        table_name="manager_pin_credentials",
    )
    op.drop_table("manager_pin_credentials")
    op.drop_constraint(
        op.f("ck_branch_settings_stock_adjust_approval_threshold_nonnegative"),
        "branch_settings",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_branch_settings_pos_cashier_discount_limit_range"),
        "branch_settings",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_branch_settings_pos_cashier_discount_limit_within_max"),
        "branch_settings",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_branch_settings_pos_max_discount_range"),
        "branch_settings",
        type_="check",
    )
    op.drop_column("branch_settings", "stock_adjust_approval_threshold_qty")
    op.drop_column("branch_settings", "pos_cashier_discount_limit_pct")
    op.drop_index("ix_payments_original_payment_id", table_name="payments")
    op.drop_constraint(
        "fk_payments_original_payment_id_payments",
        "payments",
        type_="foreignkey",
    )
    op.drop_column("payments", "original_payment_id")
