from __future__ import annotations

from datetime import datetime
from typing import Literal
import uuid

from pydantic import Field, model_validator

from app.config import settings
from app.schemas import BaseSchema


UserAccessStatus = Literal["pending", "approved", "activated", "rejected", "cancelled"]


class UserAccessRequestCreate(BaseSchema):
    brand_slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    requested_role_id: uuid.UUID
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=6, max_length=128, repr=False)
    employee_id: uuid.UUID | None = None
    employee_code: str | None = Field(default=None, max_length=20)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    request_note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_contact(self) -> "UserAccessRequestCreate":
        self.first_name = self.first_name.strip()
        self.last_name = self.last_name.strip()
        self.email = self.email.strip().lower() if self.email and self.email.strip() else None
        self.phone = self.phone.strip() if self.phone and self.phone.strip() else None
        self.employee_code = self.employee_code.strip() if self.employee_code and self.employee_code.strip() else None
        self.request_note = self.request_note.strip() if self.request_note and self.request_note.strip() else None
        self.username = self.username.strip()
        if not self.first_name or not self.last_name:
            raise ValueError("กรุณากรอกชื่อและนามสกุล")
        if not self.email and not self.phone:
            raise ValueError("กรุณากรอก email หรือเบอร์โทรศัพท์อย่างน้อย 1 รายการ")
        if len(self.password) < 8 and not (
            settings.environment == "development" and self.password == "123456"
        ):
            raise ValueError("รหัสผ่านต้องมีอย่างน้อย 8 ตัวอักษร")
        return self


class UserAccessApproveRequest(BaseSchema):
    approved_role_id: uuid.UUID
    review_note: str | None = Field(default=None, max_length=2000)


class UserAccessRejectRequest(BaseSchema):
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_reason(self) -> "UserAccessRejectRequest":
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("กรุณาระบุเหตุผลที่ปฏิเสธ")
        return self


class UserAccessCancelRequest(BaseSchema):
    brand_slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    reason: str | None = Field(default=None, max_length=2000)


class BranchAssignableRoleRead(BaseSchema):
    id: uuid.UUID
    name: str
    description: str | None = None


class UserAccessRequestRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    brand_id: uuid.UUID | None = None
    brand_slug: str | None = None
    brand_name: str | None = None
    branch_id: uuid.UUID
    branch_code: str
    branch_name: str
    requested_role_id: uuid.UUID
    requested_role_name: str
    approved_role_id: uuid.UUID | None = None
    approved_role_name: str | None = None
    employee_id: uuid.UUID | None = None
    employee_code: str | None = None
    requested_username: str | None = None
    first_name: str
    last_name: str
    email: str | None = None
    phone: str | None = None
    request_note: str | None = None
    status: UserAccessStatus
    requested_by: uuid.UUID
    requester_name: str
    requested_at: datetime
    reviewed_by: uuid.UUID | None = None
    reviewer_name: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    activated_user_id: uuid.UUID | None = None
    activated_username: str | None = None
    activated_at: datetime | None = None
    invitation_id: uuid.UUID | None = None
    invitation_expires_at: datetime | None = None
    invitation_used_at: datetime | None = None
    invitation_revoked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UserAccessApprovalResult(BaseSchema):
    request: UserAccessRequestRead
    activation_mode: Literal["activated", "invitation"]
    created_username: str | None = None
    invitation_id: uuid.UUID | None = None
    company_id: uuid.UUID
    otp_code: str | None = None
    expires_at: datetime | None = None
