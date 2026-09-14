from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class CompanyDistributionDemand(UUIDMixin, TimestampMixin, Base):
    """Company-level finished-goods demand received from one POS workspace."""

    __tablename__ = "company_distribution_demands"
    __table_args__ = (
        UniqueConstraint("company_id", "idempotency_key", name="uq_company_distribution_demands_idempotency"),
        Index("ix_company_distribution_demands_queue", "company_id", "needed_on", "status", "source_module"),
        CheckConstraint(
            "source_module IN ('restaurant_pos', 'takeaway_pos', 'retail_pos')",
            name="ck_company_distribution_demands_module",
        ),
        CheckConstraint(
            "status IN ('submitted', 'partially_allocated', 'allocated', 'fulfilled', 'cancelled')",
            name="ck_company_distribution_demands_status",
        ),
        CheckConstraint("requested_qty > 0", name="ck_company_distribution_demands_qty_positive"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    source_module: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    needed_on: Mapped[date] = mapped_column(Date, nullable=False)
    requested_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'submitted'"))
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    brand: Mapped["Brand"] = relationship("Brand")  # type: ignore[name-defined]
    branch: Mapped["Branch"] = relationship("Branch")  # type: ignore[name-defined]
    product: Mapped["Product"] = relationship("Product")  # type: ignore[name-defined]
    shipments: Mapped[list["CompanyDistributionShipment"]] = relationship(
        "CompanyDistributionShipment", back_populates="demand", order_by="CompanyDistributionShipment.created_at.asc()"
    )


class CompanyDistributionShipment(UUIDMixin, TimestampMixin, Base):
    """Distribution orchestration linked to the existing inventory transfer source of truth."""

    __tablename__ = "company_distribution_shipments"
    __table_args__ = (
        UniqueConstraint("company_id", "shipment_number", name="uq_company_distribution_shipments_number"),
        UniqueConstraint("company_id", "idempotency_key", name="uq_company_distribution_shipments_idempotency"),
        UniqueConstraint("transfer_order_id", name="uq_company_distribution_shipments_transfer"),
        Index("ix_company_distribution_shipments_tracking", "company_id", "status", "source_module", "brand_id", "branch_id"),
        CheckConstraint(
            "source_module IN ('restaurant_pos', 'takeaway_pos', 'retail_pos')",
            name="ck_company_distribution_shipments_module",
        ),
        CheckConstraint(
            "status IN ('planned', 'in_transit', 'partially_received', 'received', 'rejected', 'partially_returned', 'returned', 'cancelled')",
            name="ck_company_distribution_shipments_status",
        ),
        CheckConstraint("planned_qty > 0", name="ck_company_distribution_shipments_planned_positive"),
        CheckConstraint("shipped_qty >= 0 AND received_qty >= 0 AND rejected_qty >= 0 AND returned_qty >= 0", name="ck_company_distribution_shipments_qty_nonnegative"),
        CheckConstraint("shipped_qty <= planned_qty", name="ck_company_distribution_shipments_ship_le_plan"),
        CheckConstraint("received_qty + rejected_qty <= shipped_qty", name="ck_company_distribution_shipments_settle_le_ship"),
        CheckConstraint("returned_qty <= received_qty", name="ck_company_distribution_shipments_return_le_receive"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    demand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company_distribution_demands.id"), nullable=False, index=True)
    transfer_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("transfer_orders.id"), nullable=False, index=True)
    source_module: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    from_location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_locations.id"), nullable=False)
    to_location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_locations.id"), nullable=False)
    shipment_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'planned'"))
    planned_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    shipped_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    received_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    rejected_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    returned_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    unit_code: Mapped[str] = mapped_column(String(30), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    planned_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    demand: Mapped["CompanyDistributionDemand"] = relationship("CompanyDistributionDemand", back_populates="shipments")
    transfer_order: Mapped["TransferOrder"] = relationship("TransferOrder")  # type: ignore[name-defined]
    brand: Mapped["Brand"] = relationship("Brand")  # type: ignore[name-defined]
    branch: Mapped["Branch"] = relationship("Branch")  # type: ignore[name-defined]
    product: Mapped["Product"] = relationship("Product")  # type: ignore[name-defined]
    events: Mapped[list["CompanyDistributionEvent"]] = relationship(
        "CompanyDistributionEvent", back_populates="shipment", order_by="CompanyDistributionEvent.created_at.asc()"
    )


class CompanyDistributionEvent(UUIDMixin, Base):
    """Append-only business audit. Inventory quantities remain authoritative in StockMovement."""

    __tablename__ = "company_distribution_events"
    __table_args__ = (
        UniqueConstraint("company_id", "idempotency_key", name="uq_company_distribution_events_idempotency"),
        Index("ix_company_distribution_events_report", "company_id", "created_at", "event_type", "source_module"),
        CheckConstraint(
            "event_type IN ('planned', 'dispatched', 'received', 'rejected', 'returned', 'cancelled')",
            name="ck_company_distribution_events_type",
        ),
        CheckConstraint("qty >= 0", name="ck_company_distribution_events_qty_nonnegative"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    shipment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company_distribution_shipments.id", ondelete="CASCADE"), nullable=False, index=True)
    transfer_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("transfer_orders.id"), nullable=True, index=True)
    source_module: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(30), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"), index=True)

    shipment: Mapped["CompanyDistributionShipment"] = relationship("CompanyDistributionShipment", back_populates="events")
    transfer_order: Mapped["TransferOrder | None"] = relationship("TransferOrder")  # type: ignore[name-defined]
