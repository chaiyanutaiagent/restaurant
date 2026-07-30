"""add user access request approval workflow

Revision ID: d17e5a91c204
Revises: cc45dd67ee89
Create Date: 2026-07-21 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d17e5a91c204"
down_revision: Union[str, None] = "cc45dd67ee89"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "roles",
        sa.Column("is_branch_assignable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    op.create_table(
        "user_access_requests",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("requested_role_id", sa.UUID(), nullable=False),
        sa.Column("approved_role_id", sa.UUID(), nullable=True),
        sa.Column("employee_id", sa.UUID(), nullable=True),
        sa.Column("employee_code", sa.String(length=20), nullable=True),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("request_note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("activated_user_id", sa.UUID(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'activated', 'rejected', 'cancelled')",
            name="ck_user_access_requests_status",
        ),
        sa.ForeignKeyConstraint(["activated_user_id"], ["users.id"], name=op.f("fk_user_access_requests_activated_user_id_users")),
        sa.ForeignKeyConstraint(["approved_role_id"], ["roles.id"], name=op.f("fk_user_access_requests_approved_role_id_roles")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_user_access_requests_branch_id_branches")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_user_access_requests_company_id_companies")),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], name=op.f("fk_user_access_requests_employee_id_employees")),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], name=op.f("fk_user_access_requests_requested_by_users")),
        sa.ForeignKeyConstraint(["requested_role_id"], ["roles.id"], name=op.f("fk_user_access_requests_requested_role_id_roles")),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], name=op.f("fk_user_access_requests_reviewed_by_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_access_requests")),
    )
    op.create_index(op.f("ix_user_access_requests_company_id"), "user_access_requests", ["company_id"], unique=False)
    op.create_index(op.f("ix_user_access_requests_branch_id"), "user_access_requests", ["branch_id"], unique=False)
    op.create_index(
        "ix_user_access_requests_company_status_created",
        "user_access_requests",
        ["company_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_user_access_requests_company_branch_status",
        "user_access_requests",
        ["company_id", "branch_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_user_access_requests_employee_open_unique",
        "user_access_requests",
        ["employee_id"],
        unique=True,
        postgresql_where=sa.text("employee_id IS NOT NULL AND status IN ('pending', 'approved')"),
    )

    op.add_column("user_invitations", sa.Column("access_request_id", sa.UUID(), nullable=True))
    op.add_column("user_invitations", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        op.f("fk_user_invitations_access_request_id_user_access_requests"),
        "user_invitations",
        "user_access_requests",
        ["access_request_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_user_invitations_access_request_id"),
        "user_invitations",
        ["access_request_id"],
        unique=False,
    )
    op.alter_column("user_invitations", "otp_code", existing_type=sa.String(length=8), nullable=True)

    op.execute(
        sa.text(
            "UPDATE roles SET is_branch_assignable = true "
            "WHERE name = 'store_cashier' AND deleted_at IS NULL"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE user_invitations SET used_at = COALESCE(used_at, now()) "
            "WHERE access_request_id IS NOT NULL"
        )
    )
    op.execute(sa.text("UPDATE user_invitations SET otp_code = 'REVOKED' WHERE otp_code IS NULL"))
    op.alter_column("user_invitations", "otp_code", existing_type=sa.String(length=8), nullable=False)
    op.drop_index(op.f("ix_user_invitations_access_request_id"), table_name="user_invitations")
    op.drop_constraint(
        op.f("fk_user_invitations_access_request_id_user_access_requests"),
        "user_invitations",
        type_="foreignkey",
    )
    op.drop_column("user_invitations", "revoked_at")
    op.drop_column("user_invitations", "access_request_id")

    op.drop_index("ix_user_access_requests_employee_open_unique", table_name="user_access_requests")
    op.drop_index("ix_user_access_requests_company_branch_status", table_name="user_access_requests")
    op.drop_index("ix_user_access_requests_company_status_created", table_name="user_access_requests")
    op.drop_index(op.f("ix_user_access_requests_branch_id"), table_name="user_access_requests")
    op.drop_index(op.f("ix_user_access_requests_company_id"), table_name="user_access_requests")
    op.drop_table("user_access_requests")
    op.drop_column("roles", "is_branch_assignable")
