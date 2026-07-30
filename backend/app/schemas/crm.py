from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid

from app.schemas import BaseSchema


class CustomerTierRead(BaseSchema):
    id: uuid.UUID
    name: str
    name_th: str
    min_lifetime_spend: Decimal
    points_multiplier: Decimal
    color: str | None = None
    benefits: str | None = None
    sort_order: int
    is_active: bool


class LoyaltySettingsRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    earn_rate: Decimal
    earn_min_spend: Decimal
    redeem_rate: Decimal
    redeem_min_points: int
    redeem_max_pct: Decimal
    points_expiry_months: int
    enabled: bool
    require_phone: bool


class LoyaltySettingsUpdate(BaseSchema):
    earn_rate: Decimal | None = None
    earn_min_spend: Decimal | None = None
    redeem_rate: Decimal | None = None
    redeem_min_points: int | None = None
    redeem_max_pct: Decimal | None = None
    points_expiry_months: int | None = None
    enabled: bool | None = None
    require_phone: bool | None = None


class CustomerTagRead(BaseSchema):
    id: uuid.UUID
    name: str
    color: str


class CustomerTagCreate(BaseSchema):
    name: str
    color: str = "#6366f1"


class CustomerBase(BaseSchema):
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None
    phone: str | None = None
    email: str | None = None
    tax_id: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    address: str | None = None
    note: str | None = None


class CustomerCreate(CustomerBase):
    tag_ids: list[uuid.UUID] = []


class CustomerUpdate(CustomerBase):
    tag_ids: list[uuid.UUID] | None = None
    is_active: bool | None = None


class CustomerRead(CustomerBase):
    id: uuid.UUID
    company_id: uuid.UUID
    customer_code: str
    tier_id: uuid.UUID | None = None
    points_balance: int
    lifetime_spend: Decimal
    lifetime_points_earned: int
    lifetime_points_redeemed: int
    total_orders: int
    last_purchase_at: datetime | None = None
    is_active: bool
    is_blacklisted: bool
    created_at: datetime
    tier: CustomerTierRead | None = None
    tags: list[CustomerTagRead]


class CustomerListItem(BaseSchema):
    id: uuid.UUID
    customer_code: str
    display_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    email: str | None = None
    tier_id: uuid.UUID | None = None
    tier_name: str | None = None
    points_balance: int
    lifetime_spend: Decimal
    total_orders: int
    last_purchase_at: datetime | None = None
    is_active: bool


class PointsTransactionRead(BaseSchema):
    id: uuid.UUID
    customer_id: uuid.UUID
    transaction_type: str
    points: int
    balance_after: int
    reference_type: str | None = None
    reference_id: str | None = None
    spend_amount: Decimal | None = None
    redeem_amount: Decimal | None = None
    note: str | None = None
    expires_at: datetime | None = None
    created_at: datetime


class EarnPointsRequest(BaseSchema):
    customer_id: uuid.UUID
    sale_order_id: str
    spend_amount: Decimal
    note: str | None = None


class RedeemPointsRequest(BaseSchema):
    customer_id: uuid.UUID
    points_to_redeem: int
    sale_order_id: str | None = None


class RedeemPointsResponse(BaseSchema):
    points_redeemed: int
    discount_amount: Decimal
    new_balance: int


class CustomerPurchaseHistory(BaseSchema):
    total_orders: int
    total_spend: Decimal
    avg_order_value: Decimal
    first_purchase_at: str | None = None
    last_purchase_at: str | None = None
    recent_orders: list[dict]


class CustomerSearchResult(BaseSchema):
    id: uuid.UUID
    customer_code: str
    display_name: str | None = None
    phone: str | None = None
    points_balance: int
    tier_name: str | None = None


class AdjustPointsRequest(BaseSchema):
    customer_id: uuid.UUID
    points: int
    note: str
