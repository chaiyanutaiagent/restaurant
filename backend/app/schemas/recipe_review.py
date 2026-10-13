from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

class IngredientProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    item_id: UUID | None = None
    requested_name: str = Field(default="", max_length=255)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=4)
    unit: str = Field(min_length=1, max_length=30)
    @model_validator(mode="after")
    def identity(self):
        if not self.item_id and not self.requested_name:
            raise ValueError("เลือกวัตถุดิบเดิมหรือระบุชื่อวัตถุดิบที่ขอเพิ่ม")
        return self

class RecipeProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    output_id: UUID
    name: str = Field(min_length=1, max_length=255)
    recipe_type: Literal["sale", "production"]
    yield_qty: Decimal = Field(gt=0, max_digits=14, decimal_places=4)
    yield_unit: str = Field(min_length=1, max_length=30)
    loss_percent: Decimal = Field(default=Decimal(0), ge=0, lt=100, decimal_places=4)
    effective_from: date
    reason: str = Field(min_length=3, max_length=1000)
    ingredients: list[IngredientProposal] = Field(min_length=1, max_length=200)
    @model_validator(mode="after")
    def unique(self):
        ids=[r.item_id for r in self.ingredients if r.item_id]
        names=[r.requested_name.casefold() for r in self.ingredients if not r.item_id]
        if len(set(ids)) != len(ids) or len(set(names)) != len(names) or self.output_id in ids:
            raise ValueError("วัตถุดิบต้องไม่ซ้ำและห้ามใช้สินค้าผลลัพธ์เป็นวัตถุดิบตัวเอง")
        return self

class ReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system: Literal["restaurant", "takeaway"]
    brand_id: UUID
    branch_id: UUID | None = None
    source_id: UUID | None = None
    request_key: UUID
    proposal: RecipeProposal

class ReviewAction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    revision: int = Field(ge=1)
    action: Literal["save", "submit", "return", "reject", "approve", "resolve"]
    reason: str = Field(min_length=3, max_length=1000)
    proposal: RecipeProposal | None = None
    line_index: int | None = Field(default=None, ge=0, le=199)
    item_id: UUID | None = None
