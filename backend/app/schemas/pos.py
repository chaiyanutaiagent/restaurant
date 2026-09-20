from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
import uuid

from pydantic import ConfigDict, Field

from app.schemas import BaseSchema
from app.schemas.pricing import PriceOverrideIntent, PricingChannel


class OpenShiftRequest(BaseSchema):
    location_id: uuid.UUID
    opening_cash: Decimal = Decimal("0")


class CloseShiftRequest(BaseSchema):
    closing_cash: Decimal
    note: str | None = None


class ShiftRead(BaseSchema):
    id: uuid.UUID
    shift_number: str
    status: str
    branch_id: uuid.UUID
    location_id: uuid.UUID
    user_id: uuid.UUID
    opened_at: datetime
    closed_at: datetime | None = None
    opening_cash: Decimal
    closing_cash: Decimal | None = None
    expected_cash: Decimal | None = None
    cash_difference: Decimal | None = None
    total_sales: Decimal
    total_orders: int
    total_voids: int

    model_config = ConfigDict(from_attributes=True)


class CartItem(BaseSchema):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    qty: Decimal
    unit_price: Decimal
    original_price: Decimal
    discount_amount: Decimal = Decimal("0")
    discount_type: str = "amount"
    vat_type: str
    vat_rate: Decimal = Decimal("7")
    expected_price_version: str | None = None
    price_override: PriceOverrideIntent | None = None


class PaymentCreateRequest(BaseSchema):
    payment_method: str
    amount: Decimal
    reference_no: str | None = None


class CreateSaleRequest(BaseSchema):
    shift_id: uuid.UUID
    location_id: uuid.UUID
    items: list[CartItem] = Field(default_factory=list)
    discount_amount: Decimal = Decimal("0")
    discount_type: str = "amount"
    payment_method: str
    payments: list[PaymentCreateRequest] = Field(default_factory=list)
    payment_reference: str | None = None
    paid_amount: Decimal
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_tax_id: str | None = None
    customer_id: uuid.UUID | None = None
    note: str | None = None
    is_offline: bool = False
    client_order_id: str | None = None
    approval_token: str | None = None
    price_override_approval_token: str | None = None
    pricing_quote_id: uuid.UUID | None = None
    pricing_calculation_hash: str | None = Field(default=None, min_length=64, max_length=64)
    channel: PricingChannel = "pos"
    currency: str = Field(default="THB", min_length=3, max_length=3)
    cart_version: int = Field(default=1, ge=1)
    source_hold_draft_id: uuid.UUID | None = None
    source_hold_draft_version: int | None = Field(default=None, ge=1)


class PaymentRead(BaseSchema):
    id: uuid.UUID
    order_id: uuid.UUID
    payment_method: str
    amount: Decimal
    reference_no: str | None = None
    original_payment_id: uuid.UUID | None = None
    paid_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SaleOrderItemRead(BaseSchema):
    id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    product_name: str
    variant_name: str | None = None
    sku: str
    unit_code: str | None = None
    qty: Decimal
    unit_price: Decimal
    original_price: Decimal
    discount_amount: Decimal
    vat_type: str
    vat_rate: Decimal
    vat_amount: Decimal
    subtotal: Decimal
    refunded_qty: Decimal = Decimal("0")
    refunded_amount: Decimal = Decimal("0")
    price_source: str | None = None
    price_list_id: uuid.UUID | None = None
    price_list_version: int | None = None
    price_version: str | None = None
    price_snapshot: dict | None = None
    order_discount_share: Decimal = Decimal("0")
    line_total: Decimal = Decimal("0")
    price_override_applied: bool = False
    price_override_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SaleOrderRead(BaseSchema):
    id: uuid.UUID
    order_number: str
    status: str
    branch_id: uuid.UUID
    location_id: uuid.UUID
    shift_id: uuid.UUID
    user_id: uuid.UUID
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_tax_id: str | None = None
    subtotal: Decimal
    discount_amount: Decimal
    vat_amount: Decimal
    total_amount: Decimal
    refund_amount: Decimal = Decimal("0")
    paid_amount: Decimal
    change_amount: Decimal
    is_offline: bool
    synced_at: datetime | None = None
    recipe_stock_status: str | None = None
    recipe_stock_warnings: str | None = None
    recipe_stock_posted_at: datetime | None = None
    recipe_stock_reversed_at: datetime | None = None
    note: str | None = None
    pricing_quote_id: uuid.UUID | None = None
    pricing_request_hash: str | None = None
    pricing_calculation_hash: str | None = None
    pricing_calculation_version: str | None = None
    pricing_context: dict | None = None
    pricing_snapshot: dict | None = None
    row_version: int = 1
    created_at: datetime
    items: list[SaleOrderItemRead] = Field(default_factory=list)
    payments: list[PaymentRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class VoidRequest(BaseSchema):
    void_reason: str
    approval_token: str | None = None


class RefundRequest(BaseSchema):
    refund_reason: str
    approval_token: str | None = None


class PartialRefundItemRequest(BaseSchema):
    order_item_id: uuid.UUID
    qty: Decimal


class PartialRefundRequest(BaseSchema):
    refund_reason: str
    items: list[PartialRefundItemRequest] = Field(default_factory=list)
    approval_token: str | None = None


class ReceiptData(BaseSchema):
    order: SaleOrderRead
    company_name: str
    branch_name: str
    cashier_name: str
    receipt_footer: str = "ขอบคุณที่ใช้บริการ"


class SyncSalesRequest(BaseSchema):
    orders: list[CreateSaleRequest] = Field(default_factory=list)


class HoldDraftItemRequest(BaseSchema):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    qty: Decimal = Field(gt=0)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    discount_type: Literal["amount", "percent"] = "amount"
    expected_unit_price: Decimal | None = Field(default=None, ge=0)
    expected_price_version: str | None = Field(default=None, min_length=1, max_length=128)
    price_override: PriceOverrideIntent | None = None
    display_name: str | None = Field(default=None, max_length=500)
    display_variant_name: str | None = Field(default=None, max_length=255)
    display_sku: str | None = Field(default=None, max_length=100)
    display_unit_code: str | None = Field(default=None, max_length=20)


class HoldDraftCreateRequest(BaseSchema):
    shift_id: uuid.UUID
    location_id: uuid.UUID
    label: str = Field(min_length=1, max_length=160)
    source_type: Literal["walk_in", "takeaway", "restaurant_table", "restaurant_quick_service"] = "walk_in"
    table_id: uuid.UUID | None = None
    queue_label: str | None = Field(default=None, max_length=80)
    customer_id: uuid.UUID | None = None
    customer_display: str | None = Field(default=None, max_length=160)
    note: str | None = Field(default=None, max_length=1000)
    items: list[HoldDraftItemRequest] = Field(min_length=1, max_length=100)
    order_discount: Decimal = Field(default=Decimal("0"), ge=0)
    loyalty_discount_intent: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="THB", min_length=3, max_length=3)
    cart_version: int = Field(default=1, ge=1)
    idempotency_key: str = Field(min_length=8, max_length=100)


class HoldDraftUpdateRequest(BaseSchema):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=100)
    label: str | None = Field(default=None, min_length=1, max_length=160)
    note: str | None = Field(default=None, max_length=1000)
    assignee_user_id: uuid.UUID | None = None
    reason: str | None = Field(default=None, max_length=500)
    items: list[HoldDraftItemRequest] | None = Field(default=None, min_length=1, max_length=100)
    order_discount: Decimal | None = Field(default=None, ge=0)
    loyalty_discount_intent: Decimal | None = Field(default=None, ge=0)
    cart_version: int | None = Field(default=None, ge=1)


class HoldDraftActionRequest(BaseSchema):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=100)
    shift_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    claim_id: uuid.UUID | None = None
    accept_revalidation: bool = False
    reason: str | None = Field(default=None, max_length=500)


class HoldDraftRead(BaseSchema):
    id: uuid.UUID
    draft_no: str
    company_id: uuid.UUID
    brand_id: uuid.UUID | None = None
    branch_id: uuid.UUID
    location_id: uuid.UUID
    origin_shift_id: uuid.UUID
    owner_user_id: uuid.UUID
    assignee_user_id: uuid.UUID | None = None
    origin_device_id: uuid.UUID | None = None
    origin_device_code: str | None = None
    parent_draft_id: uuid.UUID | None = None
    converted_order_id: uuid.UUID | None = None
    label: str
    source_type: str
    table_id: uuid.UUID | None = None
    queue_label: str | None = None
    customer_id: uuid.UUID | None = None
    customer_display: str | None = None
    note: str | None = None
    content: dict[str, Any]
    pricing_context: dict[str, Any]
    pricing_snapshot: dict[str, Any]
    last_revalidation: dict[str, Any] | None = None
    status: Literal["active", "claimed", "resumed", "expired", "converted", "cancelled"]
    version: int
    claim_id: uuid.UUID | None = None
    claimed_by: uuid.UUID | None = None
    claimed_device_id: uuid.UUID | None = None
    claim_expires_at: datetime | None = None
    expires_at: datetime
    resumed_at: datetime | None = None
    resumed_by: uuid.UUID | None = None
    expired_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    converted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class HoldDraftClaimRead(BaseSchema):
    draft: HoldDraftRead
    resume_cart: dict[str, Any]
    price_changes: list[dict[str, Any]] = Field(default_factory=list)
    requires_review: bool = False
