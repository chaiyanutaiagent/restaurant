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
CompanyProductReadiness = Literal[
    "production",
    "pilot",
    "dark_launch",
    "read_only",
    "legacy",
    "planned",
]
CompanyModuleAction = Literal[
    "view",
    "create",
    "update",
    "approve",
    "refund",
    "export",
    "suspend",
    "execute",
]
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
    readiness: CompanyProductReadiness = "production"
    environment: Literal["production", "uat"] = "uat"
    company_enabled: bool
    plan_included: bool
    runtime_ready: bool
    user_permitted: bool
    effective_access: bool
    reason_code: CompanyModuleReasonCode
    allowed_actions: list[CompanyModuleAction] = Field(default_factory=list)
    enabled_branch_ids: list[uuid.UUID] = Field(default_factory=list)
    branch_scope: Literal["all", "selected", "none"] = "all"
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    data_source: str = "platform"
    status_reason: str | None = None
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
