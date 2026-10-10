"""Atomic recipe quick-create; never receives stock or changes existing products."""
from __future__ import annotations

import uuid
from decimal import Decimal
from fastapi import HTTPException
from pydantic import Field, field_validator
from typing import Literal
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.schemas import BaseSchema
from app.schemas.product import ProductListItem
from app.models.product import Product, Unit
from app.models.restaurant import Brand, BrandBranch
from app.models.stock import StockBalance, StockLocation
from app.models.audit import AuditLog
from app.models.shared_kitchen import CompanyKitchen, CompanyIngredient, CompanyIngredientAlias


class RecipeMaterialQuickCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    sku: str = Field(default="", max_length=100)
    unit: Literal["g", "kg", "ml", "l", "pcs"] = "kg"
    cost_price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=15, decimal_places=4)
    inventory_role: Literal["central_raw", "central_ready", "store_local"]
    idempotency_key: uuid.UUID
    use_company_kitchen: bool = False

    @field_validator("name", "sku", mode="before")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return " ".join(value.split()) if isinstance(value, str) else value


def material_identity(company_id: uuid.UUID, brand_id: uuid.UUID | None, key: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"recipe-material:{company_id}:{brand_id}:{key}")


async def create_recipe_material(
    db: AsyncSession, company_id: uuid.UUID, actor_id: uuid.UUID,
    payload: RecipeMaterialQuickCreate, brand: Brand | None = None,
) -> dict:
    try:
        return await _create_recipe_material(db, company_id, actor_id, payload, brand)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "มีข้อมูลวัตถุดิบหรือรหัสซ้ำ กรุณาค้นหารายการเดิมก่อนลองใหม่") from exc


async def _create_recipe_material(
    db: AsyncSession, company_id: uuid.UUID, actor_id: uuid.UUID,
    payload: RecipeMaterialQuickCreate, brand: Brand | None = None,
) -> dict:
    brand_id = brand.id if brand else None
    if brand is not None and brand.company_id != company_id:
        raise HTTPException(404, "ไม่พบแบรนด์ในบริษัทนี้")
    product_id = material_identity(company_id, brand_id, payload.idempotency_key)
    fingerprint = payload.model_dump(mode="json")
    # Serialize our creates per company: covers name, SKU, unit, balance and mapping races.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                     {"key": f"recipe-material:{company_id}"})
    existing = await db.scalar(select(Product).options(selectinload(Product.unit)).where(
        Product.id == product_id, Product.company_id == company_id))
    if existing:
        audit = await db.scalar(select(AuditLog).where(
            AuditLog.company_id == company_id, AuditLog.action == "recipe.material.quick_created",
            AuditLog.resource_id == str(product_id)))
        if not audit or audit.new_value.get("request") != fingerprint:
            raise HTTPException(409, "คำขอนี้เคยใช้กับข้อมูลอื่นแล้ว กรุณาเปิดหน้าสร้างวัตถุดิบใหม่")
        if existing.deleted_at or not existing.is_active:
            raise HTTPException(409, "วัตถุดิบนี้ถูกปิดใช้งานแล้ว กรุณาเลือกวัตถุดิบอื่น")
        return {**ProductListItem.model_validate(existing).model_dump(), "inventory_setup": audit.new_value["setup"]}

    sku = payload.sku or f"RAW-{product_id.hex[:24].upper()}"
    duplicate = await db.scalar(select(Product).where(
        Product.company_id == company_id, func.lower(Product.sku) == sku.lower()))
    if duplicate:
        raise HTTPException(409, "รหัสสินค้านี้มีอยู่แล้ว กรุณาเปลี่ยนรหัสหรือเลือกวัตถุดิบเดิม")
    duplicate = await db.scalar(select(Product).where(
        Product.company_id == company_id, Product.deleted_at.is_(None),
        or_(Product.brand_id == brand_id, Product.brand_id.is_(None)),
        func.lower(func.regexp_replace(func.trim(Product.name), r"\s+", " ", "g")) == payload.name.lower()))
    if duplicate:
        raise HTTPException(409, "มีวัตถุดิบชื่อนี้แล้ว กรุณาค้นหาและเลือกวัตถุดิบเดิม")

    location_ids: list[uuid.UUID] = []
    if payload.use_company_kitchen:
        if brand is None or payload.inventory_role != "central_raw":
            raise HTTPException(400, "กรุณาเลือกแบรนด์และวัตถุดิบสำหรับผลิตครัวกลาง")
        kitchen = await db.scalar(select(CompanyKitchen).where(
            CompanyKitchen.company_id == company_id, CompanyKitchen.is_active.is_(True)))
        if not kitchen:
            raise HTTPException(400, "กรุณาตั้งค่าคลังวัตถุดิบครัวกลางของบริษัทก่อน")
        location_ids = [kitchen.raw_location_id]
    elif brand:
        if payload.inventory_role == "store_local":
            location_ids = list((await db.scalars(select(BrandBranch.store_location_id).where(
                BrandBranch.company_id == company_id, BrandBranch.brand_id == brand.id,
                BrandBranch.is_active.is_(True), BrandBranch.store_location_id.is_not(None)))).all())
        else:
            location = brand.central_location_id if payload.inventory_role == "central_raw" else brand.central_ready_location_id
            if location:
                location_ids = [location]
        if not location_ids:
            raise HTTPException(400, "กรุณาตั้งค่าคลังของแบรนด์ให้ตรงกับแหล่งวัตถุดิบก่อน")

    locations = []
    for location_id in dict.fromkeys(location_ids):
        location = await db.scalar(select(StockLocation).where(
            StockLocation.id == location_id, StockLocation.company_id == company_id,
            StockLocation.deleted_at.is_(None), StockLocation.is_active.is_(True)))
        if not location:
            raise HTTPException(400, "ไม่พบคลังที่เปิดใช้งานในบริษัทนี้ กรุณาตรวจการตั้งค่าคลัง")
        locations.append(location)

    unit = await db.scalar(select(Unit).where(
        Unit.company_id == company_id, func.lower(Unit.code) == payload.unit))
    if unit and (unit.deleted_at or not unit.is_active):
        raise HTTPException(400, "หน่วยสต็อกนี้ถูกปิดใช้งาน กรุณาให้ผู้จัดการเปิดใช้งานก่อน")
    if not unit:
        unit = Unit(company_id=company_id, code=payload.unit.upper(), name=payload.unit,
                    decimal_places=0 if payload.unit == "pcs" else 4, is_active=True)
        db.add(unit)
        await db.flush()
    product = Product(id=product_id, company_id=company_id,
                      brand_id=None if payload.use_company_kitchen else brand_id,
                      sku=sku, name=payload.name, product_type="raw_material",
                      inventory_role=payload.inventory_role, unit_id=unit.id, cost_price=payload.cost_price,
                      selling_price=0, vat_type="included", vat_rate=7,
                      is_active=True, is_for_sale=False, is_for_purchase=True)
    db.add(product)
    await db.flush()
    for location in locations:
        db.add(StockBalance(company_id=company_id, branch_id=location.branch_id,
                            location_id=location.id, product_id=product.id,
                            qty_on_hand=0, qty_reserved=0, cost_per_unit=payload.cost_price))
    if payload.use_company_kitchen:
        ingredient = CompanyIngredient(company_id=company_id, canonical_product_id=product.id,
            code=f"RM-{product.id.hex}", name=product.name, base_unit_code=payload.unit,
            unit_dimension="mass" if payload.unit in {"kg", "g"} else "volume" if payload.unit in {"l", "ml"} else "count",
            is_active=True)
        db.add(ingredient)
        await db.flush()
        db.add(CompanyIngredientAlias(company_id=company_id, ingredient_id=ingredient.id,
            brand_id=brand_id, source_product_id=product.id, source_unit_code=payload.unit,
            conversion_factor=1, is_active=True))
    setup = {"zero_balances_created": len(locations), "mapping_created": payload.use_company_kitchen,
             "stock_deferred": not locations}
    db.add(AuditLog(company_id=company_id, user_id=actor_id, action="recipe.material.quick_created",
                    resource="Product", resource_id=str(product.id), new_value={"request": fingerprint, "setup": setup}))
    # All related records commit together; failed requests leave no partial stock/mapping.
    await db.flush()
    await db.refresh(product, ["unit"])
    result = {**ProductListItem.model_validate(product).model_dump(), "inventory_setup": setup}
    await db.commit()
    return result
