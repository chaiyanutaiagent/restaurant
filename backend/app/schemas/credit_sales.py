from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SaleLine(StrictRequest):
    product_id: UUID
    quantity: Decimal = Field(gt=0, le=100000, max_digits=12, decimal_places=4)


class CreditSaleCreate(StrictRequest):
    request_key: UUID
    customer_id: UUID
    description: str = Field(min_length=1, max_length=500)
    due_date: date
    items: list[SaleLine] = Field(min_length=1, max_length=100)


class SaleAction(StrictRequest):
    request_key: UUID
    reason: str = Field(min_length=1, max_length=1000)


class DeliveryRequest(SaleAction):
    location_id: UUID | None = None
    received_by: str = Field(min_length=1, max_length=200)


class ReceiptRequest(SaleAction):
    amount: Decimal = Field(gt=0, le=999999999, max_digits=12, decimal_places=2)
    method: Literal["cash", "bank_transfer"]
    reference: str = Field(min_length=1, max_length=200)
