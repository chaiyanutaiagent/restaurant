from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class TakeawayReferenceProjection(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_reference_projections"
    __table_args__ = (
        UniqueConstraint(
            "aggregate_type",
            "aggregate_id",
            name="uq_takeaway_reference_projection_aggregate",
        ),
        CheckConstraint(
            "aggregate_type IN ('company', 'brand', 'branch', 'brand_branch', 'user')",
            name="ck_takeaway_reference_projection_type",
        ),
    )

    aggregate_type: Mapped[str] = mapped_column(String(40), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class TakeawayCategory(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_categories"
    __table_args__ = (
        UniqueConstraint("company_id", "brand_id", "code", name="uq_takeaway_category_code"),
        Index("ix_takeaway_categories_scope", "company_id", "brand_id", "is_active"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class TakeawayUnit(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_units"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_takeaway_unit_code"),
        CheckConstraint("decimal_places BETWEEN 0 AND 6", name="ck_takeaway_unit_decimal_places"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decimal_places: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class TakeawayCatalogItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_catalog_items"
    __table_args__ = (
        UniqueConstraint("company_id", "brand_id", "sku", name="uq_takeaway_catalog_item_sku"),
        Index("ix_takeaway_catalog_items_scope", "company_id", "brand_id", "is_active"),
        CheckConstraint("price >= 0", name="ck_takeaway_catalog_item_price"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'ชิ้น'"))
    price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False, server_default=text("0"))
    kitchen_station: Mapped[str | None] = mapped_column(String(80), nullable=True)
    track_stock: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    source_metadata: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)


class TakeawayBranchCatalogItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_branch_catalog_items"
    __table_args__ = (
        UniqueConstraint("branch_id", "catalog_item_id", name="uq_takeaway_branch_catalog_item"),
        Index("ix_takeaway_branch_catalog_scope", "company_id", "brand_id", "branch_id"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    catalog_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    price_override: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class TakeawayStockLocation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_stock_locations"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "branch_id",
            "code",
            name="uq_takeaway_stock_location_code",
        ),
        CheckConstraint(
            "location_type IN ('central_raw', 'central_ready', 'store', 'transit', 'waste')",
            name="ck_takeaway_stock_location_type",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location_type: Mapped[str] = mapped_column(String(30), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class TakeawayRecipe(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_recipes"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "brand_id",
            "output_item_id",
            "branch_id",
            "version_no",
            name="uq_takeaway_recipe_version",
        ),
        CheckConstraint("yield_qty > 0", name="ck_takeaway_recipe_yield"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    output_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recipe_type: Mapped[str] = mapped_column(String(30), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    yield_qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    yield_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    loss_percent: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class TakeawayRecipeIngredient(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_recipe_ingredients"
    __table_args__ = (
        UniqueConstraint("recipe_id", "item_id", name="uq_takeaway_recipe_ingredient"),
        CheckConstraint("quantity > 0", name="ck_takeaway_recipe_ingredient_qty"),
    )

    recipe_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class TakeawayReplenishmentPolicy(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_replenishment_policies"
    __table_args__ = (
        UniqueConstraint("brand_id", "branch_id", "item_id", name="uq_takeaway_replenishment_policy"),
        CheckConstraint("pack_size > 0", name="ck_takeaway_replenishment_pack_size"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    safety_stock_percent: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    safety_stock_qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    pack_size: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("1"))
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    forecast_method: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'auto'"))
    minimum_order_qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))


class TakeawayShift(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_shifts"
    __table_args__ = (
        UniqueConstraint("branch_id", "business_date", "round_no", name="uq_takeaway_shift_round"),
        Index("ix_takeaway_shifts_scope_status", "company_id", "brand_id", "branch_id", "status"),
        CheckConstraint("status IN ('open', 'closed')", name="ck_takeaway_shift_status"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    round_no: Mapped[int] = mapped_column(Integer, nullable=False)
    opened_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    opening_cash: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'open'"))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_cash: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    counted_cash: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    close_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class TakeawayOrder(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_orders"
    __table_args__ = (
        UniqueConstraint("branch_id", "order_number", name="uq_takeaway_order_number"),
        UniqueConstraint("branch_id", "idempotency_key", name="uq_takeaway_order_idempotency"),
        Index("ix_takeaway_orders_scope_status", "company_id", "brand_id", "branch_id", "status"),
        Index("ix_takeaway_orders_queue", "branch_id", "business_date", "queue_number"),
        CheckConstraint("channel IN ('counter', 'qr', 'online', 'import')", name="ck_takeaway_order_channel"),
        CheckConstraint("status IN ('draft', 'paid', 'cancelled', 'refunded')", name="ck_takeaway_order_status"),
        CheckConstraint(
            "fulfillment_status IN ('awaiting_payment', 'queued', 'preparing', 'ready', 'picked_up', 'cancelled')",
            name="ck_takeaway_order_fulfillment_status",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    shift_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    order_number: Mapped[str] = mapped_column(String(60), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    queue_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'counter'"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'draft'"))
    fulfillment_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'awaiting_payment'"))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    offline_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    offline_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_metadata: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)


class TakeawayOrderItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_order_items"
    __table_args__ = (
        Index("ix_takeaway_order_items_order", "order_id"),
        CheckConstraint("quantity > 0", name="ck_takeaway_order_item_quantity"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    catalog_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    line_total: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    kitchen_station: Mapped[str | None] = mapped_column(String(80), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class TakeawayPayment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_payments"
    __table_args__ = (
        UniqueConstraint("order_id", "idempotency_key", name="uq_takeaway_payment_idempotency"),
        CheckConstraint("amount > 0", name="ck_takeaway_payment_amount"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'captured'"))
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class TakeawayReceipt(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_receipts"
    __table_args__ = (
        UniqueConstraint("receipt_number", name="uq_takeaway_receipt_number"),
        CheckConstraint(
            "last_printed_copy IS NULL OR last_printed_copy IN ('customer', 'merchant')",
            name="ck_takeaway_receipt_print_copy",
        ),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    receipt_number: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    print_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_printed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_printed_copy: Mapped[str | None] = mapped_column(String(20), nullable=True)


class TakeawayKitchenTicket(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_kitchen_tickets"
    __table_args__ = (
        UniqueConstraint("order_item_id", name="uq_takeaway_kitchen_order_item"),
        Index("ix_takeaway_kitchen_queue", "branch_id", "station", "status"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    order_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    queue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    station: Mapped[str] = mapped_column(String(80), nullable=False, server_default=text("'default'"))
    item_name: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'queued'"))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TakeawayPickupToken(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_pickup_tokens"

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TakeawayOrderingToken(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_ordering_tokens"
    __table_args__ = (
        Index("ix_takeaway_ordering_token_scope", "company_id", "brand_id", "branch_id"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class TakeawayCentralOrderRound(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_central_order_rounds"
    __table_args__ = (
        UniqueConstraint("brand_id", "business_date", "round_no", name="uq_takeaway_central_round"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    round_no: Mapped[int] = mapped_column(Integer, nullable=False)
    cutoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'open'"))


class TakeawayCentralOrder(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_central_orders"
    __table_args__ = (
        UniqueConstraint("branch_id", "order_number", name="uq_takeaway_central_order_number"),
        UniqueConstraint("branch_id", "idempotency_key", name="uq_takeaway_central_order_idempotency"),
        Index("ix_takeaway_central_orders_status", "company_id", "brand_id", "status"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    round_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    order_number: Mapped[str] = mapped_column(String(80), nullable=False)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'regular'"))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'submitted'"))
    requested_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    submitted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    discrepancy_status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'none'")
    )
    receipt_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class TakeawayCentralOrderItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_central_order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_takeaway_central_item_quantity"),)

    central_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    catalog_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    item_name: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'catalog'"))
    approval_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    approved_qty: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    packed_qty: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    shipped_qty: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    received_qty: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    discrepancy_qty: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False, server_default=text("0")
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class TakeawayProductionBatch(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_production_batches"
    __table_args__ = (UniqueConstraint("company_id", "batch_number", name="uq_takeaway_production_batch"),)

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    batch_number: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'planned'"))
    planned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class TakeawayProductionLine(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_production_lines"
    __table_args__ = (CheckConstraint("planned_qty > 0", name="ck_takeaway_production_line_qty"),)

    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    line_type: Mapped[str] = mapped_column(String(20), nullable=False)
    planned_qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    actual_qty: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    waste_qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    unit: Mapped[str] = mapped_column(String(40), nullable=False)


class TakeawayStockBalance(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_stock_balances"
    __table_args__ = (
        UniqueConstraint("company_id", "location_id", "item_id", "lot_code", name="uq_takeaway_stock_balance"),
        CheckConstraint("on_hand_qty >= 0", name="ck_takeaway_stock_on_hand"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lot_code: Mapped[str] = mapped_column(String(100), nullable=False, server_default=text("''"))
    on_hand_qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    reserved_qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    average_cost: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))


class TakeawayStockMovement(UUIDMixin, Base):
    __tablename__ = "takeaway_stock_movements"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_takeaway_stock_movement_idempotency"),
        Index("ix_takeaway_stock_movements_item", "company_id", "location_id", "item_id", "occurred_at"),
        CheckConstraint("quantity_delta <> 0", name="ck_takeaway_stock_movement_nonzero"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lot_code: Mapped[str] = mapped_column(String(100), nullable=False, server_default=text("''"))
    brand_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    production_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    movement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class TakeawayTransfer(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_transfers"
    __table_args__ = (UniqueConstraint("company_id", "transfer_number", name="uq_takeaway_transfer_number"),)

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    transfer_number: Mapped[str] = mapped_column(String(80), nullable=False)
    from_location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    to_location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'draft'"))
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discrepancy_status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'none'")
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class TakeawayTransferItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_transfer_items"
    __table_args__ = (CheckConstraint("requested_qty > 0", name="ck_takeaway_transfer_item_qty"),)

    transfer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requested_qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    shipped_qty: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    received_qty: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    discrepancy_qty: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False, server_default=text("0")
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)


class TakeawayCreditAccount(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_credit_accounts"
    __table_args__ = (
        UniqueConstraint("company_id", "brand_id", "branch_id", name="uq_takeaway_credit_account"),
        CheckConstraint("credit_limit >= 0", name="ck_takeaway_credit_limit"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))


class TakeawayCreditEntry(UUIDMixin, Base):
    __tablename__ = "takeaway_credit_entries"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_takeaway_credit_entry_idempotency"),)

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reference_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class TakeawayCreditTopupRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_credit_topup_requests"
    __table_args__ = (
        UniqueConstraint("account_id", "idempotency_key", name="uq_takeaway_credit_topup_idempotency"),
        CheckConstraint("amount > 0", name="ck_takeaway_credit_topup_amount"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    payment_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    evidence_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class TakeawayCreditPaymentConfig(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_credit_payment_configs"
    __table_args__ = (
        UniqueConstraint("company_id", "brand_id", name="uq_takeaway_credit_payment_config"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    promptpay_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    promptpay_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bank_account_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class TakeawayOperationalOutbox(UUIDMixin, Base):
    __tablename__ = "takeaway_operational_outbox"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_takeaway_outbox_idempotency"),)

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    contract_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class TakeawayImportBatch(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_import_batches"
    __table_args__ = (UniqueConstraint("manifest_digest", name="uq_takeaway_import_manifest_digest"),)

    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    manifest_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'dry_run'"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    total_records: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    accepted_records: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    rejected_records: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    report: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)


class TakeawayImportRecord(UUIDMixin, Base):
    __tablename__ = "takeaway_import_records"
    __table_args__ = (
        UniqueConstraint("batch_id", "source_type", "source_id", name="uq_takeaway_import_record_source"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(60), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class TakeawayHistoricalArchive(UUIDMixin, Base):
    __tablename__ = "takeaway_historical_archive"
    __table_args__ = (
        UniqueConstraint("import_batch_id", "record_type", "source_id", name="uq_takeaway_history_source"),
        Index("ix_takeaway_history_scope", "company_id", "brand_id", "record_type"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    import_batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    record_type: Mapped[str] = mapped_column(String(60), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    business_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class TakeawayCutoverRun(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "takeaway_cutover_runs"
    __table_args__ = (
        UniqueConstraint("company_id", "execution_key", name="uq_takeaway_cutover_execution_key"),
        Index("ix_takeaway_cutover_scope", "company_id", "brand_id", "created_at"),
        CheckConstraint(
            "status IN ('completed', 'failed', 'rollback_requested', 'rolled_back')",
            name="ck_takeaway_cutover_status",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    execution_key: Mapped[str] = mapped_column(String(180), nullable=False)
    export_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    manifest_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    preview_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    approved_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approval_reference: Mapped[str] = mapped_column(String(300), nullable=False)
    backup_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    rollback_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    report: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    reconciliation: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rollback_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
