from __future__ import annotations

import uuid

from pydantic import ConfigDict

from app.schemas import BaseSchema


class PermissionRead(BaseSchema):
    id: uuid.UUID
    code: str
    name: str
    module: str

    model_config = ConfigDict(from_attributes=True)


class RoleBase(BaseSchema):
    name: str
    description: str | None = None


class RoleCreate(RoleBase):
    permission_ids: list[uuid.UUID]
    is_branch_assignable: bool = False


class RoleUpdate(BaseSchema):
    name: str | None = None
    description: str | None = None
    permission_ids: list[uuid.UUID] | None = None
    is_branch_assignable: bool | None = None


class RoleRead(RoleBase):
    id: uuid.UUID
    company_id: uuid.UUID
    is_system: bool
    is_branch_assignable: bool
    permissions: list[PermissionRead]

    model_config = ConfigDict(from_attributes=True)
