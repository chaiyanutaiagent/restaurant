from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
import uuid

from pydantic import Field, field_validator

from app.schemas import BaseSchema


ApprovalAction = Literal[
    "pos.discount.override",
    "pos.price.override",
    "pos.sale.void",
    "pos.refund.create",
    "inventory.stock.adjust",
    "fb.order.cancel_after_kitchen",
    "fb.order.cancel.reopen",
    "pos.cash_movement.approve",
    "pos.shift.variance.approve",
]


def _validate_six_digit_pin(value: str) -> str:
    normalized = value.strip()
    if len(normalized) != 6 or not normalized.isascii() or not normalized.isdigit():
        raise ValueError("Manager PIN must contain exactly 6 digits")
    return normalized


class ManagerPinSetRequest(BaseSchema):
    current_password: str = Field(min_length=1, max_length=200)
    pin: str

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, value: str) -> str:
        normalized = _validate_six_digit_pin(value)
        if len(set(normalized)) == 1 or normalized in {"123456", "654321"}:
            raise ValueError("Manager PIN is too easy to guess")
        return normalized


class ManagerPinStatusRead(BaseSchema):
    is_set: bool
    pin_set_at: datetime | None = None
    locked_until: datetime | None = None


class ApprovalSessionRequest(BaseSchema):
    approver_username: str = Field(min_length=1, max_length=100)
    manager_pin: str
    action: ApprovalAction
    reason: str = Field(min_length=3, max_length=500)
    request_payload: dict[str, Any]

    @field_validator("approver_username", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("manager_pin")
    @classmethod
    def validate_manager_pin(cls, value: str) -> str:
        return _validate_six_digit_pin(value)


class ApprovalSessionRead(BaseSchema):
    approval_token: str
    expires_in: int
    action: ApprovalAction
    approver_id: uuid.UUID
    approver_display_name: str
    request_hash: str
