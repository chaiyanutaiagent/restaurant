from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import uuid

from pydantic import ConfigDict, Field

from app.schemas import BaseSchema


class APIKeyRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime
    revoked_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class APIKeyCreate(BaseSchema):
    name: str
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


class APIKeyCreatedResponse(BaseSchema):
    key: APIKeyRead
    full_key: str


class WebhookEndpointRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    url: str
    events: list[str]
    is_active: bool
    last_triggered_at: datetime | None = None
    failure_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebhookEndpointCreate(BaseSchema):
    name: str
    url: str
    events: list[str] = Field(default_factory=list)
    secret: str | None = None


class WebhookDeliveryRead(BaseSchema):
    id: uuid.UUID
    webhook_id: uuid.UUID
    event_type: str
    response_status: int | None = None
    attempt_count: int
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
    payment_method: str | None = None
    payment_status: str | None = None
    sale_order_id: uuid.UUID | None = None
    notes: str | None = None
    received_at: datetime
    processed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


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


class PublicStorefrontSummaryRead(BaseSchema):
    company: PublicStorefrontCompanyRead
    featured_products: list[PublicStorefrontProductRead] = Field(default_factory=list)
    branches: list[PublicStorefrontBranchRead] = Field(default_factory=list)


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
