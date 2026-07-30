from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid

from pydantic import ConfigDict, Field

from app.schemas import BaseSchema


class TaxDocumentItemRead(BaseSchema):
    id: uuid.UUID
    document_id: uuid.UUID
    line_number: int
    description: str
    unit_code: str | None = None
    qty: Decimal
    unit_price: Decimal
    discount_amount: Decimal
    vat_type: str
    vat_rate: Decimal
    vat_amount: Decimal
    line_total: Decimal

    model_config = ConfigDict(from_attributes=True)


class TaxDocumentRead(BaseSchema):
    id: uuid.UUID
    document_number: str
    document_type: str
    status: str
    branch_id: uuid.UUID
    reference_type: str
    reference_id: str
    seller_tax_id: str
    seller_name: str
    seller_branch_code: str | None = None
    seller_address: str | None = None
    buyer_tax_id: str | None = None
    buyer_name: str | None = None
    buyer_branch_code: str | None = None
    buyer_address: str | None = None
    subtotal: Decimal
    discount_amount: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    total_amount: Decimal
    issue_date: date
    issue_datetime: datetime
    original_document_id: uuid.UUID | None = None
    reason: str | None = None
    xml_hash: str | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    created_by: uuid.UUID
    created_at: datetime
    items: list[TaxDocumentItemRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class TaxDocumentListItem(BaseSchema):
    id: uuid.UUID
    document_number: str
    document_type: str
    status: str
    buyer_name: str | None = None
    buyer_tax_id: str | None = None
    total_amount: Decimal
    vat_amount: Decimal
    issue_date: date
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IssueTaxInvoiceRequest(BaseSchema):
    sale_order_id: uuid.UUID
    document_type: str = "abbreviated_tax_invoice"
    buyer_tax_id: str | None = None
    buyer_name: str | None = None
    buyer_branch_code: str | None = None
    buyer_address: str | None = None


class IssueCreditNoteRequest(BaseSchema):
    original_document_id: uuid.UUID
    reason: str


class CancelDocumentRequest(BaseSchema):
    cancel_reason: str
