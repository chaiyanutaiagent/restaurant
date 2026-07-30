from __future__ import annotations

from datetime import date, datetime
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Text, text
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


class TransferOrder(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "transfer_orders"
    __table_args__ = (
        CheckConstraint("from_location_id <> to_location_id", name="ck_transfer_orders_locations_different"),
        Index("ix_transfer_orders_company_id_to_number", "company_id", "to_number"),
        Index("ix_transfer_orders_status", "status"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    to_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'draft'"))
    from_branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id"),
        nullable=False,
        index=True,
    )
    to_branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id"),
        nullable=False,
        index=True,
    )
    from_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stock_locations.id"),
        nullable=False,
        index=True,
    )
    to_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stock_locations.id"),
        nullable=False,
        index=True,
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    received_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    request_date: Mapped[date] = mapped_column(Date, nullable=False, server_default=text("CURRENT_DATE"))
    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_discrepancy: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    discrepancy_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    destination_posted_at_ship: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship("Company")
    from_branch: Mapped["Branch"] = relationship("Branch", foreign_keys=[from_branch_id])
    to_branch: Mapped["Branch"] = relationship("Branch", foreign_keys=[to_branch_id])
    from_location: Mapped["StockLocation"] = relationship("StockLocation", foreign_keys=[from_location_id])
    to_location: Mapped["StockLocation"] = relationship("StockLocation", foreign_keys=[to_location_id])
    requester: Mapped["User"] = relationship("User", foreign_keys=[requested_by])
    approver: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by])
    receiver: Mapped["User | None"] = relationship("User", foreign_keys=[received_by])
    items: Mapped[list["TransferOrderItem"]] = relationship(
        "TransferOrderItem",
        back_populates="transfer_order",
        cascade="all, delete-orphan",
        order_by="TransferOrderItem.created_at.asc()",
    )


class TransferOrderItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "transfer_order_items"

    to_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transfer_orders.id"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id"),
        nullable=False,
        index=True,
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_variants.id"),
        nullable=True,
        index=True,
    )
    product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    unit_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    qty_requested: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    qty_approved: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    qty_sent: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    qty_received: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(15, 4),
        nullable=False,
        server_default=text("0"),
    )
    qty_discrepancy: Mapped[Decimal] = mapped_column(
        Numeric(15, 4),
        nullable=False,
        server_default=text("0"),
    )

    @property
    def qty_in_transit(self) -> Decimal:
        return max(
            Decimal(self.qty_sent or 0)
            - Decimal(self.qty_received or 0)
            - Decimal(self.qty_discrepancy or 0),
            Decimal("0"),
        )

    transfer_order: Mapped["TransferOrder"] = relationship("TransferOrder", back_populates="items")
    company: Mapped["Company"] = relationship("Company")
    product: Mapped["Product"] = relationship("Product")
    variant: Mapped["ProductVariant | None"] = relationship("ProductVariant")
