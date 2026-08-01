from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


DEVICE_TYPES = ("counter", "kitchen", "pickup")


class DeviceRegistration(UUIDMixin, TimestampMixin, Base):
    """Identity-owned device credential and server-controlled Restaurant context."""

    __tablename__ = "device_registrations"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "device_code",
            name="uq_device_registrations_company_device_code",
        ),
        CheckConstraint(
            "device_type IN ('counter', 'kitchen', 'pickup')",
            name="supported_device_type",
        ),
        CheckConstraint(
            "(device_type = 'kitchen' AND station_key IS NOT NULL "
            "AND length(btrim(station_key)) > 0) OR "
            "(device_type IN ('counter', 'pickup') AND station_key IS NULL)",
            name="device_station_shape",
        ),
        CheckConstraint("credential_version > 0", name="positive_credential_version"),
        CheckConstraint(
            "failed_pairing_attempts >= 0",
            name="failed_pairing_attempts_nonnegative",
        ),
        Index(
            "ix_device_registrations_company_branch_active",
            "company_id",
            "branch_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id"),
        nullable=False,
        index=True,
    )
    device_code: Mapped[str] = mapped_column(String(24), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    device_type: Mapped[str] = mapped_column(String(20), nullable=False)
    station_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pairing_pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pairing_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    failed_pairing_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    pairing_locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    credential_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )
    refresh_credential_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    refresh_credential_issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    paired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
