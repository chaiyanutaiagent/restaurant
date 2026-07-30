from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
import uuid

from pydantic import ConfigDict, Field

from app.schemas import BaseSchema


class AccountBase(BaseSchema):
    code: str
    name: str
    name_en: str | None = None
    account_type: str
    account_subtype: str | None = None
    normal_balance: str
    is_header: bool = False
    is_active: bool = True
    description: str | None = None
    sort_order: int = 0


class AccountCreate(AccountBase):
    parent_id: uuid.UUID | None = None


class AccountUpdate(BaseSchema):
    parent_id: uuid.UUID | None = None
    code: str | None = None
    name: str | None = None
    name_en: str | None = None
    account_type: str | None = None
    account_subtype: str | None = None
    normal_balance: str | None = None
    is_header: bool | None = None
    is_active: bool | None = None
    description: str | None = None
    sort_order: int | None = None


class AccountRead(AccountBase):
    id: uuid.UUID
    company_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    is_system: bool
    created_at: datetime
    children: list["AccountRead"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class AccountListItem(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    code: str
    name: str
    account_type: str
    normal_balance: str
    is_header: bool
    is_active: bool
    is_system: bool

    model_config = ConfigDict(from_attributes=True)


class JournalLineCreate(BaseSchema):
    account_id: uuid.UUID
    description: str | None = None
    debit_amount: Decimal = Decimal("0")
    credit_amount: Decimal = Decimal("0")


class JournalLineRead(BaseSchema):
    id: uuid.UUID
    entry_id: uuid.UUID
    account_id: uuid.UUID
    line_number: int
    description: str | None = None
    debit_amount: Decimal
    credit_amount: Decimal
    account_code: str
    account_name: str

    model_config = ConfigDict(from_attributes=True)


class CreateJournalEntryRequest(BaseSchema):
    entry_date: date
    description: str
    branch_id: uuid.UUID | None = None
    lines: list[JournalLineCreate]


class JournalEntryRead(BaseSchema):
    id: uuid.UUID
    entry_number: str
    entry_date: date
    period_year: int
    period_month: int
    entry_type: str
    reference_type: str | None = None
    reference_id: str | None = None
    description: str
    is_posted: bool
    is_reversed: bool
    created_by: uuid.UUID
    created_at: datetime
    posted_at: datetime | None = None
    lines: list[JournalLineRead] = Field(default_factory=list)
    total_debit: Decimal

    model_config = ConfigDict(from_attributes=True)


class JournalEntryListItem(BaseSchema):
    id: uuid.UUID
    entry_number: str
    entry_date: date
    entry_type: str
    description: str
    is_posted: bool
    total_debit: Decimal
    reference_type: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AccountBalanceRead(BaseSchema):
    account_id: uuid.UUID
    account_code: str
    account_name: str
    account_type: str
    period_year: int
    period_month: int
    opening_balance: Decimal
    debit_total: Decimal
    credit_total: Decimal
    closing_balance: Decimal

    model_config = ConfigDict(from_attributes=True)


class TrialBalanceRow(BaseSchema):
    account_code: str
    account_name: str
    account_type: str
    debit_balance: Decimal
    credit_balance: Decimal


class TrialBalanceReport(BaseSchema):
    period_year: int
    period_month: int
    period_label: str
    rows: list[TrialBalanceRow]
    total_debit: Decimal
    total_credit: Decimal
    is_balanced: bool


class ProfitLossReport(BaseSchema):
    period_year: int
    period_month: int
    period_label: str
    total_revenue: Decimal
    total_cogs: Decimal
    gross_profit: Decimal
    gross_margin_pct: Decimal
    total_operating_expense: Decimal
    net_profit: Decimal
    net_margin_pct: Decimal
    revenue_rows: list[TrialBalanceRow]
    cogs_rows: list[TrialBalanceRow]
    expense_rows: list[TrialBalanceRow]


class AccountLedgerLine(BaseSchema):
    entry_id: uuid.UUID
    entry_number: str
    entry_date: date
    line_number: int
    description: str | None = None
    debit_amount: Decimal
    credit_amount: Decimal
    running_balance: Decimal
    reference_type: str | None = None
    reference_id: str | None = None


class AccountLedgerResponse(BaseSchema):
    account_id: uuid.UUID
    account_code: str
    account_name: str
    period_year: int
    period_month: int
    opening_balance: Decimal
    closing_balance: Decimal
    lines: list[AccountLedgerLine]
    meta: dict[str, Any] = Field(default_factory=dict)


AccountRead.model_rebuild()
