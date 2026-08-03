from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, text
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
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_operators.id"),
        nullable=False,
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
