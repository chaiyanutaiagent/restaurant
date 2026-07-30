from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import uuid

from pydantic import ConfigDict, Field

from app.schemas import BaseSchema


class CarrierRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    code: str
    name: str
    name_en: str | None = None
    tracking_url: str | None = None
    is_cod: bool
    is_active: bool
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class ShippingRateRead(BaseSchema):
    id: uuid.UUID
    carrier_id: uuid.UUID
    service_name: str
    zone: str
    min_weight_g: int
    max_weight_g: int | None = None
    base_rate: Decimal
    per_kg_rate: Decimal
    cod_fee: Decimal
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ShippingEstimate(BaseSchema):
    carrier_id: str
    carrier_code: str
    carrier_name: str
    service_name: str
    cost: Decimal
    cod_fee: Decimal


class EstimateRequest(BaseSchema):
    weight_grams: int
    zone: str = "all"
    is_cod: bool = False


class ShipmentItemCreate(BaseSchema):
    product_id: uuid.UUID | None = None
    product_name: str
    sku: str | None = None
    qty: Decimal
    unit_price: Decimal | None = None


class CreateShipmentRequest(BaseSchema):
    branch_id: uuid.UUID
    carrier_id: uuid.UUID
    service_name: str | None = None
    sale_order_id: uuid.UUID | None = None
    external_order_id: uuid.UUID | None = None
    recipient_name: str
    recipient_phone: str
    recipient_address: str
    weight_grams: int
    width_cm: int | None = None
    height_cm: int | None = None
    depth_cm: int | None = None
    is_cod: bool = False
    cod_amount: Decimal = Decimal("0")
    shipping_cost: Decimal = Decimal("0")
    tracking_number: str | None = None
    note: str | None = None
    items: list[ShipmentItemCreate] = Field(default_factory=list)


class UpdateShipmentRequest(BaseSchema):
    tracking_number: str | None = None
    status: str | None = None
    note: str | None = None


class ShipmentStatusUpdateRequest(BaseSchema):
    status: str
    location: str | None = None
    note: str | None = None


class ShipmentEventRead(BaseSchema):
    id: uuid.UUID
    shipment_id: uuid.UUID
    status: str
    location: str | None = None
    note: str | None = None
    event_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ShipmentItemRead(BaseSchema):
    id: uuid.UUID
    product_id: uuid.UUID | None = None
    product_name: str
    sku: str | None = None
    qty: Decimal
    unit_price: Decimal | None = None

    model_config = ConfigDict(from_attributes=True)


class ShipmentRead(BaseSchema):
    id: uuid.UUID
    shipment_number: str
    status: str
    branch_id: uuid.UUID
    carrier_id: uuid.UUID
    sale_order_id: uuid.UUID | None = None
    external_order_id: uuid.UUID | None = None
    sender_name: str
    sender_phone: str
    sender_address: str
    recipient_name: str
    recipient_phone: str
    recipient_address: str
    weight_grams: int
    width_cm: int | None = None
    height_cm: int | None = None
    depth_cm: int | None = None
    service_name: str | None = None
    is_cod: bool
    cod_amount: Decimal
    shipping_cost: Decimal
    tracking_number: str | None = None
    picked_up_at: datetime | None = None
    delivered_at: datetime | None = None
    note: str | None = None
    created_at: datetime
    updated_at: datetime
    carrier_name: str
    carrier_code: str
    tracking_url: str | None = None
    items: list[ShipmentItemRead] = Field(default_factory=list)
    events: list[ShipmentEventRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ShipmentListItem(BaseSchema):
    id: uuid.UUID
    shipment_number: str
    status: str
    carrier_name: str
    carrier_code: str
    recipient_name: str
    recipient_phone: str
    tracking_number: str | None = None
    is_cod: bool
    cod_amount: Decimal
    shipping_cost: Decimal
    weight_grams: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
