from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.company import Company
    from app.models.product import Product, ProductVariant
    from app.models.stock import StockLocation
    from app.models.user import User


class StockCountSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "stock_count_sessions"
    __table_args__ = (
        Index("ix_stock_count_sessions_company_id_session_number", "company_id", "session_number"),
        Index("ix_stock_count_sessions_status", "status"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_locations.id"), nullable=False, index=True
    )
    session_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'draft'"))
    count_date: Mapped[date] = mapped_column(Date, nullable=False, server_default=text("CURRENT_DATE"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    completed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    items_matched: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    items_over: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    items_short: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_variance_value: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))

    company: Mapped["Company"] = relationship("Company")
    branch: Mapped["Branch"] = relationship("Branch")
    location: Mapped["StockLocation"] = relationship("StockLocation")
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    completer: Mapped["User | None"] = relationship("User", foreign_keys=[completed_by])
    items: Mapped[list["StockCountItem"]] = relationship(
        "StockCountItem",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="StockCountItem.product_name.asc()",
    )


class StockCountItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "stock_count_items"
    __table_args__ = (
        UniqueConstraint("session_id", "product_id", "variant_id", name="uq_stock_count_items_session_product_variant"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_count_sessions.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_variants.id"), nullable=True, index=True
    )
    product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    unit_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    expected_qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    actual_qty: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    variance_qty: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    cost_per_unit: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    variance_value: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    counted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    counted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_adjusted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    session: Mapped["StockCountSession"] = relationship("StockCountSession", back_populates="items")
    company: Mapped["Company"] = relationship("Company")
    product: Mapped["Product"] = relationship("Product")
    variant: Mapped["ProductVariant | None"] = relationship("ProductVariant")
    counter: Mapped["User | None"] = relationship("User", foreign_keys=[counted_by])
