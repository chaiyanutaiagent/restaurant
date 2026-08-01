from __future__ import annotations

import uuid
from typing import Literal

from pydantic import ConfigDict, Field, field_validator

from app.schemas import BaseSchema


RoleScope = Literal["company", "brand", "branch", "station"]


def unique_role_scopes(scopes: list[RoleScope] | None) -> list[RoleScope] | None:
    if scopes is None:
        return None
    if len(scopes) != len(set(scopes)):
        raise ValueError("allowed_scope_types contains duplicate scopes")
    return scopes


class PermissionRead(BaseSchema):
    id: uuid.UUID
    code: str
    name: str
    module: str

    model_config = ConfigDict(from_attributes=True)


class RolePresetRead(BaseSchema):
    key: str
    name: str
    description: str
    default_scope: RoleScope
    allowed_scopes: list[RoleScope]
    is_branch_assignable: bool
    permission_ids: list[uuid.UUID]
    permission_codes: list[str]
    missing_permission_codes: list[str]
    is_available: bool
    policy_version: str


class RoleBase(BaseSchema):
    name: str
    description: str | None = None


class RoleCreate(RoleBase):
    permission_ids: list[uuid.UUID]
    is_branch_assignable: bool = False
    allowed_scope_types: list[RoleScope] = Field(default_factory=lambda: ["branch"], min_length=1)

    _validate_scopes = field_validator("allowed_scope_types")(unique_role_scopes)


class RoleUpdate(BaseSchema):
    name: str | None = None
    description: str | None = None
    permission_ids: list[uuid.UUID] | None = None
    is_branch_assignable: bool | None = None
    allowed_scope_types: list[RoleScope] | None = Field(default=None, min_length=1)

    _validate_scopes = field_validator("allowed_scope_types")(unique_role_scopes)


class RoleRead(RoleBase):
    id: uuid.UUID
    company_id: uuid.UUID
    is_system: bool
    is_branch_assignable: bool
    allowed_scope_types: list[RoleScope]
    permissions: list[PermissionRead]

    model_config = ConfigDict(from_attributes=True)
