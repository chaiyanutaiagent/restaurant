from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
import uuid

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.schemas import BaseSchema


class StrictMutation(BaseSchema):
    model_config = ConfigDict(extra="forbid")


class PrivacyRequestCreate(StrictMutation):
    request_type: Literal["access", "export", "correction", "deletion", "restriction", "objection", "consent_withdrawal"]
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else None
        return normalized or None


class PrivacyRequestUpdate(StrictMutation):
    status: Literal["identity_verified", "in_review", "fulfilled", "rejected", "cancelled"]
    response_summary: str | None = Field(default=None, max_length=2000)
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_resolution(self) -> "PrivacyRequestUpdate":
        self.reason = self.reason.strip()
        self.response_summary = self.response_summary.strip() if self.response_summary else None
        if self.status in {"fulfilled", "rejected"} and not self.response_summary:
            raise ValueError("fulfilled/rejected requests require a response summary")
        return self


class PrivacyRequestRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    requester_user_id: uuid.UUID
    request_type: str
    subject_email: str
    description: str | None = None
    status: str
    identity_verification: str
    target_at: datetime
    response_summary: str | None = None
    decision_reason: str | None = None
    reviewed_by: uuid.UUID | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RetentionDecisionCreate(StrictMutation):
    data_category: Literal["account_identity", "account_security", "billing_records", "support_records", "audit_evidence", "tenant_business_data"]
    action: Literal["retain", "delete", "anonymize"]
    rationale: str = Field(min_length=1, max_length=1000)
    retain_until: date | None = None
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_retention(self) -> "RetentionDecisionCreate":
        self.rationale = self.rationale.strip()
        self.reason = self.reason.strip()
        if self.action == "retain" and self.retain_until is None:
            raise ValueError("retain action requires retain_until")
        if self.action != "retain" and self.retain_until is not None:
            raise ValueError("retain_until is allowed only for retain action")
        return self


class RetentionDecisionUpdate(StrictMutation):
    status: Literal["approved", "rejected"]
    reason: str = Field(min_length=1, max_length=500)


class RetentionDecisionRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    privacy_request_id: uuid.UUID
    data_category: str
    action: str
    rationale: str
    retain_until: date | None = None
    status: str
    proposed_by: uuid.UUID
    decided_by: uuid.UUID | None = None
    decided_at: datetime | None = None
    decision_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class SupportTicketCreate(StrictMutation):
    category: Literal["account", "billing", "technical", "privacy", "other"]
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    subject: str = Field(min_length=1, max_length=200)
    initial_message: str = Field(min_length=1, max_length=5000)

    @field_validator("subject", "initial_message")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value is required")
        return normalized


class SupportMessageCreate(StrictMutation):
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("body")
    @classmethod
    def normalize_body(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message is required")
        return normalized


class SupportTicketUpdate(StrictMutation):
    status: Literal["open", "in_progress", "waiting_tenant", "resolved", "closed"]
    priority: Literal["low", "normal", "high", "urgent"]
    reason: str = Field(min_length=1, max_length=500)


class SupportMessageRead(BaseSchema):
    id: uuid.UUID
    ticket_id: uuid.UUID
    company_id: uuid.UUID
    sender_type: str
    sender_user_id: uuid.UUID | None = None
    sender_operator_id: uuid.UUID | None = None
    body: str
    created_at: datetime


SupportScope = Literal["account_state", "saas_controls", "aggregate_usage", "billing_state"]


class SupportAccessRequest(StrictMutation):
    requested_scopes: list[SupportScope] = Field(min_length=1, max_length=4)
    purpose: str = Field(min_length=1, max_length=500)
    duration_minutes: int = Field(ge=5, le=60)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("requested_scopes")
    @classmethod
    def unique_scopes(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("support scopes must be unique")
        return sorted(value)


class SupportAccessDecision(StrictMutation):
    decision: Literal["approved", "denied"]
    reason: str = Field(min_length=1, max_length=500)


class SupportAccessRevoke(StrictMutation):
    reason: str = Field(min_length=1, max_length=500)


class SupportAccessGrantRead(BaseSchema):
    id: uuid.UUID
    ticket_id: uuid.UUID
    company_id: uuid.UUID
    requested_by_operator_id: uuid.UUID
    requested_scopes: list[str]
    purpose: str
    duration_minutes: int
    status: str
    decided_by_user_id: uuid.UUID | None = None
    decision_reason: str | None = None
    decided_at: datetime | None = None
    expires_at: datetime | None = None
    last_accessed_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_by_type: str | None = None
    revoke_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class SupportTicketRead(BaseSchema):
    id: uuid.UUID
    ticket_number: str
    company_id: uuid.UUID
    requester_user_id: uuid.UUID
    category: str
    priority: str
    status: str
    subject: str
    assigned_operator_id: uuid.UUID | None = None
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[SupportMessageRead] = Field(default_factory=list)
    access_grants: list[SupportAccessGrantRead] = Field(default_factory=list)


class SupportContextRead(BaseSchema):
    grant_id: uuid.UUID
    company_id: uuid.UUID
    ticket_id: uuid.UUID
    expires_at: datetime
    scopes: list[str]
    context: dict[str, Any]
