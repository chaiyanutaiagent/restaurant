from __future__ import annotations

from datetime import date, datetime
import uuid

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class SaasPrivacyRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "saas_privacy_requests"
    __table_args__ = (
        CheckConstraint("request_type IN ('access', 'export', 'correction', 'deletion', 'restriction', 'objection', 'consent_withdrawal')", name="request_type_valid"),
        CheckConstraint("status IN ('submitted', 'identity_verified', 'in_review', 'fulfilled', 'rejected', 'cancelled')", name="status_valid"),
        Index("ix_saas_privacy_company_status", "company_id", "status", "created_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    requester_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    request_type: Mapped[str] = mapped_column(String(30), nullable=False)
    subject_email: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'submitted'"))
    identity_verification: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'authenticated_owner'"))
    target_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("platform_operators.id", ondelete="SET NULL"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SaasRetentionDecision(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "saas_retention_decisions"
    __table_args__ = (
        CheckConstraint("data_category IN ('account_identity', 'account_security', 'billing_records', 'support_records', 'audit_evidence', 'tenant_business_data')", name="data_category_valid"),
        CheckConstraint("action IN ('retain', 'delete', 'anonymize')", name="action_valid"),
        CheckConstraint("status IN ('proposed', 'approved', 'rejected')", name="status_valid"),
        Index("ix_saas_retention_company_status", "company_id", "status"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    privacy_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("saas_privacy_requests.id", ondelete="CASCADE"), nullable=False)
    data_category: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    rationale: Mapped[str] = mapped_column(String(1000), nullable=False)
    retain_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'proposed'"))
    proposed_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("platform_operators.id"), nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("platform_operators.id", ondelete="SET NULL"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class SaasSupportTicket(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "saas_support_tickets"
    __table_args__ = (
        CheckConstraint("category IN ('account', 'billing', 'technical', 'privacy', 'other')", name="category_valid"),
        CheckConstraint("priority IN ('low', 'normal', 'high', 'urgent')", name="priority_valid"),
        CheckConstraint("status IN ('open', 'in_progress', 'waiting_tenant', 'resolved', 'closed')", name="status_valid"),
        Index("ix_saas_support_company_status", "company_id", "status", "created_at"),
    )

    ticket_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    requester_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'normal'"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'open'"))
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    assigned_operator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("platform_operators.id", ondelete="SET NULL"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SaasSupportMessage(UUIDMixin, Base):
    __tablename__ = "saas_support_messages"
    __table_args__ = (
        CheckConstraint("sender_type IN ('tenant_owner', 'platform_operator')", name="sender_type_valid"),
        CheckConstraint("(sender_type = 'tenant_owner' AND sender_user_id IS NOT NULL AND sender_operator_id IS NULL) OR (sender_type = 'platform_operator' AND sender_user_id IS NULL AND sender_operator_id IS NOT NULL)", name="sender_identity_valid"),
        Index("ix_saas_support_messages_ticket_created", "ticket_id", "created_at"),
    )

    ticket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("saas_support_tickets.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    sender_type: Mapped[str] = mapped_column(String(30), nullable=False)
    sender_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    sender_operator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("platform_operators.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class SaasSupportAccessGrant(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "saas_support_access_grants"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'denied', 'revoked')", name="status_valid"),
        CheckConstraint("duration_minutes > 0 AND duration_minutes <= 60", name="duration_valid"),
        CheckConstraint("revoked_by_type IS NULL OR revoked_by_type IN ('tenant_owner', 'platform_operator')", name="revoked_by_type_valid"),
        Index("ix_saas_support_grants_company_status", "company_id", "status", "expires_at"),
    )

    ticket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("saas_support_tickets.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    requested_by_operator_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("platform_operators.id"), nullable=False)
    requested_scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
