from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid

from pydantic import ConfigDict, Field

from app.schemas import BaseSchema


class SupplierInvoiceCreate(BaseSchema):
    supplier_id: uuid.UUID
    branch_id: uuid.UUID
    po_id: uuid.UUID | None = None
    supplier_ref: str | None = None
    invoice_date: date
    subtotal: Decimal
    vat_amount: Decimal = Decimal("0")
    wht_amount: Decimal = Decimal("0")
    note: str | None = None


class SupplierInvoiceRead(BaseSchema):
    id: uuid.UUID
    invoice_number: str
    supplier_id: uuid.UUID
    po_id: uuid.UUID | None = None
    status: str
    invoice_date: date
    due_date: date
    supplier_ref: str | None = None
    subtotal: Decimal
    vat_amount: Decimal
    wht_amount: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    note: str | None = None
    created_at: datetime
    supplier_name: str
    is_overdue: bool

    model_config = ConfigDict(from_attributes=True)


class SupplierInvoiceListItem(BaseSchema):
    id: uuid.UUID
    invoice_number: str
    supplier_id: uuid.UUID
    supplier_name: str
    status: str
    invoice_date: date
    due_date: date
    total_amount: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    is_overdue: bool

    model_config = ConfigDict(from_attributes=True)


class PaymentAllocationInput(BaseSchema):
    invoice_id: uuid.UUID
    allocated_amount: Decimal
    wht_amount: Decimal = Decimal("0")
    wht_rate: Decimal = Decimal("0")
    wht_type: str | None = None


class CreateAPPaymentRequest(BaseSchema):
    branch_id: uuid.UUID
    payment_date: date
    payment_method: str
    bank_account: str | None = None
    reference_no: str | None = None
    allocations: list[PaymentAllocationInput] = Field(min_length=1)
    note: str | None = None


class APPaymentAllocationRead(BaseSchema):
    id: uuid.UUID
    payment_id: uuid.UUID
    invoice_id: uuid.UUID
    allocated_amount: Decimal
    wht_amount: Decimal
    wht_rate: Decimal
    wht_type: str | None = None
    invoice_number: str
    supplier_name: str

    model_config = ConfigDict(from_attributes=True)


class APPaymentRead(BaseSchema):
    id: uuid.UUID
    payment_number: str
    payment_date: date
    payment_method: str
    bank_account: str | None = None
    reference_no: str | None = None
    total_amount: Decimal
    note: str | None = None
    created_at: datetime
    allocations: list[APPaymentAllocationRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class WHTCertificateRead(BaseSchema):
    id: uuid.UUID
    certificate_number: str
    payment_id: uuid.UUID
    supplier_id: uuid.UUID
    issue_date: date
    wht_type: str
    wht_rate: Decimal
    base_amount: Decimal
    wht_amount: Decimal
    income_type: str | None = None
    created_at: datetime
    supplier_name: str
    supplier_tax_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class VatReturnReport(BaseSchema):
    year: int
    month: int
    month_label: str
    output_vat_sales: Decimal
    output_vat_total: Decimal
    input_vat_purchases: Decimal
    input_vat_total: Decimal
    net_vat_payable: Decimal
    net_vat_label: str
    output_doc_count: int
    input_invoice_count: int
    filing_due_date: str

