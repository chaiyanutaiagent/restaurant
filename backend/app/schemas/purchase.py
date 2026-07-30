from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid

from pydantic import ConfigDict, Field

from app.schemas import BaseSchema


class SupplierBase(BaseSchema):
    code: str
    name: str
    name_en: str | None = None
    tax_id: str | None = None
    branch_code: str | None = None
    address: str | None = None
    address_en: str | None = None
    phone: str | None = None
    email: str | None = None
    contact_person: str | None = None
    payment_term_days: int = 30
    wht_rate: Decimal = Decimal("3.00")
    wht_type: str | None = None
    credit_limit: Decimal = Decimal("0")
    bank_name: str | None = None
    bank_account: str | None = None
    bank_account_name: str | None = None
    note: str | None = None
    is_active: bool = True


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseSchema):
    code: str | None = None
    name: str | None = None
    name_en: str | None = None
    tax_id: str | None = None
    branch_code: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    contact_person: str | None = None
    payment_term_days: int | None = None
    wht_rate: Decimal | None = None
    wht_type: str | None = None
    credit_limit: Decimal | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    bank_account_name: str | None = None
    note: str | None = None
    is_active: bool | None = None


class SupplierRead(SupplierBase):
    id: uuid.UUID
    company_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class POItemBase(BaseSchema):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    qty_ordered: Decimal
    unit_cost: Decimal
    discount_amount: Decimal = Decimal("0")
    vat_type: str = "excluded"
    vat_rate: Decimal = Decimal("7.00")


class POItemCreate(POItemBase):
    pass


class POItemUpdate(BaseSchema):
    qty_ordered: Decimal | None = None
    unit_cost: Decimal | None = None
    discount_amount: Decimal | None = None


class POItemRead(POItemBase):
    id: uuid.UUID
    po_id: uuid.UUID
    product_name: str
    sku: str
    unit_code: str | None = None
    qty_received: Decimal
    vat_amount: Decimal
    subtotal: Decimal

    model_config = ConfigDict(from_attributes=True)


class CreatePORequest(BaseSchema):
    supplier_id: uuid.UUID
    branch_id: uuid.UUID
    order_date: date | None = None
    expected_date: date | None = None
    items: list[POItemCreate] = Field(default_factory=list)
    vat_type: str = "excluded"
    note: str | None = None
    internal_note: str | None = None


class UpdatePORequest(BaseSchema):
    expected_date: date | None = None
    items: list[POItemCreate] | None = None
    note: str | None = None
    internal_note: str | None = None


class ApprovePORequest(BaseSchema):
    note: str | None = None


class CancelPORequest(BaseSchema):
    reason: str


class PurchaseOrderRead(BaseSchema):
    id: uuid.UUID
    po_number: str
    status: str
    branch_id: uuid.UUID
    supplier_id: uuid.UUID
    created_by: uuid.UUID
    approved_by: uuid.UUID | None = None
    order_date: date
    expected_date: date | None = None
    approved_at: datetime | None = None
    subtotal: Decimal
    discount_amount: Decimal
    vat_amount: Decimal
    wht_amount: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    vat_type: str
    vat_rate: Decimal
    wht_rate: Decimal
    note: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[POItemRead] = Field(default_factory=list)
    supplier: SupplierRead

    model_config = ConfigDict(from_attributes=True)


class POListItem(BaseSchema):
    id: uuid.UUID
    po_number: str
    status: str
    order_date: date
    expected_date: date | None = None
    supplier_id: uuid.UUID
    supplier_name: str
    total_amount: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    item_count: int


class GRItemCreate(BaseSchema):
    po_item_id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    qty_received: Decimal
    unit_cost: Decimal
    note: str | None = None


class CreateGRRequest(BaseSchema):
    po_id: uuid.UUID
    location_id: uuid.UUID
    items: list[GRItemCreate] = Field(default_factory=list)
    received_date: date | None = None
    note: str | None = None


class GRItemRead(BaseSchema):
    id: uuid.UUID
    gr_id: uuid.UUID
    po_item_id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    qty_received: Decimal
    unit_cost: Decimal
    note: str | None = None

    model_config = ConfigDict(from_attributes=True)


class GoodsReceiptRead(BaseSchema):
    id: uuid.UUID
    gr_number: str
    po_id: uuid.UUID
    branch_id: uuid.UUID
    location_id: uuid.UUID
    received_by: uuid.UUID
    received_date: date
    note: str | None = None
    created_at: datetime
    items: list[GRItemRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
