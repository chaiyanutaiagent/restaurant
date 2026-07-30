from __future__ import annotations

from datetime import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.hr import Employee
    from app.models.restaurant import Brand
    from app.models.role import Role
    from app.models.settings import UserInvitation
    from app.models.user import User


class UserAccessRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "user_access_requests"
    __table_args__ = (
        Index("ix_user_access_requests_company_status_created", "company_id", "status", "created_at"),
        Index("ix_user_access_requests_company_branch_status", "company_id", "branch_id", "status"),
        Index("ix_user_access_requests_company_brand_status", "company_id", "brand_id", "status"),
        Index(
            "ix_user_access_requests_employee_open_unique",
            "employee_id",
            unique=True,
            postgresql_where=text("employee_id IS NOT NULL AND status IN ('pending', 'approved')"),
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
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id"),
        nullable=True,
        index=True,
    )
    requested_role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id"),
        nullable=False,
    )
    approved_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id"),
        nullable=True,
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id"),
        nullable=True,
    )
    employee_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    requested_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    initial_password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    request_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    activated_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    branch: Mapped["Branch"] = relationship("Branch")
    brand: Mapped["Brand | None"] = relationship("Brand")
    requested_role: Mapped["Role"] = relationship("Role", foreign_keys=[requested_role_id])
    approved_role: Mapped["Role | None"] = relationship("Role", foreign_keys=[approved_role_id])
    employee: Mapped["Employee | None"] = relationship("Employee")
    requester: Mapped["User"] = relationship("User", foreign_keys=[requested_by])
    reviewer: Mapped["User | None"] = relationship("User", foreign_keys=[reviewed_by])
    activated_user: Mapped["User | None"] = relationship("User", foreign_keys=[activated_user_id])
    invitations: Mapped[list["UserInvitation"]] = relationship(
        "UserInvitation",
        back_populates="access_request",
    )


Index(
    "ix_user_access_requests_username_pending_unique",
    UserAccessRequest.company_id,
    func.lower(UserAccessRequest.requested_username),
    unique=True,
    postgresql_where=text("requested_username IS NOT NULL AND status = 'pending'"),
)
