from __future__ import annotations

from datetime import date, datetime
import uuid

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class PlatformOperator(UUIDMixin, TimestampMixin, Base):
    """Platform-only identity; never reused as a tenant staff account."""

    __tablename__ = "platform_operators"
    __table_args__ = (
        CheckConstraint(
            "credential_version > 0",
            name="credential_version_positive",
        ),
        CheckConstraint(
            "failed_login_attempts >= 0",
            name="failed_attempts_nonnegative",
        ),
        Index("ix_platform_operators_active", "is_active"),
    )

    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    credential_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    mfa_secret_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_enabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    mfa_last_verified_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mfa_recovery_code_hashes: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'::json"),
    )

    @property
    def mfa_enabled(self) -> bool:
        return self.mfa_enabled_at is not None


class PlatformSession(UUIDMixin, TimestampMixin, Base):
    """Revocable Platform-only browser session with rotating opaque credentials."""

    __tablename__ = "platform_sessions"
    __table_args__ = (
        CheckConstraint(
            "credential_version > 0",
            name="credential_version_positive",
        ),
        Index("ix_platform_sessions_operator_active", "operator_id", "revoked_at"),
        Index("ix_platform_sessions_expires_at", "expires_at"),
    )

    operator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_operators.id", ondelete="CASCADE"),
        nullable=False,
    )
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mfa_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)


class PlatformTenantProfile(UUIDMixin, TimestampMixin, Base):
    """Manual commercial controls and lifecycle metadata owned by Platform."""

    __tablename__ = "platform_tenant_profiles"
    __table_args__ = (
        Index("ix_platform_tenant_profiles_plan_code", "plan_code"),
        Index("ix_platform_tenant_profiles_suspended_at", "suspended_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        unique=True,
    )
    plan_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default=text("'starter'"),
    )
    feature_flags: Mapped[dict[str, bool]] = mapped_column(
        JSON,
        nullable=False,
        server_default=text("'{}'::json"),
    )
    plan_limits: Mapped[dict[str, int]] = mapped_column(
        JSON,
        nullable=False,
        server_default=text("'{}'::json"),
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_operators.id"),
        nullable=True,
    )
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_operators.id"),
        nullable=True,
    )
    suspension_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reactivated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_operators.id"),
        nullable=True,
    )
    reactivation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PlatformTenantUsageSnapshot(UUIDMixin, TimestampMixin, Base):
    """PII-free daily aggregate used by Platform operations and later billing decisions."""

    __tablename__ = "platform_tenant_usage_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "captured_on",
            name="company_captured_on",
        ),
        Index("ix_platform_usage_snapshots_captured_on", "captured_on"),
        Index("ix_platform_usage_snapshots_company_created", "company_id", "created_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    captured_on: Mapped[date] = mapped_column(Date, nullable=False)
    plan_code: Mapped[str] = mapped_column(String(50), nullable=False)
    feature_flags: Mapped[dict[str, bool]] = mapped_column(JSON, nullable=False)
    plan_limits: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    usage: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    limit_state: Mapped[dict[str, dict]] = mapped_column(JSON, nullable=False)
    attention_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    onboarding_completed_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    onboarding_total_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_operators.id"),
        nullable=False,
    )


class SaasTenantMembership(UUIDMixin, TimestampMixin, Base):
    """Public SaaS owner lifecycle; separate from staff and CRM memberships."""

    __tablename__ = "saas_tenant_memberships"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_verification', 'trial_active', 'trial_expired', "
            "'active', 'suspended', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint(
            "onboarding_state IN ('awaiting_verification', 'setup_required', 'ready')",
            name="onboarding_state_valid",
        ),
        Index("ix_saas_memberships_status_trial", "status", "trial_ends_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    owner_email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'pending_verification'"),
    )
    onboarding_state: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'awaiting_verification'"),
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trial_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    terms_version: Mapped[str] = mapped_column(String(50), nullable=False)
    privacy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SaasAccountCredential(UUIDMixin, Base):
    """Single-use hashed credential for verification and password recovery."""

    __tablename__ = "saas_account_credentials"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('verify_email', 'reset_password')",
            name="purpose_valid",
        ),
        Index(
            "ix_saas_account_credentials_lookup",
            "purpose",
            "expires_at",
            "used_at",
        ),
        Index("ix_saas_account_credentials_company", "company_id", "created_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class PlatformOperationsSnapshot(UUIDMixin, Base):
    """Sanitized Platform-only operational evidence; never stores logs or paths."""

    __tablename__ = "platform_operations_snapshots"
    __table_args__ = (
        CheckConstraint(
            "overall_status IN ('ok', 'degraded', 'critical')",
            name="overall_status_valid",
        ),
        CheckConstraint(
            "source IN ('operator_runtime', 'scheduled_runtime', 'resilience_import')",
            name="source_valid",
        ),
        CheckConstraint(
            "backup_status IN ('unknown', 'current', 'stale', 'failed')",
            name="backup_status_valid",
        ),
        CheckConstraint(
            "restore_status IN ('unknown', 'passed', 'stale', 'failed')",
            name="restore_status_valid",
        ),
        CheckConstraint(
            "alert_delivery_status IN ('unknown', 'not_configured', 'healthy', 'failed')",
            name="alert_delivery_status_valid",
        ),
        CheckConstraint(
            "disk_usage_percent IS NULL OR "
            "(disk_usage_percent >= 0 AND disk_usage_percent <= 100)",
            name="disk_usage_percent_valid",
        ),
        CheckConstraint(
            "backup_age_hours IS NULL OR backup_age_hours >= 0",
            name="backup_age_hours_valid",
        ),
        Index("ix_platform_operations_captured_at", "captured_at"),
        Index("ix_platform_operations_status", "overall_status", "captured_at"),
    )

    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    overall_status: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    component_checks: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    projector_failed_events: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    projector_loop_errors: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    disk_usage_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    backup_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'unknown'")
    )
    backup_age_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    restore_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'unknown'")
    )
    restore_drill_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    alert_delivery_status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'unknown'")
    )
    alert_codes: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'::json")
    )
    evidence_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    captured_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_operators.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
