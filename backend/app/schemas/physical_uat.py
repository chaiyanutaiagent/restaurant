from __future__ import annotations

from datetime import datetime
from typing import Literal
import uuid

from pydantic import Field, field_validator, model_validator

from app.schemas import BaseSchema


class PhysicalUATSessionCreate(BaseSchema):
    device_id: uuid.UUID
    release_commit: str = Field(min_length=7, max_length=64, pattern=r"^[0-9a-fA-F]+$")
    device_model: str = Field(min_length=1, max_length=160)
    os_version: str = Field(min_length=1, max_length=120)
    browser_version: str = Field(min_length=1, max_length=160)
    printer_model_connection: str | None = Field(default=None, max_length=200)
    network_profile: str = Field(min_length=1, max_length=160)


class PhysicalUATCheckUpdate(BaseSchema):
    result: Literal["pass", "fail", "na"]
    reason: str | None = Field(default=None, max_length=1000)
    evidence_reference: str | None = Field(default=None, max_length=500)
    defect_id: str | None = Field(default=None, max_length=100)
    defect_severity: Literal["P0", "P1", "P2", "P3"] | None = None
    evidence: dict = Field(default_factory=dict)

    @field_validator("reason", "evidence_reference", "defect_id")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def validate_evidence(self) -> "PhysicalUATCheckUpdate":
        if self.result == "na" and not self.reason:
            raise ValueError("N/A requires an approved reason")
        if self.result in {"pass", "fail"} and not self.evidence_reference:
            raise ValueError("Pass/Fail requires an evidence reference")
        if self.result == "fail" and (not self.defect_id or not self.defect_severity):
            raise ValueError("Fail requires defect id and severity")
        return self


class PhysicalUATSignoffRequest(BaseSchema):
    role: Literal["technical", "business"]
    note: str = Field(min_length=3, max_length=1000)


class PhysicalUATCheckRead(BaseSchema):
    id: uuid.UUID
    check_key: str
    category: str
    label: str
    source: Literal["automatic", "manual"]
    required: bool
    result: Literal["pending", "pass", "fail", "na"]
    reason: str | None = None
    evidence_reference: str | None = None
    defect_id: str | None = None
    defect_severity: str | None = None
    tested_by: uuid.UUID | None = None
    tested_at: datetime | None = None
    evidence: dict = Field(default_factory=dict)


class PhysicalUATSessionRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    branch_id: uuid.UUID
    device_id: uuid.UUID
    release_commit: str
    environment: Literal["uat"]
    status: Literal["in_progress", "not_ready", "ready_for_signoff", "uat_approved"]
    created_by: uuid.UUID
    submitted_by: uuid.UUID | None = None
    submitted_at: datetime | None = None
    technical_approved_by: uuid.UUID | None = None
    technical_approved_at: datetime | None = None
    business_approved_by: uuid.UUID | None = None
    business_approved_at: datetime | None = None
    device_snapshot: dict
    environment_snapshot: dict
    summary: dict
    checks: list[PhysicalUATCheckRead]
    created_at: datetime
    updated_at: datetime
