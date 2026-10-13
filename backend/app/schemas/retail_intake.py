from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas import BaseSchema


class RetailIntakeRequest(BaseSchema):
    request_id: UUID
    barcode: str = Field(min_length=1, max_length=100)
    existing_product_id: UUID | None = None
    name: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=2000)
    category_id: UUID | None = None
    unit_id: UUID | None = None
    selling_price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=15, decimal_places=4)
    cost_price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=15, decimal_places=4)
    qty: Decimal = Field(default=Decimal("0"), ge=0, max_digits=15, decimal_places=4)
    location_id: UUID | None = None
    vat_type: Literal["included", "excluded", "exempt"] = "included"
    vat_rate: Decimal = Field(default=Decimal("7"), ge=0, le=100, max_digits=5, decimal_places=2)

    @field_validator("barcode", "name", "description", mode="before")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_operation(self):
        if not self.existing_product_id and (not self.name or not self.unit_id):
            raise ValueError("กรุณาระบุชื่อสินค้าและหน่วยสินค้า")
        if self.qty > 0 and self.location_id is None:
            raise ValueError("กรุณาเลือกคลังรับสินค้า")
        if self.existing_product_id and self.qty <= 0:
            raise ValueError("จำนวนรับเพิ่มต้องมากกว่า 0")
        return self
