"""add public SaaS Tenant membership lifecycle

Revision ID: p8platform0012
Revises: p7platform0011
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p8platform0012"
down_revision: Union[str, None] = "p7platform0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("platform_tenant_profiles", "created_by", nullable=True)
    op.create_table(
        "saas_tenant_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_email", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), server_default=sa.text("'pending_verification'"), nullable=False),
        sa.Column("onboarding_state", sa.String(length=30), server_default=sa.text("'awaiting_verification'"), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terms_version", sa.String(length=50), nullable=False),
        sa.Column("privacy_version", sa.String(length=50), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending_verification', 'trial_active', 'trial_expired', 'active', 'suspended', 'cancelled')", name="ck_saas_tenant_memberships_status_valid"),
        sa.CheckConstraint("onboarding_state IN ('awaiting_verification', 'setup_required', 'ready')", name="ck_saas_tenant_memberships_onboarding_state_valid"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", name="uq_saas_tenant_memberships_company_id"),
        sa.UniqueConstraint("owner_user_id", name="uq_saas_tenant_memberships_owner_user_id"),
        sa.UniqueConstraint("owner_email", name="uq_saas_tenant_memberships_owner_email"),
    )
    op.create_index("ix_saas_memberships_status_trial", "saas_tenant_memberships", ["status", "trial_ends_at"])
    op.create_index("ix_saas_tenant_memberships_trial_ends_at", "saas_tenant_memberships", ["trial_ends_at"])
    op.create_table(
        "saas_account_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_ip", sa.String(length=45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("purpose IN ('verify_email', 'reset_password')", name="ck_saas_account_credentials_purpose_valid"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_saas_account_credentials_token_hash"),
    )
    op.create_index("ix_saas_account_credentials_lookup", "saas_account_credentials", ["purpose", "expires_at", "used_at"])
    op.create_index("ix_saas_account_credentials_company", "saas_account_credentials", ["company_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_saas_account_credentials_company", table_name="saas_account_credentials")
    op.drop_index("ix_saas_account_credentials_lookup", table_name="saas_account_credentials")
    op.drop_table("saas_account_credentials")
    op.drop_index("ix_saas_tenant_memberships_trial_ends_at", table_name="saas_tenant_memberships")
    op.drop_index("ix_saas_memberships_status_trial", table_name="saas_tenant_memberships")
    op.drop_table("saas_tenant_memberships")
    op.execute("DELETE FROM platform_tenant_profiles WHERE created_by IS NULL")
    op.alter_column("platform_tenant_profiles", "created_by", nullable=False)
