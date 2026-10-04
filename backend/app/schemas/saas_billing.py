from __future__ import annotations

from datetime import datetime
import re
from typing import Literal
import uuid

from pydantic import ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from app.schemas import BaseSchema


CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,49}$")
SOURCE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,49}$")


class SaasPlanUpsert(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    currency: str = Field(default="THB", min_length=3, max_length=3)
    billing_interval: Literal["month", "year"] = "month"
    unit_amount_satang: int | None = Field(default=None, ge=0)
    feature_flags: dict[str, StrictBool] = Field(default_factory=dict)
    plan_limits: dict[str, StrictInt] = Field(default_factory=dict)
    is_public: bool = False
    is_active: bool = True
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not CODE_PATTERN.fullmatch(normalized):
            raise ValueError("plan code format is invalid")
        return normalized

    @field_validator("name", "reason")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value is required")
        return normalized

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("feature_flags")
    @classmethod
    def validate_features(cls, value: dict[str, bool]) -> dict[str, bool]:
        if len(value) > 100:
            raise ValueError("feature flags supports at most 100 entries")
        return dict(sorted(value.items()))

    @field_validator("plan_limits")
    @classmethod
    def validate_limits(cls, value: dict[str, int]) -> dict[str, int]:
        if len(value) > 100 or any(isinstance(limit, bool) or limit < 0 for limit in value.values()):
            raise ValueError("plan limits must be non-negative integers")
        return dict(sorted(value.items()))


class SaasPlanRead(BaseSchema):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    currency: str
    billing_interval: str
    unit_amount_satang: int | None = None
    feature_flags: dict[str, bool]
    plan_limits: dict[str, int]
    is_public: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SaasSubscriptionUpdate(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    plan_code: str
    status: Literal["incomplete", "trialing", "active", "past_due", "paused", "cancelled"]
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("plan_code")
    @classmethod
    def normalize_plan(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not CODE_PATTERN.fullmatch(normalized):
            raise ValueError("plan code format is invalid")
        return normalized

    @model_validator(mode="after")
    def validate_period(self) -> "SaasSubscriptionUpdate":
        if (
            self.current_period_start is not None
            and self.current_period_end is not None
            and self.current_period_end <= self.current_period_start
        ):
            raise ValueError("current period end must be after start")
        self.reason = self.reason.strip()
        return self


class SaasSubscriptionRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    plan_id: uuid.UUID
    status: str
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    trial_started_at: datetime | None = None
    trial_ends_at: datetime | None = None
    cancel_at_period_end: bool
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SaasInvoiceCreate(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    invoice_number: str | None = Field(default=None, max_length=100)
    status: Literal["draft", "open"] = "draft"
    currency: str = Field(default="THB", min_length=3, max_length=3)
    subtotal_satang: int = Field(ge=0)
    tax_satang: int = Field(default=0, ge=0)
    period_start: datetime | None = None
    period_end: datetime | None = None
    due_at: datetime | None = None
    memo: str | None = Field(default=None, max_length=500)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class SaasInvoiceRead(BaseSchema):
    id: uuid.UUID
    subscription_id: uuid.UUID
    company_id: uuid.UUID
    invoice_number: str
    status: str
    currency: str
    subtotal_satang: int
    tax_satang: int
    total_satang: int
    paid_satang: int
    period_start: datetime | None = None
    period_end: datetime | None = None
    due_at: datetime | None = None
    paid_at: datetime | None = None
    memo: str | None = None
    created_at: datetime
    updated_at: datetime


class SaasBillingEventImport(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    event_key: str = Field(min_length=1, max_length=200)
    event_type: Literal[
        "invoice.opened",
        "invoice.paid",
        "invoice.failed",
        "invoice.voided",
        "subscription.activated",
        "subscription.past_due",
        "subscription.paused",
        "subscription.cancelled",
    ]
    source: str
    company_id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    amount_satang: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    occurred_at: datetime
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("event_key", "reason")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value is required")
        return normalized

    @field_validator("source")
    @classmethod
    def normalize_source(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not SOURCE_PATTERN.fullmatch(normalized):
            raise ValueError("event source format is invalid")
        return normalized

    @field_validator("currency")
    @classmethod
    def normalize_optional_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None


class SaasBillingEventRead(BaseSchema):
    id: uuid.UUID
    event_key: str
    event_type: str
    source: str
    company_id: uuid.UUID
    subscription_id: uuid.UUID | None = None
    invoice_id: uuid.UUID | None = None
    amount_satang: int | None = None
    currency: str | None = None
    occurred_at: datetime
    processed_at: datetime
    result_status: str
    payload_sha256: str
    created_at: datetime


class SaasBillingSummaryRead(BaseSchema):
    company_id: uuid.UUID
    provider: str
    live_charging_enabled: bool
    collection_available: bool
    plan: SaasPlanRead | None = None
    subscription: SaasSubscriptionRead | None = None
    invoices: list[SaasInvoiceRead]


class SaasBillingOverviewRead(BaseSchema):
    provider: str
    live_charging_enabled: bool
    collection_available: bool
    plans: list[SaasPlanRead]
    subscription_counts: dict[str, int]
    invoice_counts: dict[str, int]
