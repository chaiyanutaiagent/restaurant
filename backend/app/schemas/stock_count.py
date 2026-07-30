from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid

from pydantic import ConfigDict, Field

from app.schemas import BaseSchema


class CreateCountSessionRequest(BaseSchema):
    branch_id: uuid.UUID
    location_id: uuid.UUID
    count_date: date | None = None
    note: str | None = None
    product_ids: list[uuid.UUID] | None = None


class CountItemRead(BaseSchema):
    id: uuid.UUID
    session_id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    product_name: str
    sku: str
    unit_code: str | None = None
    expected_qty: Decimal
    actual_qty: Decimal | None = None
    variance_qty: Decimal | None = None
    cost_per_unit: Decimal
    variance_value: Decimal | None = None
    counted_at: datetime | None = None
    counted_by: uuid.UUID | None = None
    note: str | None = None
    is_adjusted: bool

    model_config = ConfigDict(from_attributes=True)


class CountSessionRead(BaseSchema):
    id: uuid.UUID
    session_number: str
    status: str
    branch_id: uuid.UUID
    location_id: uuid.UUID
    count_date: date
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_by: uuid.UUID
    completed_by: uuid.UUID | None = None
    note: str | None = None
    total_items: int
    items_matched: int
    items_over: int
    items_short: int
    total_variance_value: Decimal
    items: list[CountItemRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class CountSessionListItem(BaseSchema):
    id: uuid.UUID
    session_number: str
    status: str
    branch_id: uuid.UUID
    location_id: uuid.UUID
    count_date: date
    created_by: uuid.UUID
    completed_by: uuid.UUID | None = None
    total_items: int
    items_matched: int
    items_over: int
    items_short: int
    total_variance_value: Decimal

    model_config = ConfigDict(from_attributes=True)


class UpdateCountItemRequest(BaseSchema):
    actual_qty: Decimal
    note: str | None = None


class BatchUpdateCountItem(BaseSchema):
    item_id: uuid.UUID
    actual_qty: Decimal
    note: str | None = None


class BatchUpdateCountRequest(BaseSchema):
    items: list[BatchUpdateCountItem] = Field(default_factory=list)


class CompleteSessionRequest(BaseSchema):
    apply_adjustments: bool = True
    note: str | None = None


class VarianceReportItem(BaseSchema):
    product_name: str
    sku: str
    unit_code: str | None = None
    expected_qty: Decimal
    actual_qty: Decimal
    variance_qty: Decimal
    variance_value: Decimal
    variance_pct: Decimal


class VarianceReport(BaseSchema):
    session_number: str
    location_name: str
    branch_name: str
    count_date: str
    count_date_thai: str
    completed_by_name: str
    items_matched: int
    items_over: int
    items_short: int
    total_variance_value: Decimal
    variances: list[VarianceReportItem] = Field(default_factory=list)
    matched_items: list[VarianceReportItem] = Field(default_factory=list)
