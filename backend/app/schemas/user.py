from __future__ import annotations

from datetime import datetime
import uuid

from pydantic import ConfigDict

from app.schemas import BaseSchema


class UserBase(BaseSchema):
    username: str
    email: str | None = None
    phone: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseSchema):
    username: str | None = None
    email: str | None = None
    phone: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None


class UserPasswordChange(BaseSchema):
    current_password: str
    new_password: str


class UserRead(UserBase):
    id: uuid.UUID
    company_id: uuid.UUID
    is_active: bool
    is_superuser: bool
    last_login_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class UserBranchRead(BaseSchema):
    branch_id: uuid.UUID
    role_id: uuid.UUID
    is_default: bool

    model_config = ConfigDict(from_attributes=True)
