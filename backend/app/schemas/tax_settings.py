from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import re
from typing import Literal
import uuid

from pydantic import Field, field_validator, model_validator

from app.schemas import BaseSchema


VatType = Literal["included", "excluded", "exempt"]
TaxCategory = Literal["standard", "zero", "exempt"]
VatFilingMode = Literal["separate", "consolidated"]


def _digits(value: str | None, length: int, label: str) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\D", "", value)
    if not normalized:
        return None
    if len(normalized) != length:
        raise ValueError(f"{label}ต้องมี {length} หลัก")
    return normalized


class CompanyTaxProfileUpdate(BaseSchema):
    legal_name: str = Field(min_length=1, max_length=255)
    tax_id: str | None = None
    vat_registered: bool = False
    vat_registration_date: date | None = None
    registered_address: str | None = Field(default=None, max_length=2000)
    default_price_vat_type: VatType = "included"
    default_vat_rate: Decimal = Field(default=Decimal("7.00"), ge=0, le=100)
    vat_filing_mode: VatFilingMode = "separate"
    consolidated_filing_approved: bool = False
    effective_from: date
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("tax_id", mode="before")
    @classmethod
    def validate_tax_id(cls, value: object) -> str | None:
        return _digits(None if value is None else str(value), 13, "เลขผู้เสียภาษี")

    @model_validator(mode="after")
    def validate_registration(self) -> "CompanyTaxProfileUpdate":
        if self.vat_registered and not self.tax_id:
            raise ValueError("กิจการที่จด VAT ต้องระบุเลขผู้เสียภาษี")
        if self.vat_registered and not (self.registered_address or "").strip():
            raise ValueError("กิจการที่จด VAT ต้องระบุที่อยู่จดทะเบียน")
        if self.vat_filing_mode == "consolidated" and not self.consolidated_filing_approved:
            raise ValueError("การยื่นรวมต้องยืนยันว่าได้รับอนุมัติให้ยื่นรวมแล้ว")
        if self.default_price_vat_type == "exempt" and self.default_vat_rate != 0:
            raise ValueError("ราคายกเว้น VAT ต้องมีอัตราภาษี 0")
        return self


class CompanyTaxProfileRead(BaseSchema):
    id: uuid.UUID | None = None
    configured: bool
    company_id: uuid.UUID
    legal_name: str
    tax_id: str | None = None
    vat_registered: bool
    vat_registration_date: date | None = None
    registered_address: str | None = None
    default_price_vat_type: VatType
    default_vat_rate: Decimal
    vat_filing_mode: VatFilingMode
    consolidated_filing_approved: bool
    updated_at: datetime | None = None


class BranchTaxProfileUpdate(BaseSchema):
    tax_branch_code: str
    is_head_office: bool = False
    legal_name: str | None = Field(default=None, max_length=255)
    registered_address: str | None = Field(default=None, max_length=2000)
    vat_registration_date: date | None = None
    filing_enabled: bool = True
    effective_from: date
    effective_to: date | None = None
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("tax_branch_code", mode="before")
    @classmethod
    def validate_branch_code(cls, value: object) -> str:
        normalized = _digits(str(value), 5, "รหัสสาขาภาษี")
        if normalized is None:
            raise ValueError("ต้องระบุรหัสสาขาภาษี")
        return normalized

    @model_validator(mode="after")
    def validate_branch_profile(self) -> "BranchTaxProfileUpdate":
        if self.is_head_office and self.tax_branch_code != "00000":
            raise ValueError("สำนักงานใหญ่ต้องใช้รหัสสาขาภาษี 00000")
        if not self.is_head_office and self.tax_branch_code == "00000":
            raise ValueError("รหัส 00000 ใช้ได้เฉพาะสำนักงานใหญ่")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("วันที่สิ้นสุดต้องไม่ก่อนวันที่เริ่มใช้")
        return self


class BranchTaxProfileRead(BaseSchema):
    id: uuid.UUID | None = None
    configured: bool
    company_id: uuid.UUID
    branch_id: uuid.UUID
    branch_code: str
    branch_name: str
    tax_branch_code: str | None = None
    is_head_office: bool
    legal_name: str | None = None
    registered_address: str | None = None
    vat_registration_date: date | None = None
    filing_enabled: bool
    effective_from: date | None = None
    effective_to: date | None = None
    updated_at: datetime | None = None


class TaxRateRuleCreate(BaseSchema):
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(min_length=1, max_length=100)
    tax_category: TaxCategory
    rate: Decimal = Field(ge=0, le=100)
    price_vat_type: VatType
    effective_from: date
    effective_to: date | None = None
    is_default: bool = False
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> str:
        return str(value).strip().upper()

    @model_validator(mode="after")
    def validate_rule(self) -> "TaxRateRuleCreate":
        validate_tax_rule_values(
            self.tax_category,
            self.rate,
            self.price_vat_type,
            self.effective_from,
            self.effective_to,
        )
        return self


class TaxRateRuleUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    tax_category: TaxCategory | None = None
    rate: Decimal | None = Field(default=None, ge=0, le=100)
    price_vat_type: VatType | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    is_default: bool | None = None
    is_active: bool | None = None
    reason: str = Field(min_length=3, max_length=500)


class TaxRateRuleRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    code: str
    name: str
    tax_category: TaxCategory
    rate: Decimal
    price_vat_type: VatType
    effective_from: date
    effective_to: date | None = None
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TaxSettingsRead(BaseSchema):
    company: CompanyTaxProfileRead
    branches: list[BranchTaxProfileRead]
    rates: list[TaxRateRuleRead]


def validate_tax_rule_values(
    category: str,
    rate: Decimal,
    price_vat_type: str,
    effective_from: date,
    effective_to: date | None,
) -> None:
    if effective_to is not None and effective_to < effective_from:
        raise ValueError("วันที่สิ้นสุดต้องไม่ก่อนวันที่เริ่มใช้")
    if category in {"zero", "exempt"} and rate != 0:
        raise ValueError("อัตรา 0% และยกเว้น VAT ต้องมีอัตราภาษี 0")
    if category == "exempt" and price_vat_type != "exempt":
        raise ValueError("รายการยกเว้น VAT ต้องใช้ประเภทราคา exempt")
    if category != "exempt" and price_vat_type == "exempt":
        raise ValueError("ประเภทราคา exempt ใช้ได้กับรายการยกเว้น VAT เท่านั้น")
