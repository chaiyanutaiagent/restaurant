from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.api_integration import ExternalOrder
    from app.models.branch import Branch
    from app.models.company import Company
    from app.models.pos import SaleOrder
    from app.models.product import Product
    from app.models.user import User


class Carrier(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "carriers"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_carriers_company_id_code"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tracking_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_cod: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    company: Mapped["Company"] = relationship("Company")
    rates: Mapped[list["ShippingRate"]] = relationship("ShippingRate", back_populates="carrier")
    shipments: Mapped[list["Shipment"]] = relationship("Shipment", back_populates="carrier")


class ShippingRate(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "shipping_rates"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    carrier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("carriers.id"), nullable=False, index=True)
    service_name: Mapped[str] = mapped_column(String(100), nullable=False)
    zone: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'all'"))
    min_weight_g: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_weight_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    per_kg_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("0"))
    cod_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    company: Mapped["Company"] = relationship("Company")
    carrier: Mapped["Carrier"] = relationship("Carrier", back_populates="rates")


class Shipment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "shipments"
    __table_args__ = (
        Index("ix_shipments_company_id_shipment_number", "company_id", "shipment_number"),
        Index("ix_shipments_status", "status"),
        Index("ix_shipments_tracking_number", "tracking_number"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    carrier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("carriers.id"), nullable=False, index=True)
    shipment_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    sale_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sale_orders.id"), nullable=True, index=True)
    external_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("external_orders.id"), nullable=True, index=True)
    sender_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    sender_address: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_name: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient_address: Mapped[str] = mapped_column(Text, nullable=False)
    weight_grams: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    width_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    depth_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    service_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_cod: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    cod_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    tracking_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    company: Mapped["Company"] = relationship("Company")
    branch: Mapped["Branch"] = relationship("Branch")
    carrier: Mapped["Carrier"] = relationship("Carrier", back_populates="shipments")
    sale_order: Mapped["SaleOrder | None"] = relationship("SaleOrder")
    external_order: Mapped["ExternalOrder | None"] = relationship("ExternalOrder")
    creator: Mapped["User"] = relationship("User")
    items: Mapped[list["ShipmentItem"]] = relationship(
        "ShipmentItem",
        back_populates="shipment",
        cascade="all, delete-orphan",
        order_by="ShipmentItem.created_at.asc()",
    )
    events: Mapped[list["ShipmentEvent"]] = relationship(
        "ShipmentEvent",
        back_populates="shipment",
        cascade="all, delete-orphan",
        order_by="ShipmentEvent.event_at.asc()",
    )


class ShipmentItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "shipment_items"

    shipment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)
    product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)

    shipment: Mapped["Shipment"] = relationship("Shipment", back_populates="items")
    product: Mapped["Product | None"] = relationship("Product")


class ShipmentEvent(UUIDMixin, Base):
    __tablename__ = "shipment_events"

    shipment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    shipment: Mapped["Shipment"] = relationship("Shipment", back_populates="events")
    creator: Mapped["User | None"] = relationship("User")
