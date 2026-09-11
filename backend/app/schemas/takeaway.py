from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
import uuid

from pydantic import Field, field_validator, model_validator

from app.schemas import BaseSchema


def _text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value is required")
    return normalized


class TakeawayCategoryCreate(BaseSchema):
    brand_id: uuid.UUID
    code: str = Field(max_length=60)
    name: str = Field(max_length=200)
    sort_order: int = Field(default=0, ge=0)

    _normalize_code = field_validator("code")(_text)
    _normalize_name = field_validator("name")(_text)


class TakeawayCatalogItemCreate(BaseSchema):
    brand_id: uuid.UUID
    category_id: uuid.UUID | None = None
    sku: str = Field(max_length=100)
    barcode: str | None = Field(default=None, max_length=100)
    name: str = Field(max_length=300)
    unit: str = Field(default="ชิ้น", max_length=40)
    price: Decimal = Field(ge=0, decimal_places=2)
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    kitchen_station: str | None = Field(default=None, max_length=80)
    track_stock: bool = True

    _normalize_sku = field_validator("sku")(_text)
    _normalize_name = field_validator("name")(_text)
    _normalize_unit = field_validator("unit")(_text)


class TakeawayBranchAvailabilityUpdate(BaseSchema):
    price_override: Decimal | None = Field(default=None, ge=0)
    is_available: bool


class TakeawayShiftOpen(BaseSchema):
    business_date: date
    opening_cash: Decimal = Field(default=Decimal("0"), ge=0)


class TakeawayShiftClose(BaseSchema):
    counted_cash: Decimal = Field(ge=0)
    note: str | None = Field(default=None, max_length=500)


class TakeawaySaleLine(BaseSchema):
    catalog_item_id: uuid.UUID
    quantity: Decimal = Field(gt=0, decimal_places=4)
    note: str | None = Field(default=None, max_length=500)


class TakeawayPaymentCreate(BaseSchema):
    method: Literal["cash", "promptpay", "card", "credit", "other"]
    amount: Decimal = Field(gt=0, decimal_places=2)
    reference: str | None = Field(default=None, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=160)


class TakeawaySaleCreate(BaseSchema):
    brand_id: uuid.UUID
    branch_id: uuid.UUID
    shift_id: uuid.UUID
    idempotency_key: str = Field(min_length=8, max_length=160)
    channel: Literal["counter", "qr", "online"] = "counter"
    items: list[TakeawaySaleLine] = Field(min_length=1, max_length=100)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    payment: TakeawayPaymentCreate
    customer_name: str | None = Field(default=None, max_length=200)
    customer_phone: str | None = Field(default=None, max_length=40)
    note: str | None = Field(default=None, max_length=1000)
    offline_device_id: uuid.UUID | None = None
    offline_sequence: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_offline_pair(self) -> "TakeawaySaleCreate":
        if (self.offline_device_id is None) != (self.offline_sequence is None):
            raise ValueError("offline device and sequence must be supplied together")
        return self


class TakeawayOrderingLinkCreate(BaseSchema):
    expires_in_hours: int = Field(default=12, ge=1, le=168)


class TakeawayPublicOrderCreate(BaseSchema):
    idempotency_key: str = Field(min_length=8, max_length=160)
    items: list[TakeawaySaleLine] = Field(min_length=1, max_length=100)
    customer_name: str | None = Field(default=None, max_length=200)
    customer_phone: str | None = Field(default=None, max_length=40)
    note: str | None = Field(default=None, max_length=1000)


class TakeawayOrderPaymentCapture(BaseSchema):
    payment: TakeawayPaymentCreate


class TakeawayOrderStatusUpdate(BaseSchema):
    status: Literal["preparing", "ready"]


class TakeawayRefundCreate(BaseSchema):
    idempotency_key: str = Field(min_length=8, max_length=160)
    reason: str = Field(min_length=1, max_length=500)


class TakeawayCentralRoundCreate(BaseSchema):
    brand_id: uuid.UUID
    business_date: date
    round_no: int = Field(ge=1)


class TakeawayCentralOrderLineCreate(BaseSchema):
    catalog_item_id: uuid.UUID | None = None
    sku: str | None = Field(default=None, max_length=100)
    item_name: str = Field(max_length=300)
    quantity: Decimal = Field(gt=0, decimal_places=4)
    unit: str = Field(max_length=40)
    source_kind: Literal["catalog", "extra", "unlisted"] = "catalog"

    _normalize_name = field_validator("item_name")(_text)
    _normalize_unit = field_validator("unit")(_text)


class TakeawayCentralOrderCreate(BaseSchema):
    brand_id: uuid.UUID
    branch_id: uuid.UUID
    round_id: uuid.UUID
    order_type: Literal["regular", "extra", "unlisted"] = "regular"
    requested_delivery_date: date | None = None
    items: list[TakeawayCentralOrderLineCreate] = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=1000)


class TakeawayCentralOrderStatusUpdate(BaseSchema):
    status: Literal["approved", "rejected", "in_production", "packed", "shipped", "received"]


class TakeawayProductionLineCreate(BaseSchema):
    item_id: uuid.UUID
    line_type: Literal["input", "output"]
    planned_qty: Decimal = Field(gt=0, decimal_places=4)
    unit: str = Field(max_length=40)

    _normalize_unit = field_validator("unit")(_text)


class TakeawayProductionBatchCreate(BaseSchema):
    brand_id: uuid.UUID
    location_id: uuid.UUID
    planned_at: date | None = None
    lines: list[TakeawayProductionLineCreate] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def require_input_and_output(self) -> "TakeawayProductionBatchCreate":
        kinds = {line.line_type for line in self.lines}
        if kinds != {"input", "output"}:
            raise ValueError("production requires at least one input and one output")
        return self


class TakeawayProductionCompleteLine(BaseSchema):
    line_id: uuid.UUID
    actual_qty: Decimal = Field(gt=0, decimal_places=4)


class TakeawayProductionComplete(BaseSchema):
    lines: list[TakeawayProductionCompleteLine] = Field(min_length=2, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=160)


class TakeawayStockMovementCreate(BaseSchema):
    location_id: uuid.UUID
    item_id: uuid.UUID
    lot_code: str = Field(default="", max_length=100)
    quantity_delta: Decimal = Field(decimal_places=4)
    unit_cost: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=4)
    movement_type: Literal["receive", "adjust", "waste"]
    brand_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    idempotency_key: str = Field(min_length=8, max_length=180)

    @field_validator("quantity_delta")
    @classmethod
    def nonzero_quantity(cls, value: Decimal) -> Decimal:
        if value == 0:
            raise ValueError("quantity_delta must not be zero")
        return value


class TakeawayTransferLineCreate(BaseSchema):
    item_id: uuid.UUID
    requested_qty: Decimal = Field(gt=0, decimal_places=4)
    unit: str = Field(max_length=40)


class TakeawayTransferCreate(BaseSchema):
    brand_id: uuid.UUID | None = None
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    items: list[TakeawayTransferLineCreate] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def different_locations(self) -> "TakeawayTransferCreate":
        if self.from_location_id == self.to_location_id:
            raise ValueError("transfer locations must be different")
        return self


class TakeawayTransferStatusUpdate(BaseSchema):
    status: Literal["shipped", "received", "cancelled"]
    idempotency_key: str = Field(min_length=8, max_length=180)


class TakeawayCreditLimitUpdate(BaseSchema):
    brand_id: uuid.UUID
    branch_id: uuid.UUID
    credit_limit: Decimal = Field(ge=0, decimal_places=2)


class TakeawayCreditEntryCreate(BaseSchema):
    entry_type: Literal["charge", "payment", "adjustment"]
    amount: Decimal = Field(gt=0, decimal_places=2)
    reference_type: str = Field(min_length=1, max_length=40)
    reference_id: uuid.UUID
    idempotency_key: str = Field(min_length=8, max_length=180)


class TakeawayImportDryRun(BaseSchema):
    manifest: dict[str, object]
    mapping: dict[str, object]
    records: list[dict[str, object]] = Field(max_length=10000)


class TakeawayErpEventAcknowledge(BaseSchema):
    idempotency_key: str = Field(min_length=8, max_length=180)
    erp_reference: str = Field(min_length=1, max_length=180)
