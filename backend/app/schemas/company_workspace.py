from __future__ import annotations

from datetime import datetime
from typing import Literal
import re
import uuid

from pydantic import ConfigDict, Field, field_validator

from app.schemas import BaseSchema
from app.schemas.module_access import CompanyModuleAccessRead, CompanyModuleKey


WorkspaceModuleKey = Literal["restaurant_pos", "takeaway_pos", "retail_pos"]
WorkspaceBusinessType = Literal["restaurant", "takeaway", "retail_pos"]
WorkspaceKind = Literal["shared_service", "workspace_collection", "planned"]


class CompanyWorkspaceRead(BaseSchema):
    workspace_id: uuid.UUID
    module_key: WorkspaceModuleKey
    business_type: WorkspaceBusinessType
    brand_id: uuid.UUID
    brand_slug: str
    brand_name: str
    branch_id: uuid.UUID
    branch_code: str
    branch_name: str
    branch_type: str
    storefront_mode: str
    is_active: bool
    can_open: bool
    entry_route: str


class CompanyWorkspaceModuleRead(BaseSchema):
    module_key: CompanyModuleKey
    kind: WorkspaceKind
    entry_route: str | None
    can_provision: bool
    access: CompanyModuleAccessRead
    workspaces: list[CompanyWorkspaceRead] = Field(default_factory=list)


class CompanyWorkspaceDirectoryRead(BaseSchema):
    company_id: uuid.UUID
    generated_at: datetime
    modules: list[CompanyWorkspaceModuleRead]


class CompanyWorkspaceProvisionRequest(BaseSchema):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    idempotency_key: str = Field(min_length=8, max_length=64)
    module_key: WorkspaceModuleKey
    brand_slug: str = Field(min_length=2, max_length=80)
    brand_name: str = Field(min_length=1, max_length=255)
    branch_code: str = Field(min_length=1, max_length=20)
    branch_name: str = Field(min_length=1, max_length=255)
    branch_type: Literal["company_owned", "franchise"] = "company_owned"
    storefront_mode: Literal["food_stall", "drink_shop"] = "food_stall"

    @field_validator("idempotency_key")
    @classmethod
    def normalize_idempotency_key(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9._:-]+", normalized):
            raise ValueError("idempotency_key contains unsupported characters")
        return normalized

    @field_validator("brand_slug")
    @classmethod
    def normalize_brand_slug(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalized):
            raise ValueError("brand_slug must use lowercase letters, numbers and hyphens")
        return normalized

    @field_validator("brand_name", "branch_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("name is required")
        return normalized

    @field_validator("branch_code")
    @classmethod
    def normalize_branch_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]*", normalized):
            raise ValueError("branch_code contains unsupported characters")
        return normalized


class CompanyWorkspaceProvisionRead(BaseSchema):
    created: bool
    created_resources: list[Literal["brand", "branch", "workspace"]]
    workspace: CompanyWorkspaceRead


class CompanyWorkspaceStatusUpdate(BaseSchema):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    active: bool
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason is required")
        return normalized
