from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import uuid

from pydantic import ConfigDict, Field

from app.schemas import BaseSchema


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


class PaymentRead(BaseSchema):
    id: uuid.UUID
    order_id: uuid.UUID
    payment_method: str
    amount: Decimal
    reference_no: str | None = None
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
    created_at: datetime
    items: list[SaleOrderItemRead] = Field(default_factory=list)
    payments: list[PaymentRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class VoidRequest(BaseSchema):
    void_reason: str


class RefundRequest(BaseSchema):
    refund_reason: str


class PartialRefundItemRequest(BaseSchema):
    order_item_id: uuid.UUID
    qty: Decimal


class PartialRefundRequest(BaseSchema):
    refund_reason: str
    items: list[PartialRefundItemRequest] = Field(default_factory=list)


class ReceiptData(BaseSchema):
    order: SaleOrderRead
    company_name: str
    branch_name: str
    cashier_name: str
    receipt_footer: str = "ขอบคุณที่ใช้บริการ"


class SyncSalesRequest(BaseSchema):
    orders: list[CreateSaleRequest] = Field(default_factory=list)
