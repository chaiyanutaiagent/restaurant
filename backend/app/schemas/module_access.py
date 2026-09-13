from __future__ import annotations

from datetime import datetime
from typing import Literal
import uuid

from pydantic import Field, StrictBool, field_validator

from app.schemas import BaseSchema


CompanyModuleKey = Literal[
    "erp",
    "central_kitchen",
    "restaurant_pos",
    "takeaway_pos",
    "retail_pos",
    "hotel_pms",
]
CompanyModuleLifecycle = Literal["active", "dark_launch", "planned"]
CompanyModuleReasonCode = Literal[
    "enabled",
    "company_inactive",
    "lifecycle_planned",
    "not_in_plan",
    "company_disabled",
    "runtime_unavailable",
    "permission_denied",
]


class CompanyModuleAccessRead(BaseSchema):
    module_key: CompanyModuleKey
    lifecycle: CompanyModuleLifecycle
    company_enabled: bool
    plan_included: bool
    runtime_ready: bool
    user_permitted: bool
    effective_access: bool
    reason_code: CompanyModuleReasonCode
    updated_at: datetime
    updated_by: uuid.UUID | None = None
    audit_id: uuid.UUID | None = None


class CompanyModuleAccessUpdate(BaseSchema):
    enabled: StrictBool
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason is required")
        return normalized
