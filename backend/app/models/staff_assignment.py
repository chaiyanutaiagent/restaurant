from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDMixin


class StaffRoleAssignment(UUIDMixin, Base):
    __tablename__ = "staff_role_assignments"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('company', 'brand', 'branch', 'station')",
            name="ck_staff_role_assignments_scope_type",
        ),
        CheckConstraint(
            "(scope_type = 'company' AND brand_id IS NULL AND branch_id IS NULL "
            "AND station_key IS NULL) OR "
            "(scope_type = 'brand' AND brand_id IS NOT NULL AND branch_id IS NULL "
            "AND station_key IS NULL) OR "
            "(scope_type = 'branch' AND brand_id IS NOT NULL AND branch_id IS NOT NULL "
            "AND station_key IS NULL) OR "
            "(scope_type = 'station' AND brand_id IS NOT NULL AND branch_id IS NOT NULL "
            "AND station_key IS NOT NULL AND length(btrim(station_key)) > 0)",
            name="ck_staff_role_assignments_scope_shape",
        ),
        Index(
            "uq_staff_role_assignments_active_scope",
            "user_id",
            "role_id",
            "scope_type",
            "scope_key",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "ix_staff_role_assignments_user_active",
            "company_id",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False, index=True
    )
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(255), nullable=False)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id"), nullable=True, index=True
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True, index=True
    )
    station_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    assignment_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    assigned_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    role = relationship("Role")
    brand = relationship("Brand")
    branch = relationship("Branch")
    assigner = relationship("User", foreign_keys=[assigned_by])
    revoker = relationship("User", foreign_keys=[revoked_by])
