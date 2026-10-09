"""add Platform custom roles

Revision ID: p16platform0020
Revises: p15platform0019
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p16platform0020"
down_revision: Union[str, None] = "p15platform0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_platform_operator_role_assignments_role_code_valid",
        "platform_operator_role_assignments",
        type_="check",
    )
    op.drop_constraint(
        "ck_platform_operator_invitations_role_code_valid",
        "platform_operator_invitations",
        type_="check",
    )
    op.create_table(
        "platform_custom_roles",
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("permissions", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "environment IN ('uat', 'production')",
            name="ck_platform_custom_roles_environment_valid",
        ),
        sa.CheckConstraint("version > 0", name="ck_platform_custom_roles_version_positive"),
        sa.ForeignKeyConstraint(
            ["created_by"], ["platform_operators.id"], name="fk_platform_custom_roles_created_by_platform_operators"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["platform_operators.id"], name="fk_platform_custom_roles_updated_by_platform_operators"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_platform_custom_roles"),
        sa.UniqueConstraint(
            "environment", "code", name="uq_platform_custom_roles_environment_code"
        ),
    )
    op.create_index(
        "ix_platform_custom_roles_environment_active",
        "platform_custom_roles",
        ["environment", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_platform_custom_roles_environment_active", table_name="platform_custom_roles")
    op.drop_table("platform_custom_roles")
    op.create_check_constraint(
        "ck_platform_operator_invitations_role_code_valid",
        "platform_operator_invitations",
        "role_code IN ('platform_owner', 'operations', 'support', 'billing', 'security', 'auditor')",
    )
    op.create_check_constraint(
        "ck_platform_operator_role_assignments_role_code_valid",
        "platform_operator_role_assignments",
        "role_code IN ('platform_owner', 'operations', 'support', 'billing', 'security', 'auditor')",
    )
