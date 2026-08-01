from __future__ import annotations

from datetime import datetime
import uuid

from pydantic import Field, field_validator, model_validator

from app.schemas import BaseSchema
from app.schemas.role import RoleScope


class StaffRoleAssignmentCreate(BaseSchema):
    role_id: uuid.UUID
    scope_type: RoleScope
    brand_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    station_key: str | None = Field(default=None, max_length=100)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("station_key")
    @classmethod
    def normalize_station_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_target_shape(self) -> "StaffRoleAssignmentCreate":
        if self.scope_type == "company":
            valid = self.brand_id is None and self.branch_id is None and self.station_key is None
        elif self.scope_type == "brand":
            valid = self.brand_id is not None and self.branch_id is None and self.station_key is None
        elif self.scope_type == "branch":
            valid = self.brand_id is None and self.branch_id is not None and self.station_key is None
        else:
            valid = self.brand_id is None and self.branch_id is not None and self.station_key is not None
        if not valid:
            raise ValueError("scope target does not match scope_type")
        return self


class StaffRoleAssignmentRevoke(BaseSchema):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason must not be blank")
        return normalized


class StaffRoleAssignmentRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    user_id: uuid.UUID
    employee_id: uuid.UUID | None = None
    employee_code: str | None = None
    employee_name: str | None = None
    role_id: uuid.UUID
    role_name: str
    scope_type: RoleScope
    scope_key: str
    scope_label: str
    brand_id: uuid.UUID | None = None
    brand_name: str | None = None
    branch_id: uuid.UUID | None = None
    branch_name: str | None = None
    station_key: str | None = None
    assignment_reason: str
    assigned_by: uuid.UUID
    assigned_at: datetime
    revoked_by: uuid.UUID | None = None
    revoked_at: datetime | None = None
    revocation_reason: str | None = None


class AssignmentCompanyOption(BaseSchema):
    id: uuid.UUID
    name: str


class AssignmentBrandOption(BaseSchema):
    id: uuid.UUID
    name: str
    business_type: str


class AssignmentBranchOption(BaseSchema):
    id: uuid.UUID
    code: str
    name: str
    brand_id: uuid.UUID
    stations: list[str]


class StaffAssignmentOptionsRead(BaseSchema):
    company: AssignmentCompanyOption
    brands: list[AssignmentBrandOption]
    branches: list[AssignmentBranchOption]
