from __future__ import annotations

from datetime import datetime
from typing import Literal
import uuid

from pydantic import Field, field_validator, model_validator

from app.schemas import BaseSchema


DeviceType = Literal["counter", "kitchen", "pickup"]
DeviceStatus = Literal["pending_pairing", "pairing_expired", "paired", "revoked"]


def _strip_required(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must not be blank")
    return normalized


class DeviceCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=100)
    device_type: DeviceType
    branch_id: uuid.UUID
    station_key: str | None = Field(default=None, max_length=100)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("name", "reason")
    @classmethod
    def strip_required(cls, value: str) -> str:
        return _strip_required(value)

    @field_validator("station_key")
    @classmethod
    def strip_station(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_station_shape(self) -> "DeviceCreate":
        if self.device_type == "kitchen" and self.station_key is None:
            raise ValueError("Kitchen devices require station_key")
        if self.device_type != "kitchen" and self.station_key is not None:
            raise ValueError("Only Kitchen devices may use station_key")
        return self


class DevicePairRequest(BaseSchema):
    company_id: uuid.UUID
    device_code: str = Field(min_length=6, max_length=24)
    pairing_pin: str

    @field_validator("device_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return _strip_required(value).upper()

    @field_validator("pairing_pin")
    @classmethod
    def validate_pin(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) != 6 or not normalized.isascii() or not normalized.isdigit():
            raise ValueError("Pairing PIN must contain exactly 6 digits")
        return normalized


class DeviceActionReason(BaseSchema):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return _strip_required(value)


class DeviceRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    branch_id: uuid.UUID
    device_code: str
    name: str
    device_type: DeviceType
    station_key: str | None = None
    status: DeviceStatus
    credential_version: int
    pairing_expires_at: datetime | None = None
    paired_at: datetime | None = None
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None
    revocation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class DeviceProvisioningRead(BaseSchema):
    device: DeviceRead
    pairing_pin: str
    pairing_expires_at: datetime
    pairing_qr_payload: str


class DeviceContextRead(BaseSchema):
    device_id: uuid.UUID
    company_id: uuid.UUID
    brand_id: uuid.UUID
    branch_id: uuid.UUID
    device_code: str
    name: str
    device_type: DeviceType
    station_key: str | None = None
    business_type: Literal["restaurant"]
    target_database: Literal["restaurant"]
    credential_version: int
    paired_at: datetime
    last_seen_at: datetime


class DevicePairRead(BaseSchema):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    device: DeviceContextRead
