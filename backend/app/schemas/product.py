from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
import uuid

from pydantic import ConfigDict, Field

from app.schemas import BaseSchema


InventoryRole = Literal["central_raw", "central_ready", "store_local", "not_stocked"]


class UnitBase(BaseSchema):
    code: str
    name: str
    name_en: str | None = None
    decimal_places: int = 0
    is_active: bool = True


class UnitCreate(UnitBase):
    pass


class UnitUpdate(BaseSchema):
    code: str | None = None
    name: str | None = None
    name_en: str | None = None
    decimal_places: int | None = None
    is_active: bool | None = None


class UnitRead(UnitBase):
    id: uuid.UUID
    company_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CategoryBase(BaseSchema):
    code: str | None = None
    name: str
    name_en: str | None = None
    parent_id: uuid.UUID | None = None
    sort_order: int = 0
    is_active: bool = True


class CategoryCreate(CategoryBase):
    description: str | None = None


class CategoryUpdate(BaseSchema):
    code: str | None = None
    name: str | None = None
    name_en: str | None = None
    parent_id: uuid.UUID | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    description: str | None = None
    image_url: str | None = None


class CategoryRead(CategoryBase):
    id: uuid.UUID
    company_id: uuid.UUID
    image_url: str | None = None
    created_at: datetime
    children: list["CategoryRead"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


CategoryTree = CategoryRead


class ProductVariantBase(BaseSchema):
    sku: str
    barcode: str | None = None
    name: str
    attributes: dict | None = None
    cost_price: Decimal | None = None
    selling_price: Decimal | None = None
    is_active: bool = True
    sort_order: int = 0


class ProductVariantCreate(ProductVariantBase):
    product_id: uuid.UUID


class ProductVariantUpdate(BaseSchema):
    sku: str | None = None
    barcode: str | None = None
    name: str | None = None
    attributes: dict | None = None
    cost_price: Decimal | None = None
    selling_price: Decimal | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class ProductVariantRead(ProductVariantBase):
    id: uuid.UUID
    product_id: uuid.UUID
    image_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ProductImageRead(BaseSchema):
    id: uuid.UUID
    url: str
    filename: str
    is_primary: bool
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class ProductBase(BaseSchema):
    sku: str
    barcode: str | None = None
    name: str
    name_en: str | None = None
    description: str | None = None
    description_en: str | None = None
    product_type: str = "simple"
    inventory_role: InventoryRole | None = None
    cost_price: Decimal = Decimal("0")
    selling_price: Decimal = Decimal("0")
    vat_type: str = "included"
    vat_rate: Decimal = Decimal("7.00")
    category_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    is_active: bool = True
    is_for_sale: bool = True
    is_for_purchase: bool = True
    min_stock_qty: Decimal = Decimal("0")
    weight_grams: int | None = None


class ProductCreate(ProductBase):
    sku: str
    name: str
    selling_price: Decimal


class ProductUpdate(BaseSchema):
    sku: str | None = None
    barcode: str | None = None
    name: str | None = None
    name_en: str | None = None
    description: str | None = None
    description_en: str | None = None
    product_type: str | None = None
    inventory_role: InventoryRole | None = None
    cost_price: Decimal | None = None
    selling_price: Decimal | None = None
    vat_type: str | None = None
    vat_rate: Decimal | None = None
    category_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    is_active: bool | None = None
    is_for_sale: bool | None = None
    is_for_purchase: bool | None = None
    min_stock_qty: Decimal | None = None
    weight_grams: int | None = None
    image_url: str | None = None


class ProductRead(ProductBase):
    id: uuid.UUID
    company_id: uuid.UUID
    image_url: str | None = None
    created_at: datetime
    updated_at: datetime
    category: CategoryRead | None = None
    unit: UnitRead | None = None
    variants: list[ProductVariantRead] = Field(default_factory=list)
    images: list[ProductImageRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ProductListItem(BaseSchema):
    id: uuid.UUID
    sku: str
    barcode: str | None = None
    name: str
    product_type: str
    inventory_role: InventoryRole | None = None
    min_stock_qty: Decimal = Decimal("0")
    cost_price: Decimal
    selling_price: Decimal
    vat_type: str
    vat_rate: Decimal
    is_active: bool
    image_url: str | None = None
    category_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    unit: UnitRead | None = None
    brand_id: uuid.UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BranchProductReplacementRuleCreate(BaseSchema):
    source_product_id: uuid.UUID
    replacement_product_id: uuid.UUID


class BranchProductReplacementRuleRead(BaseSchema):
    id: uuid.UUID
    branch_id: uuid.UUID
    source_product_id: uuid.UUID
    source_product_name: str
    replacement_product_id: uuid.UUID
    replacement_product_name: str
    created_at: datetime


class PriceListBase(BaseSchema):
    name: str
    description: str | None = None
    currency: str = "THB"
    is_default: bool = False
    valid_from: date | None = None
    valid_until: date | None = None
    is_active: bool = True


class PriceListCreate(PriceListBase):
    pass


class PriceListUpdate(BaseSchema):
    name: str | None = None
    description: str | None = None
    currency: str | None = None
    is_default: bool | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    is_active: bool | None = None


class PriceListRead(PriceListBase):
    id: uuid.UUID
    company_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PriceListItemBase(BaseSchema):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    price: Decimal
    min_qty: Decimal = Decimal("1")


class PriceListItemCreate(PriceListItemBase):
    price_list_id: uuid.UUID


class PriceListItemUpdate(BaseSchema):
    price: Decimal | None = None
    min_qty: Decimal | None = None


class PriceListItemRead(PriceListItemBase):
    id: uuid.UUID
    price_list_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


CategoryRead.model_rebuild()
ProductRead.model_rebuild()
