from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
import uuid

from pydantic import ConfigDict, Field, field_validator

from app.schemas import BaseSchema


class APIKeyRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    purpose: str
    owner_contact: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime
    revoked_at: datetime | None = None
    rotated_from_id: uuid.UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class APIKeyCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    purpose: str = Field(min_length=3, max_length=255)
    owner_contact: str = Field(min_length=3, max_length=255)
    scopes: list[str] = Field(min_length=1)
    expires_at: datetime

    @field_validator("scopes")
    @classmethod
    def reject_wildcard_scope(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(scope.strip() for scope in value if scope.strip()))
        if not normalized or "*" in normalized:
            raise ValueError("Explicit API scopes are required; wildcard is not allowed")
        return normalized


class APIKeyRotate(BaseSchema):
    reason: str = Field(min_length=3, max_length=500)
    expires_at: datetime


class APIKeyCreatedResponse(BaseSchema):
    key: APIKeyRead
    full_key: str


class WebhookEndpointRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    url: str
    events: list[str]
    secret_configured: bool = False
    secret_rotated_at: datetime | None = None
    incoming_source: str | None = None
    is_active: bool
    last_triggered_at: datetime | None = None
    failure_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebhookEndpointCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=8, max_length=500, pattern=r"^https://")
    events: list[str] = Field(min_length=1)
    secret: str = Field(min_length=32, max_length=255)
    incoming_source: str | None = Field(default=None, min_length=3, max_length=50, pattern=r"^[a-z0-9][a-z0-9_-]{1,48}[a-z0-9]$")


class WebhookSecretRotate(BaseSchema):
    secret: str = Field(min_length=32, max_length=255)
    reason: str = Field(min_length=3, max_length=500)


class WebhookDeliveryRead(BaseSchema):
    id: uuid.UUID
    webhook_id: uuid.UUID
    event_type: str
    response_status: int | None = None
    status: str
    attempt_count: int
    last_error_code: str | None = None
    delivered_at: datetime | None = None
    failed_at: datetime | None = None
    next_retry_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExternalOrderRead(BaseSchema):
    id: uuid.UUID
    source: str
    external_order_id: str
    status: str
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_email: str | None = None
    customer_address: str | None = None
    items_json: list[dict]
    total_amount: Decimal
    server_total_amount: Decimal | None = None
    review_reasons: list[str] = Field(default_factory=list)
    payment_method: str | None = None
    payment_status: str | None = None
    sale_order_id: uuid.UUID | None = None
    notes: str | None = None
    received_at: datetime
    processed_at: datetime | None = None
    reviewed_at: datetime | None = None
    reviewed_by: uuid.UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class ExternalOrderReview(BaseSchema):
    decision: Literal["accept", "reject"]
    reason: str = Field(min_length=3, max_length=500)


class PublicProductRead(BaseSchema):
    id: uuid.UUID
    sku: str
    barcode: str | None = None
    name: str
    name_en: str | None = None
    description: str | None = None
    selling_price: Decimal
    vat_type: str
    vat_rate: Decimal
    category_id: uuid.UUID | None = None
    category_name: str | None = None
    unit_code: str | None = None
    image_url: str | None = None
    is_active: bool


class PublicStorefrontCompanyRead(BaseSchema):
    id: uuid.UUID
    name: str
    business_slug: str
    name_en: str | None = None
    tax_id: str | None = None
    vat_registered: bool
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    logo_url: str | None = None
    website: str | None = None
    currency: str
    timezone: str


class PublicStorefrontProductRead(PublicProductRead):
    total_qty_available: Decimal = Decimal("0")
    in_stock: bool = False


class PublicStorefrontBranchRead(BaseSchema):
    id: uuid.UUID
    code: str
    name: str
    name_en: str | None = None
    address: str | None = None
    landmark: str | None = None
    phone: str | None = None
    email: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    google_maps_url: str | None = None
    working_hours: dict | None = None
    is_active: bool
    is_pickup_available: bool


class PublicExperienceCapabilitiesRead(BaseSchema):
    catalog: bool = True
    branch_locator: bool = True
    ecommerce: bool = False
    checkout: bool = False
    payment: bool = False
    member_portal: bool = False
    digital_receipt: bool = False


class PublicExperienceRead(BaseSchema):
    mode: Literal["catalog_locator"] = "catalog_locator"
    release_stage: Literal["public_read_only"] = "public_read_only"
    generated_at: datetime
    stale_after_seconds: int = Field(default=300, ge=60, le=3600)
    capabilities: PublicExperienceCapabilitiesRead = Field(default_factory=PublicExperienceCapabilitiesRead)
    hard_holds: list[str] = Field(default_factory=list)


class PublicStorefrontSummaryRead(BaseSchema):
    company: PublicStorefrontCompanyRead
    featured_products: list[PublicStorefrontProductRead] = Field(default_factory=list)
    branches: list[PublicStorefrontBranchRead] = Field(default_factory=list)
    experience: PublicExperienceRead


class PublicStockLocationRead(BaseSchema):
    location_name: str
    branch_name: str
    qty_available: Decimal


class PublicStockRead(BaseSchema):
    product_id: uuid.UUID
    sku: str
    name: str
    total_qty_available: Decimal
    locations: list[PublicStockLocationRead]


class PublicOrderItem(BaseSchema):
    sku: str
    qty: int
    unit_price: Decimal


class PublicOrderCreate(BaseSchema):
    external_order_id: str
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_email: str | None = None
    customer_address: str | None = None
    items: list[PublicOrderItem] = Field(default_factory=list)
    total_amount: Decimal
    payment_method: str | None = None
    payment_status: str | None = None
    notes: str | None = None
