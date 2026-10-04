from __future__ import annotations

from datetime import datetime
from typing import Literal
import uuid

from pydantic import Field, field_validator, model_validator

from app.schemas import BaseSchema


AccessReviewOutcome = Literal["retain", "reduce", "revoke", "investigate"]


class CompanyAccessMutationRequest(BaseSchema):
    reason: str = Field(min_length=1, max_length=500)
    request_id: uuid.UUID
    expected_credential_version: int = Field(ge=1)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip()


class CompanyAccessReviewRequest(CompanyAccessMutationRequest):
    outcome: AccessReviewOutcome
    assignment_id: uuid.UUID | None = None
    next_review_due_at: datetime | None = None

    @model_validator(mode="after")
    def validate_outcome_target(self) -> "CompanyAccessReviewRequest":
        if self.outcome == "reduce" and self.assignment_id is None:
            raise ValueError("assignment_id is required for reduce outcome")
        if self.outcome != "reduce" and self.assignment_id is not None:
            raise ValueError("assignment_id is only valid for reduce outcome")
        return self


class CompanyTenantSessionRead(BaseSchema):
    id: uuid.UUID
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    state: Literal["active", "revoked", "expired"]


class CompanyAccessReviewUserRead(BaseSchema):
    id: uuid.UUID
    username: str
    display_name: str
    email: str | None = None
    is_active: bool
    is_superuser: bool
    credential_version: int
    mfa_state: Literal["enabled", "not_configured"]
    last_login_at: datetime | None = None
    active_session_count: int
    role_names: list[str]
    risk_flags: list[str]
    access_reviewed_at: datetime | None = None
    access_review_due_at: datetime | None = None
    access_review_outcome: AccessReviewOutcome | None = None
    review_due: bool
    stale_access: bool


class CompanyTenantSecurityRead(BaseSchema):
    tenant_mfa_policy: Literal["hold"] = "hold"
    tenant_mfa_enforcement_enabled: bool = False
    session_management_enabled: bool = True
    recovery_process_state: Literal["product_owner_decision_required"] = "product_owner_decision_required"
    suspicious_login_alert_state: Literal["planned"] = "planned"
    note: str
