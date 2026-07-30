from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import uuid

from pydantic import Field

from app.schemas import BaseSchema


class GatewayConfigRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    omise_public_key: str | None
    omise_enabled: bool
    twoc2p_merchant_id: str | None
    twoc2p_enabled: bool
    promptpay_target: str | None
    promptpay_name: str | None
    promptpay_enabled: bool
    scb_enabled: bool
    line_notify_enabled: bool
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_from_email: str | None
    smtp_from_name: str | None
    smtp_enabled: bool


class GatewayConfigUpdate(BaseSchema):
    omise_public_key: str | None = None
    omise_secret_key: str | None = None
    omise_enabled: bool | None = None
    twoc2p_merchant_id: str | None = None
    twoc2p_secret_key: str | None = None
    twoc2p_enabled: bool | None = None
    promptpay_target: str | None = None
    promptpay_name: str | None = None
    promptpay_enabled: bool | None = None
    scb_api_key: str | None = None
    scb_api_secret: str | None = None
    scb_enabled: bool | None = None
    line_notify_token: str | None = None
    line_notify_enabled: bool | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str | None = None
    smtp_enabled: bool | None = None


class PaymentSessionRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    branch_id: uuid.UUID
    session_ref: str
    gateway: str
    method: str
    amount: Decimal
    currency: str
    status: str
    reference_type: str | None
    reference_id: str | None
    gateway_ref: str | None
    gateway_status: str | None
    qr_payload: str | None
    redirect_url: str | None
    expires_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    created_at: datetime


class CreatePromptPayRequest(BaseSchema):
    amount: Decimal
    branch_id: uuid.UUID
    reference_type: str | None = None
    reference_id: str | None = None


class CreateOmiseRequest(BaseSchema):
    amount: Decimal
    branch_id: uuid.UUID
    method: str = "credit_card"
    reference_type: str | None = None
    reference_id: str | None = None


class NotificationLogRead(BaseSchema):
    id: uuid.UUID
    channel: str
    recipient: str
    event_type: str
    subject: str | None
    status: str
    error_message: str | None
    sent_at: datetime
    reference_type: str | None
    reference_id: str | None


class PaymentSessionConfirmRequest(BaseSchema):
    gateway_ref: str | None = None


class NotificationTestRequest(BaseSchema):
    recipient: str | None = None
    message: str | None = Field(default=None, max_length=500)
