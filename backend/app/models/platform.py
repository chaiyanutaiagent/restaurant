from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, text
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
