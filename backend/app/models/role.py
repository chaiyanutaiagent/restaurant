from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Table, UniqueConstraint, Column, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.company import Company


role_permissions_table = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", UUID(as_uuid=True), ForeignKey("permissions.id"), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
)


class Role(SoftDeleteMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_roles_company_id_name"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_branch_assignable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    allowed_scope_types: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        server_default=text("'[\"branch\"]'::json"),
    )

    company: Mapped["Company"] = relationship("Company")
    permissions: Mapped[list["Permission"]] = relationship(
        "Permission",
        secondary=role_permissions_table,
        back_populates="roles",
    )


class Permission(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    module: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    roles: Mapped[list["Role"]] = relationship(
        "Role",
        secondary=role_permissions_table,
        back_populates="permissions",
    )
