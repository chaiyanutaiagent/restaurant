from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
import uuid

from pydantic import Field, field_validator

from app.schemas import BaseSchema


PricingChannel = Literal[
    "pos",
    "restaurant_table",
    "restaurant_qr",
    "restaurant_quick_service",
    "retail",
    "takeaway",
]


class PriceOverrideIntent(BaseSchema):
    requested_unit_price: Decimal = Field(ge=0)
    reason_code: Literal[
        "customer_recovery",
        "price_match",
        "manager_comp",
        "damaged_item",
        "manual_correction",
        "other",
    ] = "other"
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class PricingLineRequest(BaseSchema):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    qty: Decimal = Field(gt=0)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    discount_type: Literal["amount", "percent"] = "amount"
    expected_unit_price: Decimal | None = Field(default=None, ge=0)
    expected_price_version: str | None = Field(default=None, min_length=1, max_length=128)
    price_override: PriceOverrideIntent | None = None


class PricingCalculateRequest(BaseSchema):
    items: list[PricingLineRequest] = Field(min_length=1, max_length=100)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    discount_type: Literal["amount", "percent"] = "amount"
    channel: PricingChannel = "pos"
    currency: str = Field(default="THB", min_length=3, max_length=3)
    customer_id: uuid.UUID | None = None
    idempotency_key: str = Field(min_length=8, max_length=100)
    cart_version: int = Field(default=1, ge=1)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class PricingLineRead(BaseSchema):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    product_name: str
    sku: str
    qty: Decimal
    authoritative_unit_price: Decimal
    applied_unit_price: Decimal
    promotion_code: str | None = None
    promotion_discount_amount: Decimal = Decimal("0")
    line_discount_amount: Decimal
    order_discount_share: Decimal
    vat_type: str
    vat_rate: Decimal
    vat_amount: Decimal
    line_subtotal: Decimal
    line_total: Decimal
    price_source: str
    price_list_id: uuid.UUID | None = None
    price_list_version: int
    price_version: str
    effective_at: datetime
    rounding_rule: str = "THB_HALF_UP_0.01"
    discrepancy: bool = False
    override_requested: bool = False
    override_requires_approval: bool = False
    override_deviation_pct: Decimal = Decimal("0")


class PricingCalculationRead(BaseSchema):
    quote_id: uuid.UUID
    idempotency_key: str
    request_hash: str
    calculation_hash: str
    calculation_version: str
    cart_version: int
    company_id: uuid.UUID
    brand_id: uuid.UUID | None = None
    branch_id: uuid.UUID
    channel: PricingChannel
    currency: str
    price_list_id: uuid.UUID | None = None
    price_list_version: int
    subtotal: Decimal
    line_discount_amount: Decimal
    order_discount_amount: Decimal
    discount_amount: Decimal
    promotion_discount_amount: Decimal = Decimal("0")
    discount_percentage: Decimal
    vat_amount: Decimal
    total_amount: Decimal
    rounding_rule: str = "THB_HALF_UP_0.01"
    effective_at: datetime
    expires_at: datetime
    status: Literal["quoted", "consumed"] = "quoted"
    requires_price_override_approval: bool = False
    has_price_discrepancy: bool = False
    lines: list[PricingLineRead] = Field(default_factory=list)
