from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
import uuid

from pydantic import ConfigDict, Field, model_validator

from app.schemas import BaseSchema
from app.schemas.pricing import PriceOverrideIntent, PricingChannel


class OpenShiftRequest(BaseSchema):
    location_id: uuid.UUID
    opening_cash: Decimal = Field(default=Decimal("0"), ge=0)
    shift_type: Literal["staff_cashier", "operational_cashless"] = "staff_cashier"
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)


class CashDenominationCount(BaseSchema):
    denomination: Decimal = Field(gt=0)
    quantity: int = Field(ge=0, le=10000)


ShiftVarianceReason = Literal[
    "count_short",
    "count_over",
    "change_error",
    "cash_movement",
    "other",
]


class CloseShiftRequest(BaseSchema):
    closing_cash: Decimal = Field(ge=0)
    reason_code: ShiftVarianceReason | None = None
    note: str | None = Field(default=None, max_length=500)
    cash_count: list[CashDenominationCount] = Field(default_factory=list, max_length=20)
    expected_version: int | None = Field(default=None, ge=1)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)
    approval_token: str | None = None

    @model_validator(mode="after")
    def validate_cash_count(self) -> "CloseShiftRequest":
        if self.cash_count:
            counted = sum(
                (Decimal(item.denomination) * item.quantity for item in self.cash_count),
                Decimal("0"),
            ).quantize(Decimal("0.01"))
            if counted != Decimal(self.closing_cash).quantize(Decimal("0.01")):
                raise ValueError("Cash denomination total must equal closing cash")
        return self


CashMovementType = Literal["cash_in", "cash_out"]
CashMovementReason = Literal[
    "change_fund",
    "cash_drop",
    "petty_cash",
    "supplier_payment",
    "correction",
    "other",
]


class CashMovementCreateRequest(BaseSchema):
    movement_type: CashMovementType
    amount: Decimal = Field(gt=0)
    reason_code: CashMovementReason
    reason: str = Field(min_length=3, max_length=500)
    expected_shift_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=100)
    approval_token: str | None = None


class ShiftRead(BaseSchema):
    id: uuid.UUID
    shift_number: str
    shift_type: str = "staff_cashier"
    version: int = 1
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
    close_reason_code: str | None = None
    cash_count_json: list[dict[str, Any]] | None = None
    opened_device_id: uuid.UUID | None = None
    opened_device_code: str | None = None
    closed_device_id: uuid.UUID | None = None
    closed_device_code: str | None = None
    closed_by_user_id: uuid.UUID | None = None
    close_snapshot_json: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class CashMovementRead(BaseSchema):
    id: uuid.UUID
    shift_id: uuid.UUID
    movement_type: str
    amount: Decimal
    reason_code: str
    reason: str
    status: str
    shift_version: int
    requester_id: uuid.UUID
    approver_id: uuid.UUID | None = None
    device_code: str | None = None
    journal_entry_id: uuid.UUID | None = None
    posted_at: datetime

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
    currency: str = "THB"
    provider_name: str | None = None
    provider_payment_ref: str | None = None
    settlement_state: str = "unknown"
    refund_operation_id: uuid.UUID | None = None
    provider_refund_state: str | None = None
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


RefundReasonCode = Literal[
    "customer_request",
    "wrong_item",
    "quality_issue",
    "duplicate_charge",
    "payment_error",
    "other",
]


class RefundQuoteItemRequest(BaseSchema):
    order_item_id: uuid.UUID
    qty: Decimal = Field(gt=0)


class RefundQuoteCreateRequest(BaseSchema):
    order_id: uuid.UUID
    shift_id: uuid.UUID
    items: list[RefundQuoteItemRequest] = Field(default_factory=list, max_length=100)
    reason_code: RefundReasonCode
    reason_note: str | None = Field(default=None, max_length=500)
    stock_disposition: Literal["none", "sellable"] = "none"
    currency: str = Field(default="THB", min_length=3, max_length=3)
    idempotency_key: str = Field(min_length=8, max_length=100)

    @model_validator(mode="after")
    def validate_other_reason(self) -> "RefundQuoteCreateRequest":
        if self.reason_code == "other" and len((self.reason_note or "").strip()) < 3:
            raise ValueError("reason_note is required when reason_code is other")
        return self


class RefundExecuteRequest(BaseSchema):
    quote_id: uuid.UUID
    quote_hash: str = Field(min_length=64, max_length=64)
    order_id: uuid.UUID
    expected_order_version: int = Field(ge=1)
    total_amount: Decimal = Field(gt=0)
    reason_code: RefundReasonCode
    reason_note: str | None = Field(default=None, max_length=500)
    stock_disposition: Literal["none", "sellable"] = "none"
    provider_scenario: Literal[
        "succeeded",
        "failed",
        "processing_then_succeeded",
        "unknown_then_succeeded",
        "unknown_persistent",
    ] = "succeeded"
    idempotency_key: str = Field(min_length=8, max_length=100)
    approval_token: str | None = None

    @model_validator(mode="after")
    def validate_other_reason(self) -> "RefundExecuteRequest":
        if self.reason_code == "other" and len((self.reason_note or "").strip()) < 3:
            raise ValueError("reason_note is required when reason_code is other")
        return self


class RefundOperationActionRequest(BaseSchema):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=100)


class RefundProviderWebhookRequest(BaseSchema):
    provider_event_id: str = Field(min_length=8, max_length=160)
    payment_leg_id: uuid.UUID
    sequence: int = Field(ge=1)
    state: Literal["processing", "succeeded", "failed", "unknown"]
    provider_refund_ref: str | None = Field(default=None, max_length=255)
    error_code: str | None = Field(default=None, max_length=80)


class RefundQuoteRead(BaseSchema):
    id: uuid.UUID
    order_id: uuid.UUID
    shift_id: uuid.UUID
    status: str
    currency: str
    order_version: int
    quote_hash: str
    items: list[dict[str, Any]]
    payment_allocations: list[dict[str, Any]]
    totals: dict[str, Any]
    policy: dict[str, Any]
    expires_at: datetime


class RefundOperationRead(BaseSchema):
    id: uuid.UUID
    order_id: uuid.UUID
    quote_id: uuid.UUID
    shift_id: uuid.UUID
    status: str
    reason_code: str
    reason_note: str | None
    currency: str
    subtotal_amount: Decimal
    discount_amount: Decimal
    vat_amount: Decimal
    rounding_amount: Decimal
    total_amount: Decimal
    stock_disposition: str
    provider_scenario: str
    row_version: int
    failure_code: str | None
    failure_message: str | None
    finalized_at: datetime | None
    tax_completed_at: datetime | None
    items: list[dict[str, Any]]
    payment_legs: list[dict[str, Any]]
    tax: dict[str, Any] | None
    created_at: datetime


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
    owner_display: str | None = None
    assignee_user_id: uuid.UUID | None = None
    assignee_display: str | None = None
    origin_device_id: uuid.UUID | None = None
    origin_device_code: str | None = None
    origin_shift_number: str | None = None
    location_name: str | None = None
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
