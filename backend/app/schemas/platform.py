from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
import re
import uuid

from pydantic import Field, field_validator

from app.schemas import BaseSchema


USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,99}$")
PLAN_CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,49}$")
FEATURE_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,99}$")
LIMIT_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,99}$")


def _required_text(value: str, *, field_name: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return normalized


class PlatformLoginRequest(BaseSchema):
    username: str
    password: str
    mfa_code: str | None = Field(default=None, max_length=32)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not USERNAME_PATTERN.fullmatch(normalized):
            raise ValueError("username format is invalid")
        return normalized


class PlatformOperatorRead(BaseSchema):
    id: uuid.UUID
    username: str
    email: str | None = None
    display_name: str
    is_superuser: bool
    mfa_enabled: bool
    last_login_at: datetime | None = None


class PlatformTokenResponse(BaseSchema):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    csrf_token: str
    session_id: uuid.UUID
    operator: PlatformOperatorRead


class PlatformSessionRead(BaseSchema):
    id: uuid.UUID
    current: bool
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    mfa_verified_at: datetime | None = None
    revoked_at: datetime | None = None
    ip_address: str | None = None
    user_agent: str | None = None


class PlatformMfaSetupRead(BaseSchema):
    secret: str
    provisioning_uri: str


class PlatformMfaCodeRequest(BaseSchema):
    code: str = Field(min_length=6, max_length=32)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return _required_text(value, field_name="code", max_length=32)


class PlatformMfaConfirmRead(BaseSchema):
    recovery_codes: list[str]
    operator: PlatformOperatorRead


class PlatformMfaDisableRequest(PlatformMfaCodeRequest):
    password: str = Field(min_length=1, max_length=128)


class PlatformPasswordChangeRequest(BaseSchema):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)
    mfa_code: str | None = Field(default=None, max_length=32)


class PlatformCompanyOwnerCreate(BaseSchema):
    username: str
    password: str = Field(min_length=12, max_length=128)
    email: str | None = Field(default=None, max_length=255)
    display_name: str = Field(min_length=1, max_length=200)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not USERNAME_PATTERN.fullmatch(normalized):
            raise ValueError("owner username format is invalid")
        return normalized

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return value.strip().lower() if value and value.strip() else None

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        return _required_text(value, field_name="display_name", max_length=200)


class PlatformCompanyCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    name_en: str | None = Field(default=None, max_length=255)
    tax_id: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    currency: str = Field(default="THB", min_length=3, max_length=3)
    timezone: str = Field(default="Asia/Bangkok", min_length=1, max_length=50)
    plan_code: str = "starter"
    feature_flags: dict[str, bool] = Field(
        default_factory=lambda: {"restaurant": True, "retail_pos": False, "takeaway": False}
    )
    plan_limits: dict[str, int] = Field(
        default_factory=lambda: {"brands": 1, "branches": 1, "users": 10, "devices": 3}
    )
    owner: PlatformCompanyOwnerCreate
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("name", "reason")
    @classmethod
    def normalize_required_text(cls, value: str, info) -> str:
        return _required_text(value, field_name=info.field_name, max_length=500)

    @field_validator("name_en", "tax_id", "email", "phone")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("timezone")
    @classmethod
    def normalize_timezone(cls, value: str) -> str:
        return _required_text(value, field_name="timezone", max_length=50)

    @field_validator("plan_code")
    @classmethod
    def validate_plan_code(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not PLAN_CODE_PATTERN.fullmatch(normalized):
            raise ValueError("plan_code format is invalid")
        return normalized

    @field_validator("feature_flags")
    @classmethod
    def validate_feature_flags(cls, value: dict[str, bool]) -> dict[str, bool]:
        if len(value) > 100:
            raise ValueError("feature_flags supports at most 100 entries")
        normalized: dict[str, bool] = {}
        for key, enabled in value.items():
            normalized_key = key.strip().lower()
            if not FEATURE_KEY_PATTERN.fullmatch(normalized_key):
                raise ValueError(f"feature flag key is invalid: {key}")
            normalized[normalized_key] = enabled
        return normalized

    @field_validator("plan_limits")
    @classmethod
    def validate_plan_limits(cls, value: dict[str, int]) -> dict[str, int]:
        if len(value) > 100:
            raise ValueError("plan_limits supports at most 100 entries")
        normalized: dict[str, int] = {}
        for key, limit in value.items():
            normalized_key = key.strip().lower()
            if not LIMIT_KEY_PATTERN.fullmatch(normalized_key):
                raise ValueError(f"plan limit key is invalid: {key}")
            if isinstance(limit, bool) or limit < 0 or limit > 1_000_000:
                raise ValueError(f"plan limit must be between 0 and 1000000: {key}")
            normalized[normalized_key] = limit
        return normalized


class PlatformTenantControlsUpdate(BaseSchema):
    plan_code: str
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    plan_limits: dict[str, int] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=500)

    _validate_plan_code = field_validator("plan_code")(
        PlatformCompanyCreate.validate_plan_code.__func__
    )
    _validate_feature_flags = field_validator("feature_flags")(
        PlatformCompanyCreate.validate_feature_flags.__func__
    )
    _validate_plan_limits = field_validator("plan_limits")(
        PlatformCompanyCreate.validate_plan_limits.__func__
    )

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return _required_text(value, field_name="reason", max_length=500)


class PlatformLifecycleAction(BaseSchema):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return _required_text(value, field_name="reason", max_length=500)


class PlatformTenantExportRequest(BaseSchema):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return _required_text(value, field_name="reason", max_length=500)


class PlatformTenantControlsRead(BaseSchema):
    plan_code: str
    feature_flags: dict[str, bool]
    plan_limits: dict[str, int]


class PlatformCompanyListItem(BaseSchema):
    id: uuid.UUID
    name: str
    name_en: str | None = None
    tax_id: str | None = None
    email: str | None = None
    is_active: bool
    credential_version: int
    plan_code: str
    created_at: datetime
    suspended_at: datetime | None = None


class PlatformOnboardingStepRead(BaseSchema):
    key: str
    label: str
    complete: bool
    count: int
    target: int


class PlatformOnboardingRead(BaseSchema):
    complete: bool
    completed_steps: int
    total_steps: int
    steps: list[PlatformOnboardingStepRead]


class PlatformCompanyDetailRead(PlatformCompanyListItem):
    phone: str | None = None
    currency: str
    timezone: str
    controls: PlatformTenantControlsRead
    onboarding: PlatformOnboardingRead
    suspension_reason: str | None = None
    reactivated_at: datetime | None = None
    reactivation_reason: str | None = None
    updated_at: datetime


class PlatformDashboardTotalsRead(BaseSchema):
    companies: int
    active_companies: int
    suspended_companies: int
    brands: int
    branches: int
    enabled_user_accounts: int
    devices: int
    paired_devices: int


class PlatformDashboardOnboardingRead(BaseSchema):
    ready_companies: int
    pending_companies: int
    total_active_companies: int


class PlatformDashboardCompanyRead(PlatformCompanyListItem):
    onboarding_complete: bool
    completed_steps: int
    total_steps: int


class PlatformDashboardRead(BaseSchema):
    generated_at: datetime
    totals: PlatformDashboardTotalsRead
    onboarding: PlatformDashboardOnboardingRead
    product_status: dict[str, Literal["pilot", "planned"]]
    feature_usage: dict[str, int]
    plan_usage: dict[str, int]
    recent_companies: list[PlatformDashboardCompanyRead]
    recent_events: list[dict[str, Any]]
