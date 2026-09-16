from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
import uuid

from pydantic import Field, model_validator

from app.schemas import BaseSchema


SourceModule = Literal["restaurant_pos", "retail_pos", "takeaway_pos", "purchasing", "manual"]
TaxDirection = Literal["output", "input"]
TaxCategory = Literal["standard", "zero", "exempt"]
ExportType = Literal["vat_sales", "vat_purchases", "pp30_summary", "wht_pnd3", "wht_pnd53", "etax_manifest", "tax_archive"]


class TaxLedgerIngest(BaseSchema):
    source_module: SourceModule
    tax_direction: TaxDirection
    tax_category: TaxCategory = "standard"
    source_document_type: str = Field(min_length=1, max_length=40)
    source_document_id: str = Field(min_length=1, max_length=100)
    line_key: str = Field(default="summary", min_length=1, max_length=100)
    source_status: str | None = Field(default=None, max_length=30)
    document_number: str = Field(min_length=1, max_length=100)
    document_date: date
    branch_id: uuid.UUID | None = None
    brand_id: uuid.UUID | None = None
    counterparty_name: str | None = Field(default=None, max_length=255)
    counterparty_tax_id: str | None = Field(default=None, max_length=20)
    counterparty_branch_code: str | None = Field(default=None, max_length=10)
    base_amount: Decimal = Field(ge=0)
    tax_amount: Decimal = Field(ge=0)
    total_amount: Decimal = Field(ge=0)
    vat_rate: Decimal = Field(ge=0, le=100)
    status: Literal["posted", "reversed", "excluded"] = "posted"
    source_event_id: str | None = Field(default=None, max_length=100)
    source_event_at: datetime | None = None

    @model_validator(mode="after")
    def validate_tax_values(self) -> "TaxLedgerIngest":
        if self.tax_category in {"zero", "exempt"} and self.tax_amount != 0:
            raise ValueError("รายการอัตรา 0% หรือยกเว้น ต้องไม่มีภาษี")
        if abs((self.base_amount + self.tax_amount) - self.total_amount) > Decimal("0.02"):
            raise ValueError("ยอดฐานภาษีและภาษีรวมไม่ตรงกับยอดรวม")
        return self


class TaxPeriodAction(BaseSchema):
    year: int = Field(ge=2000, le=2200)
    month: int = Field(ge=1, le=12)
    branch_id: uuid.UUID | None = None
    reason: str | None = Field(default=None, max_length=500)


class TaxIssueResolve(BaseSchema):
    status: Literal["resolved", "ignored"]
    note: str = Field(min_length=3, max_length=500)


class TaxExportCreate(BaseSchema):
    year: int = Field(ge=2000, le=2200)
    month: int = Field(ge=1, le=12)
    branch_id: uuid.UUID | None = None
    export_type: ExportType
    reason: str | None = Field(default=None, max_length=500)
