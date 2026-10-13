from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from app.schemas import BaseSchema


class RetailTransferLine(BaseSchema):
    product_id: UUID
    variant_id: UUID | None = None
    qty_requested: Decimal = Field(gt=0, max_digits=15, decimal_places=4)


class RetailTransferCreate(BaseSchema):
    request_id: UUID
    from_location_id: UUID
    to_location_id: UUID
    note: str = Field(default="", max_length=1000)
    items: list[RetailTransferLine] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_items(self):
        if len({(i.product_id,i.variant_id) for i in self.items}) != len(self.items):
            raise ValueError("รายการสินค้าซ้ำ")
        return self


class RetailTransferQuantity(BaseSchema):
    item_id: UUID
    quantity: Decimal = Field(ge=0, max_digits=15, decimal_places=4)


class RetailTransferCommand(BaseSchema):
    request_id: UUID
    expected_version: int = Field(ge=1)
    action: Literal["submit","approve","ship","receive","cancel"]
    items: list[RetailTransferQuantity] = Field(default_factory=list, max_length=100)
    note: str = Field(default="", max_length=1000)
    finalize: bool = False

    @model_validator(mode="after")
    def unique_items(self):
        if len({i.item_id for i in self.items}) != len(self.items):
            raise ValueError("รายการสินค้าซ้ำ")
        if self.action == "cancel" and not self.note.strip():
            raise ValueError("กรุณาระบุเหตุผลยกเลิก")
        return self
