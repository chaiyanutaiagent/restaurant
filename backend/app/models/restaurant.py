from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class Brand(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "brands"
    __table_args__ = (
        UniqueConstraint("company_id", "slug", name="uq_brands_company_slug"),
        Index("ix_brands_company_active", "company_id", "is_active"),
        CheckConstraint(
            "business_type IN ('restaurant', 'retail_pos', 'takeaway')",
            name="ck_brands_business_type",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    central_branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True, index=True)
    central_location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_locations.id"), nullable=True, index=True)
    central_ready_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stock_locations.id"),
        nullable=True,
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'restaurant'"),
        index=True,
    )
    storefront_mode: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'food_stall'"))
    theme_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    branches: Mapped[list["BrandBranch"]] = relationship("BrandBranch", back_populates="brand", cascade="all, delete-orphan")
    central_branch: Mapped["Branch | None"] = relationship("Branch", foreign_keys=[central_branch_id])  # type: ignore[name-defined]
    central_location: Mapped["StockLocation | None"] = relationship("StockLocation", foreign_keys=[central_location_id])  # type: ignore[name-defined]
    central_ready_location: Mapped["StockLocation | None"] = relationship(
        "StockLocation",
        foreign_keys=[central_ready_location_id],
    )  # type: ignore[name-defined]


class BrandBranch(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "brand_branches"
    __table_args__ = (
        UniqueConstraint("brand_id", "branch_id", name="uq_brand_branches_brand_branch"),
        Index("ix_brand_branches_company_brand", "company_id", "brand_id"),
        Index(
            "uq_brand_branches_active_branch",
            "branch_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    store_location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_locations.id"), nullable=True, index=True)
    branch_type: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'company_owned'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    brand: Mapped["Brand"] = relationship("Brand", back_populates="branches")
    branch: Mapped["Branch"] = relationship("Branch")  # type: ignore[name-defined]
    store_location: Mapped["StockLocation | None"] = relationship("StockLocation")  # type: ignore[name-defined]


class BranchReplenishmentPolicy(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "branch_replenishment_policies"
    __table_args__ = (
        UniqueConstraint(
            "brand_id",
            "branch_id",
            "product_id",
            name="uq_branch_replenishment_policy_product",
        ),
        Index(
            "ix_branch_replenishment_policies_company_brand_branch",
            "company_id",
            "brand_id",
            "branch_id",
        ),
        CheckConstraint("safety_stock_percent >= 0", name="ck_replenishment_safety_percent_nonnegative"),
        CheckConstraint("safety_stock_qty >= 0", name="ck_replenishment_safety_qty_nonnegative"),
        CheckConstraint("pack_size > 0", name="ck_replenishment_pack_size_positive"),
        CheckConstraint("lead_time_days >= 1", name="ck_replenishment_lead_time_positive"),
        CheckConstraint("minimum_order_qty >= 0", name="ck_replenishment_minimum_order_nonnegative"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    safety_stock_percent: Mapped[Decimal] = mapped_column(
        Numeric(7, 4), nullable=False, server_default=text("10")
    )
    safety_stock_qty: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False, server_default=text("0")
    )
    pack_size: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False, server_default=text("1")
    )
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    forecast_method: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'auto'")
    )
    minimum_order_qty: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False, server_default=text("0")
    )

    brand: Mapped["Brand"] = relationship("Brand")
    branch: Mapped["Branch"] = relationship("Branch")  # type: ignore[name-defined]
    product: Mapped["Product"] = relationship("Product")  # type: ignore[name-defined]


class Recipe(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "recipes"
    __table_args__ = (
        Index("ix_recipes_company_id", "company_id"),
        Index("ix_recipes_product_branch_type_active", "product_id", "branch_id", "recipe_type", "is_active"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id"),
        nullable=True,
        index=True,
        comment="NULL = ใช้ทุกสาขา, มีค่า = สูตรเฉพาะสาขา",
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id"),
        nullable=True,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id"),
        nullable=False,
        index=True,
    )
    recipe_type: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'menu_recipe'"))
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    yield_qty: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        server_default=text("1"),
        comment="ปริมาณที่ได้ต่อ 1 ครั้งที่ทำสูตรนี้",
    )
    yield_unit: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'แก้ว'"),
    )
    loss_percent: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False, server_default=text("0"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    product: Mapped["Product"] = relationship("Product")  # type: ignore[name-defined]
    branch: Mapped["Branch | None"] = relationship("Branch")  # type: ignore[name-defined]
    brand: Mapped["Brand | None"] = relationship("Brand")
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        "RecipeIngredient",
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="RecipeIngredient.sort_order.asc()",
    )


class DiningTable(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "dining_tables"
    __table_args__ = (
        Index("ix_dining_tables_branch_id", "branch_id"),
        Index("ix_dining_tables_branch_zone", "branch_id", "zone"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    zone: Mapped[str] = mapped_column(String(100), nullable=False, server_default=text("'โซนทั่วไป'"))
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("4"))
    table_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'dine_in'"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'available'"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    sessions: Mapped[list["DiningSession"]] = relationship("DiningSession", back_populates="table")


class DiningSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "dining_sessions"
    __table_args__ = (
        Index("ix_dining_sessions_branch_id", "branch_id"),
        Index("ix_dining_sessions_qr_token", "qr_token", unique=True),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    table_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("dining_tables.id"), nullable=True)
    qr_token: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True, server_default=text("gen_random_uuid()"))
    shift_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cashier_shifts.id"), nullable=True)
    opened_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    queue_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    queue_date: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="YYYY-MM-DD สำหรับ reset รายวัน")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'open'"))
    guest_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    sale_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sale_orders.id"), nullable=True)
    customer_slip_printed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    kitchen_slip_printed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    kitchen_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    table: Mapped["DiningTable | None"] = relationship("DiningTable", back_populates="sessions")
    orders: Mapped[list["DiningOrder"]] = relationship("DiningOrder", back_populates="session")


class DiningOrder(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "dining_orders"
    __table_args__ = (
        Index("ix_dining_orders_session_id", "session_id"),
        UniqueConstraint("company_id", "branch_id", "idempotency_key", name="uq_dining_orders_idempotency"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dining_sessions.id"), nullable=False)
    order_number: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'qr_self'"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pricing_calculation_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pricing_calculation_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    pricing_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    session: Mapped["DiningSession"] = relationship("DiningSession", back_populates="orders")
    items: Mapped[list["DiningOrderItem"]] = relationship("DiningOrderItem", back_populates="order", cascade="all, delete-orphan")


class DiningOrderItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "dining_order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dining_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    special_request: Mapped[str | None] = mapped_column(String(500), nullable=True)
    station: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    original_price: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    vat_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'included'"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("7"))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    line_total: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    price_source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    price_list_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    price_list_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    price_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    order: Mapped["DiningOrder"] = relationship("DiningOrder", back_populates="items")
    product: Mapped["Product"] = relationship("Product")  # type: ignore[name-defined]


class KitchenTicket(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "kitchen_tickets"
    __table_args__ = (
        Index("ix_kitchen_tickets_branch_status", "branch_id", "status"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dining_sessions.id"), nullable=False, index=True)
    order_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dining_order_items.id"), nullable=False, unique=True)
    product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    special_request: Mapped[str | None] = mapped_column(String(500), nullable=True)
    station: Mapped[str | None] = mapped_column(String(50), nullable=True)
    queue_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    table_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    order_item: Mapped["DiningOrderItem"] = relationship("DiningOrderItem")


class RestaurantCancellation(UUIDMixin, Base):
    __tablename__ = "restaurant_cancellations"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "branch_id",
            "requester_id",
            "idempotency_key",
            name="uq_restaurant_cancellations_idempotency",
        ),
        CheckConstraint("target_type IN ('item', 'order')", name="target_type"),
        CheckConstraint("stage_before IN ('pending', 'cooking', 'done')", name="stage_before"),
        CheckConstraint("waste_disposition IN ('none', 'full')", name="waste_disposition"),
        CheckConstraint("waste_status IN ('not_required', 'posted')", name="waste_status"),
        Index(
            "ix_restaurant_cancellations_scope_created",
            "company_id",
            "brand_id",
            "branch_id",
            "created_at",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dining_sessions.id"), nullable=False, index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dining_orders.id"), nullable=False, index=True)
    order_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("dining_order_items.id"), nullable=True, index=True)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    stage_before: Mapped[str] = mapped_column(String(20), nullable=False)
    requester_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    approver_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    origin_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    origin_device_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    station_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason_code: Mapped[str] = mapped_column(String(50), nullable=False)
    reason_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    approval_policy_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    bill_impact: Mapped[dict] = mapped_column(JSON, nullable=False)
    waste_disposition: Mapped[str] = mapped_column(String(20), nullable=False)
    waste_status: Mapped[str] = mapped_column(String(20), nullable=False)
    stock_location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_locations.id"), nullable=True)
    approval_grant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approval_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    waste_lines: Mapped[list["RestaurantCancellationWaste"]] = relationship(
        "RestaurantCancellationWaste",
        back_populates="cancellation",
        order_by="RestaurantCancellationWaste.created_at.asc()",
    )
    kds_events: Mapped[list["KitchenCancellationEvent"]] = relationship(
        "KitchenCancellationEvent",
        back_populates="cancellation",
        order_by="KitchenCancellationEvent.created_at.asc()",
    )


class RestaurantCancellationWaste(UUIDMixin, Base):
    __tablename__ = "restaurant_cancellation_waste"
    __table_args__ = (
        UniqueConstraint("cancellation_id", "product_id", name="uq_restaurant_cancel_waste_product"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_restaurant_cancel_waste_scope", "company_id", "branch_id", "created_at"),
    )

    cancellation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurant_cancellations.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_locations.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    stock_movement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_movements.id"), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    cancellation: Mapped["RestaurantCancellation"] = relationship("RestaurantCancellation", back_populates="waste_lines")


class KitchenCancellationEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "kitchen_cancellation_events"
    __table_args__ = (
        UniqueConstraint("cancellation_id", "ticket_id", name="uq_kitchen_cancel_event_ticket"),
        CheckConstraint("status IN ('pending_ack', 'acknowledged')", name="status"),
        CheckConstraint("row_version >= 1", name="row_version_positive"),
        Index("ix_kitchen_cancel_events_queue", "company_id", "branch_id", "status", "created_at"),
    )

    cancellation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurant_cancellations.id"), nullable=False, index=True
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("kitchen_tickets.id"), nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    station: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reason_code: Mapped[str] = mapped_column(String(50), nullable=False)
    reason_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    ticket_status_before: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending_ack'"))
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    acknowledged_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cancellation: Mapped["RestaurantCancellation"] = relationship("RestaurantCancellation", back_populates="kds_events")
    ticket: Mapped["KitchenTicket"] = relationship("KitchenTicket")


class RestaurantCancellationAudit(UUIDMixin, Base):
    __tablename__ = "restaurant_cancellation_audits"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "branch_id",
            "action",
            "idempotency_key",
            name="uq_restaurant_cancel_audits_idempotency",
        ),
        Index("ix_restaurant_cancel_audits_cancellation", "cancellation_id", "created_at"),
        Index("ix_restaurant_cancel_audits_scope", "company_id", "branch_id", "created_at"),
    )

    cancellation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurant_cancellations.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approver_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    station_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    from_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    to_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'::json"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class WapShiftClosure(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "wap_shift_closures"
    __table_args__ = (
        Index("ix_wap_shift_closures_branch_date", "branch_id", "business_date"),
        Index("ix_wap_shift_closures_brand_branch_date_round", "brand_id", "branch_id", "business_date", "round_no"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id"), nullable=True, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    closed_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    business_date: Mapped[str] = mapped_column(String(10), nullable=False)
    round_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    total_orders: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["WapShiftClosureItem"]] = relationship(
        "WapShiftClosureItem",
        back_populates="closure",
        cascade="all, delete-orphan",
        order_by="WapShiftClosureItem.sort_order.asc()",
    )
    brand: Mapped["Brand | None"] = relationship("Brand")
    central_orders: Mapped[list["CentralOrder"]] = relationship(
        "CentralOrder",
        back_populates="shift_closure",
    )
    central_order_links: Mapped[list["CentralOrderShiftClosure"]] = relationship(
        "CentralOrderShiftClosure",
        back_populates="shift_closure",
        cascade="all, delete-orphan",
    )


class WapShiftClosureItem(UUIDMixin, Base):
    __tablename__ = "wap_shift_closure_items"
    __table_args__ = (
        Index("ix_wap_shift_closure_items_closure_type", "closure_id", "item_type"),
    )

    closure_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("wap_shift_closures.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(30), nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    unit: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'ชิ้น'"))
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    closure: Mapped["WapShiftClosure"] = relationship("WapShiftClosure", back_populates="items")
    product: Mapped["Product | None"] = relationship("Product")  # type: ignore[name-defined]


class CentralOrder(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "central_orders"
    __table_args__ = (
        Index("ix_central_orders_company_status", "company_id", "status"),
        Index("ix_central_orders_branch_status", "branch_id", "status"),
        UniqueConstraint("shift_closure_id", name="uq_central_orders_shift_closure"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id"), nullable=True, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    shift_closure_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("wap_shift_closures.id"), nullable=False, index=True)
    transfer_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("transfer_orders.id"), nullable=True, index=True)
    order_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'submitted'"))
    business_date: Mapped[str] = mapped_column(String(10), nullable=False)
    submitted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    packed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    shipped_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    received_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    packed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    credit_reserved_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    credit_captured_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    credit_released_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    shift_closure: Mapped["WapShiftClosure"] = relationship("WapShiftClosure", back_populates="central_orders")
    brand: Mapped["Brand | None"] = relationship("Brand")
    transfer_order: Mapped["TransferOrder | None"] = relationship("TransferOrder")  # type: ignore[name-defined]
    items: Mapped[list["CentralOrderItem"]] = relationship(
        "CentralOrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="CentralOrderItem.sort_order.asc()",
    )
    shift_closure_links: Mapped[list["CentralOrderShiftClosure"]] = relationship(
        "CentralOrderShiftClosure",
        back_populates="central_order",
        cascade="all, delete-orphan",
        order_by="CentralOrderShiftClosure.created_at.asc()",
    )


class CentralOrderShiftClosure(UUIDMixin, Base):
    __tablename__ = "central_order_shift_closures"
    __table_args__ = (
        UniqueConstraint("shift_closure_id", name="uq_central_order_shift_closures_closure"),
        Index("ix_central_order_shift_closures_order", "central_order_id"),
        Index("ix_central_order_shift_closures_branch_date", "branch_id", "business_date"),
    )

    central_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("central_orders.id", ondelete="CASCADE"), nullable=False)
    shift_closure_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("wap_shift_closures.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id"), nullable=True, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    business_date: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    central_order: Mapped["CentralOrder"] = relationship("CentralOrder", back_populates="shift_closure_links")
    shift_closure: Mapped["WapShiftClosure"] = relationship("WapShiftClosure", back_populates="central_order_links")


class CentralOrderItem(UUIDMixin, Base):
    __tablename__ = "central_order_items"
    __table_args__ = (
        Index("ix_central_order_items_order_id", "order_id"),
        Index("ix_central_order_items_product_id", "product_id"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("central_orders.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'ชิ้น'"))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    system_qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    requested_qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    approved_qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    shipped_qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    received_qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    approved_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    shipped_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    order: Mapped["CentralOrder"] = relationship("CentralOrder", back_populates="items")
    product: Mapped["Product | None"] = relationship("Product")  # type: ignore[name-defined]


class CreditAccount(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "credit_accounts"
    __table_args__ = (
        UniqueConstraint("brand_id", "branch_id", name="uq_credit_accounts_brand_branch"),
        Index("ix_credit_accounts_company_brand", "company_id", "brand_id"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    reserved_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    brand: Mapped["Brand"] = relationship("Brand")
    branch: Mapped["Branch"] = relationship("Branch")  # type: ignore[name-defined]
    ledger_entries: Mapped[list["CreditLedger"]] = relationship(
        "CreditLedger",
        back_populates="account",
        cascade="all, delete-orphan",
        order_by="CreditLedger.created_at.desc()",
    )


class CreditLedger(UUIDMixin, Base):
    __tablename__ = "credit_ledgers"
    __table_args__ = (
        Index("ix_credit_ledgers_account_created", "account_id", "created_at"),
        Index("ix_credit_ledgers_reference", "reference_type", "reference_id"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("credit_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    entry_type: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    reserved_after: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    account: Mapped["CreditAccount"] = relationship("CreditAccount", back_populates="ledger_entries")
    brand: Mapped["Brand"] = relationship("Brand")
    branch: Mapped["Branch"] = relationship("Branch")  # type: ignore[name-defined]


class CreditTopupRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "credit_topup_requests"
    __table_args__ = (
        Index("ix_credit_topup_requests_company_brand_status", "company_id", "brand_id", "status"),
        Index("ix_credit_topup_requests_branch_status", "branch_id", "status"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("credit_accounts.id"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'pending'"))
    slip_url: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    account: Mapped["CreditAccount"] = relationship("CreditAccount")
    brand: Mapped["Brand"] = relationship("Brand")
    branch: Mapped["Branch"] = relationship("Branch")  # type: ignore[name-defined]


class RecipeIngredient(UUIDMixin, Base):
    __tablename__ = "recipe_ingredients"
    __table_args__ = (
        Index("ix_recipe_ingredients_recipe_id", "recipe_id"),
        Index("ix_recipe_ingredients_ingredient_id", "ingredient_id"),
    )

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id"),
        nullable=False,
        comment="FK → products ที่มี product_type = raw_material",
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        comment="ปริมาณที่ใช้ต่อ 1 yield",
    )
    unit: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="g / ml / ชิ้น / ช้อนชา",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)

    recipe: Mapped["Recipe"] = relationship("Recipe", back_populates="ingredients")
    ingredient: Mapped["Product"] = relationship("Product", foreign_keys=[ingredient_id])  # type: ignore[name-defined]


class ProductionBatch(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "production_batches"
    __table_args__ = (
        UniqueConstraint("company_id", "batch_number", name="uq_production_batches_company_number"),
        CheckConstraint(
            "status IN ('draft', 'planned', 'in_progress', 'completed', 'cancelled')",
            name="ck_production_batches_status",
        ),
        CheckConstraint(
            "raw_location_id <> ready_location_id",
            name="ck_production_batches_distinct_locations",
        ),
        Index("ix_production_batches_company_brand_date", "company_id", "brand_id", "planned_date"),
        Index("ix_production_batches_brand_status", "brand_id", "status"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False)
    batch_number: Mapped[str] = mapped_column(String(50), nullable=False)
    planned_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'planned'"))
    raw_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stock_locations.id"),
        nullable=False,
        index=True,
    )
    ready_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stock_locations.id"),
        nullable=False,
        index=True,
    )
    planned_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    started_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    completed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    planned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    brand: Mapped["Brand"] = relationship("Brand")
    raw_location: Mapped["StockLocation"] = relationship(  # type: ignore[name-defined]
        "StockLocation",
        foreign_keys=[raw_location_id],
    )
    ready_location: Mapped["StockLocation"] = relationship(  # type: ignore[name-defined]
        "StockLocation",
        foreign_keys=[ready_location_id],
    )
    lines: Mapped[list["ProductionBatchLine"]] = relationship(
        "ProductionBatchLine",
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="ProductionBatchLine.sort_order.asc()",
    )


class ProductionBatchLine(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "production_batch_lines"
    __table_args__ = (
        CheckConstraint("line_type IN ('input', 'output')", name="ck_production_batch_lines_type"),
        CheckConstraint("planned_qty > 0", name="ck_production_batch_lines_planned_qty"),
        CheckConstraint(
            "actual_qty IS NULL OR actual_qty >= 0",
            name="ck_production_batch_lines_actual_qty",
        ),
        CheckConstraint(
            "(line_type = 'input' AND source_location_id IS NOT NULL AND destination_location_id IS NULL) "
            "OR (line_type = 'output' AND source_location_id IS NULL AND destination_location_id IS NOT NULL)",
            name="ck_production_batch_lines_location_direction",
        ),
        Index("ix_production_batch_lines_batch_type_order", "batch_id", "line_type", "sort_order"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("production_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_type: Mapped[str] = mapped_column(String(20), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    variant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("product_variants.id"), nullable=True)
    source_location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_locations.id"), nullable=True)
    destination_location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_locations.id"), nullable=True)
    planned_qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    actual_qty: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    unit_code: Mapped[str] = mapped_column(String(30), nullable=False)
    cost_per_unit: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    batch: Mapped["ProductionBatch"] = relationship("ProductionBatch", back_populates="lines")
    product: Mapped["Product"] = relationship("Product")  # type: ignore[name-defined]
    variant: Mapped["ProductVariant | None"] = relationship("ProductVariant")  # type: ignore[name-defined]
    source_location: Mapped["StockLocation | None"] = relationship(  # type: ignore[name-defined]
        "StockLocation",
        foreign_keys=[source_location_id],
    )
    destination_location: Mapped["StockLocation | None"] = relationship(  # type: ignore[name-defined]
        "StockLocation",
        foreign_keys=[destination_location_id],
    )


class StockCutoverRun(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "stock_cutover_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_stock_cutover_runs_status",
        ),
        Index("ix_stock_cutover_runs_company_brand", "company_id", "brand_id", "created_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_locations.id"), nullable=False, index=True
    )
    destination_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_locations.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'running'"))
    preview_token: Mapped[str] = mapped_column(String(64), nullable=False)
    preview_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    executed_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    brand: Mapped["Brand"] = relationship("Brand")
    source_location: Mapped["StockLocation"] = relationship(  # type: ignore[name-defined]
        "StockLocation", foreign_keys=[source_location_id]
    )
    destination_location: Mapped["StockLocation"] = relationship(  # type: ignore[name-defined]
        "StockLocation", foreign_keys=[destination_location_id]
    )
    items: Mapped[list["StockCutoverItem"]] = relationship(
        "StockCutoverItem",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="StockCutoverItem.created_at.asc()",
    )


class StockCutoverItem(UUIDMixin, Base):
    __tablename__ = "stock_cutover_items"
    __table_args__ = (
        UniqueConstraint("run_id", "product_id", "variant_id", name="uq_stock_cutover_item_product"),
        CheckConstraint("qty >= 0", name="ck_stock_cutover_items_qty_nonnegative"),
        Index("ix_stock_cutover_items_run", "run_id"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_cutover_runs.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_variants.id"), nullable=True
    )
    qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    cost_per_unit: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    source_qty_before: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    source_qty_after: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    destination_qty_before: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    destination_qty_after: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    source_movement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_movements.id"), nullable=False
    )
    destination_movement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_movements.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    run: Mapped["StockCutoverRun"] = relationship("StockCutoverRun", back_populates="items")
    product: Mapped["Product"] = relationship("Product")  # type: ignore[name-defined]
