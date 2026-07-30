from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, PrimaryKeyConstraint, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.user import User


class CustomerTier(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "customer_tiers"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_customer_tiers_company_id_name"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_th: Mapped[str] = mapped_column(String(100), nullable=False)
    min_lifetime_spend: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    points_multiplier: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, server_default=text("1.0"))
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    benefits: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    company: Mapped["Company"] = relationship("Company")
    customers: Mapped[list["Customer"]] = relationship("Customer", back_populates="tier")


class Customer(SoftDeleteMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("company_id", "customer_code", name="uq_customers_company_id_customer_code"),
        Index(
            "ix_customers_company_phone_unique",
            "company_id",
            "phone",
            unique=True,
            postgresql_where=text("phone IS NOT NULL"),
        ),
        Index("ix_customers_company_phone", "company_id", "phone"),
        Index("ix_customers_company_email", "company_id", "email"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    tier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_tiers.id"), nullable=True, index=True)
    customer_code: Mapped[str] = mapped_column(String(20), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    tax_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    points_balance: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    lifetime_spend: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    lifetime_points_earned: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    lifetime_points_redeemed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_orders: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_purchase_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_blacklisted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    blacklist_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship("Company")
    tier: Mapped["CustomerTier | None"] = relationship("CustomerTier", back_populates="customers")
    points_transactions: Mapped[list["PointsTransaction"]] = relationship("PointsTransaction", back_populates="customer")
    tag_assignments: Mapped[list["CustomerTagAssignment"]] = relationship("CustomerTagAssignment", back_populates="customer", cascade="all, delete-orphan")

    @property
    def full_name(self) -> str:
        full_name = " ".join(part for part in [self.first_name, self.last_name] if part)
        return full_name or self.display_name or self.customer_code


class LoyaltySettings(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "loyalty_settings"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, unique=True)
    earn_rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, server_default=text("1.0"))
    earn_min_spend: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    redeem_rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, server_default=text("0.1"))
    redeem_min_points: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("100"))
    redeem_max_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("100"))
    points_expiry_months: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("12"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    require_phone: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    company: Mapped["Company"] = relationship("Company")


class PointsTransaction(UUIDMixin, Base):
    __tablename__ = "points_transactions"
    __table_args__ = (
        Index("ix_points_transactions_customer_created_at", "customer_id", "created_at"),
        Index("ix_points_transactions_company_transaction_type", "company_id", "transaction_type"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    spend_amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    redeem_amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    company: Mapped["Company"] = relationship("Company")
    customer: Mapped["Customer"] = relationship("Customer", back_populates="points_transactions")
    creator: Mapped["User | None"] = relationship("User")


class CustomerTag(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "customer_tags"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_customer_tags_company_id_name"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False, server_default=text("'#6366f1'"))

    company: Mapped["Company"] = relationship("Company")
    customer_assignments: Mapped[list["CustomerTagAssignment"]] = relationship("CustomerTagAssignment", back_populates="tag", cascade="all, delete-orphan")


class CustomerTagAssignment(Base):
    __tablename__ = "customer_tag_assignments"
    __table_args__ = (
        PrimaryKeyConstraint("customer_id", "tag_id", name="pk_customer_tag_assignments"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    tag_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_tags.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    customer: Mapped["Customer"] = relationship("Customer", back_populates="tag_assignments")
    tag: Mapped["CustomerTag"] = relationship("CustomerTag", back_populates="customer_assignments")
