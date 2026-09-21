from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from pydantic import ConfigDict, Field, field_validator

from app.schemas import BaseSchema
from app.schemas.role import PermissionRead, RoleScope, unique_role_scopes
from app.utils.promptpay import generate_promptpay_payload


class UserBranchDetail(BaseSchema):
    branch_id: uuid.UUID
    branch_name: str
    branch_code: str
    brand_id: uuid.UUID | None = None
    business_type: str | None = None
    target_database: str | None = None
    role_id: uuid.UUID
    role_name: str
    is_default: bool

    model_config = ConfigDict(from_attributes=True)


class UserCreateFull(BaseSchema):
    username: str
    email: str | None = None
    phone: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None
    password: str
    branch_id: uuid.UUID
    role_id: uuid.UUID


class UserUpdateFull(BaseSchema):
    email: str | None = None
    phone: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None
    is_active: bool | None = None


class UserDetailRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    username: str
    email: str | None = None
    phone: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None
    is_active: bool
    is_superuser: bool
    last_login_at: datetime | None = None
    created_at: datetime
    branches: list[UserBranchDetail]

    model_config = ConfigDict(from_attributes=True)


class AssignBranchRequest(BaseSchema):
    branch_id: uuid.UUID
    role_id: uuid.UUID
    is_default: bool = False


class RemoveBranchRequest(BaseSchema):
    branch_id: uuid.UUID


class ChangePasswordRequest(BaseSchema):
    new_password: str


class RoleCreateFull(BaseSchema):
    name: str
    description: str | None = None
    permission_ids: list[uuid.UUID]
    is_branch_assignable: bool = False
    allowed_scope_types: list[RoleScope] = Field(default_factory=lambda: ["branch"], min_length=1)

    _validate_scopes = field_validator("allowed_scope_types")(unique_role_scopes)


class RoleUpdateFull(BaseSchema):
    name: str | None = None
    description: str | None = None
    permission_ids: list[uuid.UUID] | None = None
    is_branch_assignable: bool | None = None
    allowed_scope_types: list[RoleScope] | None = Field(default=None, min_length=1)

    _validate_scopes = field_validator("allowed_scope_types")(unique_role_scopes)


class RoleDetailRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    description: str | None = None
    is_system: bool
    is_branch_assignable: bool
    allowed_scope_types: list[RoleScope]
    created_at: datetime
    permissions: list[PermissionRead]
    user_count: int

    model_config = ConfigDict(from_attributes=True)


class BranchSettingsRead(BaseSchema):
    id: uuid.UUID
    branch_id: uuid.UUID
    pos_receipt_header: str | None = None
    pos_receipt_footer: str | None = None
    pos_require_customer: bool
    pos_allow_discount: bool
    pos_max_discount_pct: float
    pos_cashier_discount_limit_pct: float = 10
    pos_price_override_auto_limit_pct: float = 10
    pos_price_override_auto_limit_amount: float = 100
    pos_price_override_max_deviation_pct: float = 50
    pos_price_override_min_margin_pct: float = 0
    pos_price_override_self_approval: bool = False
    pos_hold_draft_ttl_minutes: int = 120
    pos_cash_movement_approval_threshold: float = 1000
    pos_shift_variance_soft_threshold: float = 100
    pos_shift_variance_approval_threshold: float = 500
    stock_adjust_approval_threshold_qty: float = 10
    promptpay_target: str | None = None
    promptpay_name: str | None = None
    promptpay_qr_url: str | None = None
    working_hours: dict[str, Any] | None = None
    public_storefront_enabled: bool
    allow_negative_stock: bool
    low_stock_alert_enabled: bool
    receipt_show_tax_id: bool
    receipt_show_logo: bool
    receipt_logo_url: str | None = None
    receipt_copies: int
    notify_low_stock_email: str | None = None
    # F&B
    fb_enabled: bool = False
    fb_service_mode: str = "quick_service"
    fb_table_qr_enabled: bool = False
    fb_bill_at_table: bool = False
    fb_queue_enabled: bool = True
    fb_queue_reset: str = "daily"
    fb_queue_prefix: str = ""
    fb_pickup_display_enabled: bool = True
    fb_line_notify_token: str | None = None
    fb_line_mode: str = "group"
    fb_kitchen_stations: list[str] | None = None
    fb_setup_completed: bool = False
    fb_qs_qr_token: uuid.UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class BranchSettingsUpdate(BaseSchema):
    pos_receipt_header: str | None = None
    pos_receipt_footer: str | None = None
    pos_require_customer: bool | None = None
    pos_allow_discount: bool | None = None
    pos_max_discount_pct: float | None = Field(default=None, ge=0, le=100)
    pos_cashier_discount_limit_pct: float | None = Field(default=None, ge=0, le=100)
    pos_price_override_auto_limit_pct: float | None = Field(default=None, ge=0, le=100)
    pos_price_override_auto_limit_amount: float | None = Field(default=None, ge=0)
    pos_price_override_max_deviation_pct: float | None = Field(default=None, ge=0, le=100)
    pos_price_override_min_margin_pct: float | None = Field(default=None, ge=-100, le=100)
    pos_price_override_self_approval: bool | None = None
    pos_hold_draft_ttl_minutes: int | None = Field(default=None, ge=15, le=1440)
    pos_cash_movement_approval_threshold: float | None = Field(default=None, ge=0)
    pos_shift_variance_soft_threshold: float | None = Field(default=None, ge=0)
    pos_shift_variance_approval_threshold: float | None = Field(default=None, ge=0)
    stock_adjust_approval_threshold_qty: float | None = Field(default=None, ge=0)
    pos_default_price_list_id: uuid.UUID | None = None
    promptpay_target: str | None = None
    promptpay_name: str | None = None
    promptpay_qr_url: str | None = None
    working_hours: dict[str, Any] | None = None
    public_storefront_enabled: bool | None = None
    allow_negative_stock: bool | None = None
    low_stock_alert_enabled: bool | None = None
    receipt_show_tax_id: bool | None = None
    receipt_show_logo: bool | None = None
    receipt_logo_url: str | None = None
    receipt_copies: int | None = None
    notify_low_stock_email: str | None = None
    # F&B
    fb_enabled: bool | None = None
    fb_service_mode: str | None = None
    fb_table_qr_enabled: bool | None = None
    fb_bill_at_table: bool | None = None
    fb_queue_enabled: bool | None = None
    fb_queue_reset: str | None = None
    fb_queue_prefix: str | None = None
    fb_pickup_display_enabled: bool | None = None
    fb_line_notify_token: str | None = None
    fb_line_mode: str | None = None
    fb_kitchen_stations: list[str] | None = None
    fb_setup_completed: bool | None = None
    fb_qs_qr_token: uuid.UUID | None = None

    @field_validator("promptpay_target", mode="before")
    @classmethod
    def validate_promptpay_target(cls, value: Any) -> str | None:
        if value is None:
            return None
        target = str(value).strip()
        if not target:
            return None
        try:
            generate_promptpay_payload(target)
        except ValueError as exc:
            raise ValueError("PromptPay ต้องเป็นเบอร์มือถือไทย 10 หลักหรือเลขผู้เสียภาษี 13 หลัก") from exc
        return target


class BranchCreateFull(BaseSchema):
    code: str
    name: str
    name_en: str | None = None
    address: str | None = None
    landmark: str | None = None
    phone: str | None = None
    email: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    google_maps_url: str | None = None
    is_warehouse: bool = False
    sort_order: int = 0


class BranchUpdateFull(BaseSchema):
    name: str | None = None
    name_en: str | None = None
    address: str | None = None
    landmark: str | None = None
    phone: str | None = None
    email: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    google_maps_url: str | None = None
    is_active: bool | None = None
    is_warehouse: bool | None = None
    sort_order: int | None = None


class BranchDetailRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    brand_id: uuid.UUID | None = None
    business_type: str | None = None
    target_database: str | None = None
    code: str
    name: str
    name_en: str | None = None
    address: str | None = None
    landmark: str | None = None
    phone: str | None = None
    email: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    google_maps_url: str | None = None
    is_warehouse: bool
    is_active: bool
    sort_order: int
    created_at: datetime
    user_count: int
    settings: BranchSettingsRead | None = None

    model_config = ConfigDict(from_attributes=True)


class InviteUserRequest(BaseSchema):
    email: str | None = None
    phone: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    branch_id: uuid.UUID
    role_id: uuid.UUID


class InviteUserResponse(BaseSchema):
    invitation_id: uuid.UUID
    otp_code: str
    expires_at: datetime
    message: str


class AcceptInvitationRequest(BaseSchema):
    invitation_id: uuid.UUID | None = None
    otp_code: str = Field(min_length=1, max_length=8)
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)
