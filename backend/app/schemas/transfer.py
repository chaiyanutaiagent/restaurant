from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid

from pydantic import ConfigDict, Field

from app.schemas import BaseSchema


class TOItemCreate(BaseSchema):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    qty_requested: Decimal


class TOItemApprove(BaseSchema):
    item_id: uuid.UUID
    qty_approved: Decimal


class TOItemReceive(BaseSchema):
    item_id: uuid.UUID
    qty_received: Decimal


class TOItemRead(BaseSchema):
    id: uuid.UUID
    to_id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    product_name: str
    sku: str
    unit_code: str | None = None
    qty_requested: Decimal
    qty_approved: Decimal | None = None
    qty_sent: Decimal | None = None
    qty_received: Decimal | None = None
    unit_cost: Decimal = Decimal("0")
    qty_in_transit: Decimal = Decimal("0")
    qty_discrepancy: Decimal = Decimal("0")

    model_config = ConfigDict(from_attributes=True)


class CreateTORequest(BaseSchema):
    from_branch_id: uuid.UUID
    to_branch_id: uuid.UUID
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    expected_date: date | None = None
    note: str | None = None
    items: list[TOItemCreate] = Field(default_factory=list)


class ApproveTORequest(BaseSchema):
    items: list[TOItemApprove] = Field(default_factory=list)
    note: str | None = None


class ShipTORequest(BaseSchema):
    note: str | None = None


class ReceiveTORequest(BaseSchema):
    items: list[TOItemReceive] = Field(default_factory=list)
    note: str | None = None
    finalize: bool = True


class CancelTORequest(BaseSchema):
    reason: str


class TransferOrderRead(BaseSchema):
    id: uuid.UUID
    to_number: str
    status: str
    from_branch_id: uuid.UUID
    to_branch_id: uuid.UUID
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    requested_by: uuid.UUID
    approved_by: uuid.UUID | None = None
    received_by: uuid.UUID | None = None
    request_date: date
    expected_date: date | None = None
    approved_at: datetime | None = None
    shipped_at: datetime | None = None
    last_received_at: datetime | None = None
    completed_at: datetime | None = None
    has_discrepancy: bool = False
    discrepancy_note: str | None = None
    note: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[TOItemRead] = Field(default_factory=list)
    from_branch_name: str
    to_branch_name: str
    from_location_name: str
    to_location_name: str
    requested_by_name: str

    model_config = ConfigDict(from_attributes=True)


class TOListItem(BaseSchema):
    id: uuid.UUID
    to_number: str
    status: str
    from_branch_name: str
    to_branch_name: str
    request_date: date
    expected_date: date | None = None
    item_count: int
    requested_by_name: str

    model_config = ConfigDict(from_attributes=True)


class BranchStockSummary(BaseSchema):
    branch_id: str
    branch_name: str
    location_count: int
    product_count: int
    total_value: Decimal
    low_stock_count: int
    zero_stock_count: int


class MultiBranchStockResponse(BaseSchema):
    branches: list[BranchStockSummary] = Field(default_factory=list)
    grand_total_value: Decimal
    grand_low_stock_count: int
