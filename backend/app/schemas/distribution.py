from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
import uuid

from pydantic import Field

from app.schemas import BaseSchema


DistributionModule = Literal["restaurant_pos", "takeaway_pos", "retail_pos"]


class DistributionDemandCreateRequest(BaseSchema):
    source_module: DistributionModule
    brand_id: uuid.UUID
    branch_id: uuid.UUID
    product_id: uuid.UUID
    needed_on: date
    requested_qty: Decimal = Field(gt=0)
    unit_code: str = Field(min_length=1, max_length=30)
    source_type: str = Field(min_length=1, max_length=50)
    source_id: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=8, max_length=120)
    note: str | None = Field(default=None, max_length=1000)


class DistributionShipmentPlanRequest(BaseSchema):
    demand_id: uuid.UUID
    planned_qty: Decimal = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=120)
    note: str | None = Field(default=None, max_length=1000)


class DistributionActionRequest(BaseSchema):
    idempotency_key: str = Field(min_length=8, max_length=120)
    note: str | None = Field(default=None, max_length=1000)


class DistributionReceiveRequest(DistributionActionRequest):
    cumulative_received_qty: Decimal = Field(ge=0)
    finalize: bool = False


class DistributionRejectRequest(DistributionActionRequest):
    reason: str = Field(min_length=3, max_length=500)


class DistributionReturnRequest(DistributionActionRequest):
    qty: Decimal = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)
