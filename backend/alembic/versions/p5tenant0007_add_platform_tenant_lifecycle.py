"""add Phase 5 Platform tenant lifecycle

Revision ID: p5tenant0007
Revises: p4feature0006
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p5tenant0007"
down_revision: Union[str, None] = "p4feature0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("credential_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.create_check_constraint(
        "ck_companies_company_credential_version_positive",
        "companies",
        "credential_version > 0",
    )
    op.create_table(
        "platform_operators",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("credential_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("failed_login_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "credential_version > 0",
            name="ck_platform_operators_credential_version_positive",
        ),
        sa.CheckConstraint(
            "failed_login_attempts >= 0",
            name="ck_platform_operators_failed_attempts_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_platform_operators_active", "platform_operators", ["is_active"])
    op.create_table(
        "platform_tenant_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_code", sa.String(length=50), server_default=sa.text("'starter'"), nullable=False),
        sa.Column("feature_flags", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("plan_limits", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("suspension_reason", sa.Text(), nullable=True),
        sa.Column("reactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reactivated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reactivation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["platform_operators.id"]),
        sa.ForeignKeyConstraint(["suspended_by"], ["platform_operators.id"]),
        sa.ForeignKeyConstraint(["reactivated_by"], ["platform_operators.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id"),
    )
    op.create_index("ix_platform_tenant_profiles_plan_code", "platform_tenant_profiles", ["plan_code"])
    op.create_index("ix_platform_tenant_profiles_suspended_at", "platform_tenant_profiles", ["suspended_at"])


def downgrade() -> None:
    op.drop_table("platform_tenant_profiles")
    op.drop_table("platform_operators")
    op.drop_constraint(
        "ck_companies_company_credential_version_positive",
        "companies",
        type_="check",
    )
    op.drop_column("companies", "credential_version")
