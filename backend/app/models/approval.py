from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


APPROVAL_ACTIONS = (
    "pos.discount.override",
    "pos.price.override",
    "pos.sale.void",
    "pos.refund.create",
    "inventory.stock.adjust",
)


class ManagerPinCredential(UUIDMixin, TimestampMixin, Base):
    """Identity-owned manager credential; never copied into the operational boundary."""

    __tablename__ = "manager_pin_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_manager_pin_credentials_user_id"),
        CheckConstraint("failed_attempts >= 0", name="failed_attempts_nonnegative"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    pin_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    failed_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pin_set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApprovalGrantUsage(UUIDMixin, Base):
    """Operational, single-use receipt for a signed approval grant."""

    __tablename__ = "approval_grant_usages"
    __table_args__ = (
        UniqueConstraint("grant_id", name="uq_approval_grant_usages_grant_id"),
        CheckConstraint(
            "action IN (" + ", ".join(f"'{action}'" for action in APPROVAL_ACTIONS) + ")",
            name="supported_action",
        ),
        Index(
            "ix_approval_grant_usages_company_branch_consumed",
            "company_id",
            "branch_id",
            "consumed_at",
        ),
    )

    # Scalar IDs intentionally have no cross-database foreign keys.
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    grant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requester_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
