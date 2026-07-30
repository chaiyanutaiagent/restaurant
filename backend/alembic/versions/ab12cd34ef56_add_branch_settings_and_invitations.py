"""add_branch_settings_and_invitations

Revision ID: ab12cd34ef56
Revises: f1a2b3c4d5e6
Create Date: 2026-05-14 08:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ab12cd34ef56"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "branch_settings",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("pos_receipt_header", sa.Text(), nullable=True),
        sa.Column("pos_receipt_footer", sa.Text(), nullable=True),
        sa.Column("pos_require_customer", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("pos_allow_discount", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("pos_max_discount_pct", sa.Numeric(5, 2), server_default=sa.text("100"), nullable=False),
        sa.Column("pos_default_price_list_id", sa.UUID(), nullable=True),
        sa.Column("promptpay_target", sa.String(length=20), nullable=True),
        sa.Column("promptpay_name", sa.String(length=255), nullable=True),
        sa.Column("working_hours", sa.JSON(), nullable=True),
        sa.Column("allow_negative_stock", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("low_stock_alert_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("receipt_show_tax_id", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("receipt_show_logo", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("receipt_copies", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("notify_low_stock_email", sa.String(length=255), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_branch_settings_branch_id_branches")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_branch_settings_company_id_companies")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_branch_settings")),
        sa.UniqueConstraint("branch_id", name=op.f("uq_branch_settings_branch_id")),
    )
    op.create_index(op.f("ix_branch_settings_company_id"), "branch_settings", ["company_id"], unique=False)

    op.create_table(
        "user_invitations",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("invited_by", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("otp_code", sa.String(length=8), nullable=False),
        sa.Column("otp_hash", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_user_invitations_branch_id_branches")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_user_invitations_company_id_companies")),
        sa.ForeignKeyConstraint(["created_user_id"], ["users.id"], name=op.f("fk_user_invitations_created_user_id_users")),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], name=op.f("fk_user_invitations_invited_by_users")),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name=op.f("fk_user_invitations_role_id_roles")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_invitations")),
    )
    op.create_index(op.f("ix_user_invitations_company_id"), "user_invitations", ["company_id"], unique=False)
    op.create_index(
        "ix_user_invitations_company_id_otp_hash",
        "user_invitations",
        ["company_id", "otp_hash"],
        unique=False,
    )
    op.create_index("ix_user_invitations_expires_at", "user_invitations", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_invitations_expires_at", table_name="user_invitations")
    op.drop_index("ix_user_invitations_company_id_otp_hash", table_name="user_invitations")
    op.drop_index(op.f("ix_user_invitations_company_id"), table_name="user_invitations")
    op.drop_table("user_invitations")
    op.drop_index(op.f("ix_branch_settings_company_id"), table_name="branch_settings")
    op.drop_table("branch_settings")
