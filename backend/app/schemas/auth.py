from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.schemas.user import UserRead


class LoginRequest(BaseModel):
    username: str
    password: str
    branch_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class BranchSwitchRequest(BaseModel):
    branch_id: uuid.UUID


class MeResponse(BaseModel):
    user: UserRead
    company_id: uuid.UUID
    branch_id: uuid.UUID | None
    permissions: list[str]
