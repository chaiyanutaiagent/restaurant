from __future__ import annotations

from datetime import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import SoftDeleteMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.company import Company
    from app.models.restaurant import Brand
    from app.models.role import Role


class User(SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("company_id", "username", name="uq_users_company_id_username"),
        Index(
            "ix_users_company_id_email_unique",
            "company_id",
            "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    employee_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    company: Mapped["Company"] = relationship("Company", back_populates="users")
    user_branches: Mapped[list["UserBranch"]] = relationship("UserBranch", back_populates="user")
    branches: Mapped[list["Branch"]] = relationship(
        "Branch",
        secondary="user_branches",
        primaryjoin="User.id == UserBranch.user_id",
        secondaryjoin="Branch.id == UserBranch.branch_id",
        viewonly=True,
    )


class UserBranch(UUIDMixin, Base):
    __tablename__ = "user_branches"
    __table_args__ = (
        Index(
            "ix_user_branches_user_branch_active_unique",
            "user_id",
            "branch_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint(
            "business_type IS NULL OR business_type IN ('restaurant', 'retail_pos', 'takeaway')",
            name="ck_user_branches_business_type",
        ),
        CheckConstraint(
            "target_database IS NULL OR target_database IN ('restaurant', 'retail_pos', 'takeaway')",
            name="ck_user_branches_target_database",
        ),
        CheckConstraint(
            "(brand_id IS NULL AND business_type IS NULL AND target_database IS NULL) "
            "OR (brand_id IS NOT NULL AND business_type IS NOT NULL "
            "AND target_database = business_type)",
            name="ck_user_branches_context_complete",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id"),
        nullable=False,
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id"),
        nullable=True,
        index=True,
    )
    business_type: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    target_database: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id"),
        nullable=False,
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="user_branches")
    branch: Mapped["Branch"] = relationship("Branch", back_populates="user_branches")
    brand: Mapped["Brand | None"] = relationship("Brand")
    role: Mapped["Role"] = relationship("Role")
