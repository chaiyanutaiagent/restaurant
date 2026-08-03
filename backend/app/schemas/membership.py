from __future__ import annotations

from datetime import datetime
import re
import uuid

from pydantic import Field, field_validator, model_validator

from app.schemas import BaseSchema


USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,99}$")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) > 255 or not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("email format is invalid")
    return normalized


class SaasSignupRequest(BaseSchema):
    company_name: str = Field(min_length=1, max_length=255)
    owner_display_name: str = Field(min_length=1, max_length=200)
    owner_email: str
    username: str
    password: str = Field(min_length=12, max_length=128)
    phone: str | None = Field(default=None, max_length=20)
    terms_accepted: bool
    privacy_accepted: bool

    @field_validator("company_name", "owner_display_name")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value is required")
        return normalized

    @field_validator("owner_email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not USERNAME_PATTERN.fullmatch(normalized):
            raise ValueError("username format is invalid")
        return normalized

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @model_validator(mode="after")
    def require_consents(self) -> "SaasSignupRequest":
        if not self.terms_accepted or not self.privacy_accepted:
            raise ValueError("terms and privacy acceptance are required")
        if self.password.lower() in {
            self.username.lower(),
            self.owner_email.lower(),
        }:
            raise ValueError("password must not match account identifiers")
        return self


class SaasSignupRead(BaseSchema):
    company_id: uuid.UUID
    status: str
    verification_required: bool = True
    message: str


class SaasEmailRequest(BaseSchema):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class SaasCredentialRequest(BaseSchema):
    token: str = Field(min_length=32, max_length=512)

    @field_validator("token")
    @classmethod
    def normalize_token(cls, value: str) -> str:
        return value.strip()


class SaasPasswordResetConfirm(SaasCredentialRequest):
    new_password: str = Field(min_length=12, max_length=128)


class SaasMembershipRead(BaseSchema):
    company_id: uuid.UUID
    owner_email: str
    status: str
    onboarding_state: str
    email_verified_at: datetime | None = None
    trial_started_at: datetime | None = None
    trial_ends_at: datetime | None = None
    trial_days_remaining: int | None = None


class SaasActionRead(BaseSchema):
    message: str
    membership: SaasMembershipRead | None = None
