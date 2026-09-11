from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Integer, String, Text, text
from sqlalchemy.orm import Mapped, relationship, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.user import User


class Company(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint(
            "credential_version > 0",
            name="company_credential_version_positive",
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_slug: Mapped[str] = mapped_column(String(63), nullable=False, unique=True, index=True)
    name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vat_registered: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'THB'"))
    timezone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default=text("'Asia/Bangkok'"),
    )
    fiscal_year_start: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    credential_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )

    branches: Mapped[list["Branch"]] = relationship("Branch", back_populates="company")
    users: Mapped[list["User"]] = relationship("User", back_populates="company")
