"""add SaaS privacy and tenant-approved support workflows

Revision ID: p11platform0015
Revises: p10platform0014
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p11platform0015"
down_revision: Union[str, None] = "p10platform0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saas_privacy_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requester_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_type", sa.String(length=30), nullable=False),
        sa.Column("subject_email", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default=sa.text("'submitted'"), nullable=False),
        sa.Column("identity_verification", sa.String(length=30), server_default=sa.text("'authenticated_owner'"), nullable=False),
        sa.Column("target_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_summary", sa.Text(), nullable=True),
        sa.Column("decision_reason", sa.String(length=500), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("request_type IN ('access', 'export', 'correction', 'deletion', 'restriction', 'objection', 'consent_withdrawal')", name="ck_saas_privacy_requests_request_type_valid"),
        sa.CheckConstraint("status IN ('submitted', 'identity_verified', 'in_review', 'fulfilled', 'rejected', 'cancelled')", name="ck_saas_privacy_requests_status_valid"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requester_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["platform_operators.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_saas_privacy_company_status", "saas_privacy_requests", ["company_id", "status", "created_at"])
    op.create_table(
        "saas_retention_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("privacy_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_category", sa.String(length=40), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("rationale", sa.String(length=1000), nullable=False),
        sa.Column("retain_until", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'proposed'"), nullable=False),
        sa.Column("proposed_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("data_category IN ('account_identity', 'account_security', 'billing_records', 'support_records', 'audit_evidence', 'tenant_business_data')", name="ck_saas_retention_decisions_data_category_valid"),
        sa.CheckConstraint("action IN ('retain', 'delete', 'anonymize')", name="ck_saas_retention_decisions_action_valid"),
        sa.CheckConstraint("status IN ('proposed', 'approved', 'rejected')", name="ck_saas_retention_decisions_status_valid"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["privacy_request_id"], ["saas_privacy_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proposed_by"], ["platform_operators.id"]),
        sa.ForeignKeyConstraint(["decided_by"], ["platform_operators.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_saas_retention_company_status", "saas_retention_decisions", ["company_id", "status"])
    op.create_table(
        "saas_support_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_number", sa.String(length=40), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requester_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.String(length=10), server_default=sa.text("'normal'"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'open'"), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("assigned_operator_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("category IN ('account', 'billing', 'technical', 'privacy', 'other')", name="ck_saas_support_tickets_category_valid"),
        sa.CheckConstraint("priority IN ('low', 'normal', 'high', 'urgent')", name="ck_saas_support_tickets_priority_valid"),
        sa.CheckConstraint("status IN ('open', 'in_progress', 'waiting_tenant', 'resolved', 'closed')", name="ck_saas_support_tickets_status_valid"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requester_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_operator_id"], ["platform_operators.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_number", name="uq_saas_support_tickets_ticket_number"),
    )
    op.create_index("ix_saas_support_company_status", "saas_support_tickets", ["company_id", "status", "created_at"])
    op.create_table(
        "saas_support_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_type", sa.String(length=30), nullable=False),
        sa.Column("sender_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sender_operator_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("sender_type IN ('tenant_owner', 'platform_operator')", name="ck_saas_support_messages_sender_type_valid"),
        sa.CheckConstraint("(sender_type = 'tenant_owner' AND sender_user_id IS NOT NULL AND sender_operator_id IS NULL) OR (sender_type = 'platform_operator' AND sender_user_id IS NULL AND sender_operator_id IS NOT NULL)", name="ck_saas_support_messages_sender_identity_valid"),
        sa.ForeignKeyConstraint(["ticket_id"], ["saas_support_tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["sender_operator_id"], ["platform_operators.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_saas_support_messages_ticket_created", "saas_support_messages", ["ticket_id", "created_at"])
    op.create_table(
        "saas_support_access_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_operator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("purpose", sa.String(length=500), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision_reason", sa.String(length=500), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_type", sa.String(length=30), nullable=True),
        sa.Column("revoke_reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'approved', 'denied', 'revoked')", name="ck_saas_support_access_grants_status_valid"),
        sa.CheckConstraint("duration_minutes > 0 AND duration_minutes <= 60", name="ck_saas_support_access_grants_duration_valid"),
        sa.CheckConstraint("revoked_by_type IS NULL OR revoked_by_type IN ('tenant_owner', 'platform_operator')", name="ck_saas_support_access_grants_revoked_by_type_valid"),
        sa.ForeignKeyConstraint(["ticket_id"], ["saas_support_tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_operator_id"], ["platform_operators.id"]),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_saas_support_grants_company_status", "saas_support_access_grants", ["company_id", "status", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_saas_support_grants_company_status", table_name="saas_support_access_grants")
    op.drop_table("saas_support_access_grants")
    op.drop_index("ix_saas_support_messages_ticket_created", table_name="saas_support_messages")
    op.drop_table("saas_support_messages")
    op.drop_index("ix_saas_support_company_status", table_name="saas_support_tickets")
    op.drop_table("saas_support_tickets")
    op.drop_index("ix_saas_retention_company_status", table_name="saas_retention_decisions")
    op.drop_table("saas_retention_decisions")
    op.drop_index("ix_saas_privacy_company_status", table_name="saas_privacy_requests")
    op.drop_table("saas_privacy_requests")
