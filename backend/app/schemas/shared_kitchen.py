from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
import uuid

from pydantic import Field

from app.schemas import BaseSchema


class CompanyKitchenConfigureRequest(BaseSchema):
    branch_id: uuid.UUID
    raw_location_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    timezone: str = Field(default="Asia/Bangkok", min_length=1, max_length=50)


class CompanyIngredientCreateRequest(BaseSchema):
    canonical_product_id: uuid.UUID
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=255)
    base_unit_code: str = Field(min_length=1, max_length=30)
    unit_dimension: Literal["mass", "volume", "count"]


class CompanyIngredientAliasCreateRequest(BaseSchema):
    ingredient_id: uuid.UUID
    brand_id: uuid.UUID
    source_product_id: uuid.UUID
    source_unit_code: str = Field(min_length=1, max_length=30)
    conversion_factor: Decimal = Field(gt=0)
    supplier_sku: str | None = Field(default=None, max_length=100)


class CompanyIngredientReceiptRequest(BaseSchema):
    ingredient_id: uuid.UUID
    lot_code: str = Field(min_length=1, max_length=100)
    qty: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)
    expires_on: date | None = None
    idempotency_key: str = Field(min_length=8, max_length=120)
    reference_type: str = Field(default="goods_receipt", min_length=1, max_length=50)
    reference_id: str = Field(min_length=1, max_length=120)
    note: str | None = None


class CompanyProductionDemandCreateRequest(BaseSchema):
    brand_id: uuid.UUID
    branch_id: uuid.UUID
    output_product_id: uuid.UUID
    needed_on: date
    requested_qty: Decimal = Field(gt=0)
    unit_code: str = Field(min_length=1, max_length=30)
    source_type: str = Field(min_length=1, max_length=50)
    source_id: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=8, max_length=120)
    note: str | None = None


class CompanyProductionOrderCreateRequest(BaseSchema):
    brand_id: uuid.UUID
    output_product_id: uuid.UUID
    planned_date: date
    planned_qty: Decimal = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=120)
    demand_id: uuid.UUID | None = None
    recipe_id: uuid.UUID | None = None
    note: str | None = None


class CompanyProductionActualInput(BaseSchema):
    input_id: uuid.UUID
    actual_qty: Decimal = Field(ge=0)


class CompanyProductionCompleteRequest(BaseSchema):
    completion_key: str = Field(min_length=8, max_length=120)
    actual_output_qty: Decimal = Field(gt=0)
    waste_qty: Decimal = Field(default=Decimal("0"), ge=0)
    inputs: list[CompanyProductionActualInput] = Field(default_factory=list)
    note: str | None = None


class CompanyProductionReverseRequest(BaseSchema):
    reversal_key: str = Field(min_length=8, max_length=120)
    reason: str = Field(min_length=3, max_length=500)
