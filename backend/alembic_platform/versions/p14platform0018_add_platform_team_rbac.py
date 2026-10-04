"""add Platform Team RBAC and operator governance

Revision ID: p14platform0018
Revises: p13platform0017
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p14platform0018"
down_revision: Union[str, None] = "p13platform0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("platform_operators", sa.Column("access_reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("platform_operators", sa.Column("access_review_due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("platform_operators", sa.Column("access_reviewed_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("platform_operators", sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("platform_operators", sa.Column("deactivated_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("platform_operators", sa.Column("deactivation_reason", sa.Text(), nullable=True))
    op.create_foreign_key("fk_platform_operators_access_reviewed_by_platform_operators", "platform_operators", "platform_operators", ["access_reviewed_by"], ["id"])
    op.create_foreign_key("fk_platform_operators_deactivated_by_platform_operators", "platform_operators", "platform_operators", ["deactivated_by"], ["id"])

    op.create_table(
        "platform_operator_role_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_code", sa.String(length=40), nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role_code IN ('platform_owner', 'operations', 'support', 'billing', 'security', 'auditor')", name="ck_platform_operator_role_assignments_role_code_valid"),
        sa.CheckConstraint("environment IN ('uat', 'production')", name="ck_platform_operator_role_assignments_environment_valid"),
        sa.ForeignKeyConstraint(["assigned_by"], ["platform_operators.id"]),
        sa.ForeignKeyConstraint(["operator_id"], ["platform_operators.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revoked_by"], ["platform_operators.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", name="uq_platform_operator_role_assignments_request_id"),
    )
    op.create_index("uq_platform_operator_role_assignments_active", "platform_operator_role_assignments", ["operator_id", "environment", "role_code"], unique=True, postgresql_where=sa.text("revoked_at IS NULL"))
    op.create_index("ix_platform_operator_roles_environment_active", "platform_operator_role_assignments", ["environment", "revoked_at"])

    op.create_table(
        "platform_operator_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("role_code", sa.String(length=40), nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_operator_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role_code IN ('platform_owner', 'operations', 'support', 'billing', 'security', 'auditor')", name="ck_platform_operator_invitations_role_code_valid"),
        sa.CheckConstraint("environment IN ('uat', 'production')", name="ck_platform_operator_invitations_environment_valid"),
        sa.ForeignKeyConstraint(["accepted_operator_id"], ["platform_operators.id"]),
        sa.ForeignKeyConstraint(["invited_by"], ["platform_operators.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", name="uq_platform_operator_invitations_request_id"),
        sa.UniqueConstraint("token_hash", name="uq_platform_operator_invitations_token_hash"),
    )
    op.create_index("ix_platform_operator_invitations_email", "platform_operator_invitations", ["email"])
    op.create_index("ix_platform_operator_invitations_expires", "platform_operator_invitations", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_platform_operator_invitations_expires", table_name="platform_operator_invitations")
    op.drop_index("ix_platform_operator_invitations_email", table_name="platform_operator_invitations")
    op.drop_table("platform_operator_invitations")
    op.drop_index("ix_platform_operator_roles_environment_active", table_name="platform_operator_role_assignments")
    op.drop_index("uq_platform_operator_role_assignments_active", table_name="platform_operator_role_assignments")
    op.drop_table("platform_operator_role_assignments")
    op.drop_constraint("fk_platform_operators_deactivated_by_platform_operators", "platform_operators", type_="foreignkey")
    op.drop_constraint("fk_platform_operators_access_reviewed_by_platform_operators", "platform_operators", type_="foreignkey")
    op.drop_column("platform_operators", "deactivation_reason")
    op.drop_column("platform_operators", "deactivated_by")
    op.drop_column("platform_operators", "deactivated_at")
    op.drop_column("platform_operators", "access_reviewed_by")
    op.drop_column("platform_operators", "access_review_due_at")
    op.drop_column("platform_operators", "access_reviewed_at")
