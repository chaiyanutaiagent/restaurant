from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
from sqlalchemy import func, nulls_last, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.product import Product
from app.models.restaurant import Brand, BrandBranch, Recipe, RecipeIngredient
from app.models.shared_kitchen import (
    CompanyIngredient,
    CompanyIngredientAlias,
    CompanyIngredientLot,
    CompanyKitchen,
    CompanyKitchenMovement,
    CompanyProductionDemand,
    CompanyProductionInput,
    CompanyProductionOrder,
)
from app.models.stock import StockBalance, StockLocation
from app.schemas.shared_kitchen import (
    CompanyIngredientAliasCreateRequest,
    CompanyIngredientCreateRequest,
    CompanyIngredientReceiptRequest,
    CompanyKitchenConfigureRequest,
    CompanyProductionCompleteRequest,
    CompanyProductionDemandCreateRequest,
    CompanyProductionOrderCreateRequest,
)
from app.services.stock_service import StockService


FOUR_PLACES = Decimal("0.0001")
EIGHT_PLACES = Decimal("0.00000001")
UNIT_FACTORS: dict[str, tuple[str, Decimal]] = {
    "mg": ("mass", Decimal("0.001")),
    "g": ("mass", Decimal("1")),
    "gram": ("mass", Decimal("1")),
    "กรัม": ("mass", Decimal("1")),
    "kg": ("mass", Decimal("1000")),
    "กก": ("mass", Decimal("1000")),
    "ml": ("volume", Decimal("1")),
    "มล": ("volume", Decimal("1")),
    "l": ("volume", Decimal("1000")),
    "liter": ("volume", Decimal("1000")),
    "ลิตร": ("volume", Decimal("1000")),
    "ea": ("count", Decimal("1")),
    "pc": ("count", Decimal("1")),
    "pcs": ("count", Decimal("1")),
    "piece": ("count", Decimal("1")),
    "ชิ้น": ("count", Decimal("1")),
    "ลูก": ("count", Decimal("1")),
    "ขวด": ("count", Decimal("1")),
    "ถุง": ("count", Decimal("1")),
}


def q4(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


def normalized_unit(unit_code: str) -> str:
    return unit_code.strip().lower().replace(".", "")


def unit_dimension(unit_code: str) -> str:
    normalized = normalized_unit(unit_code)
    try:
        return UNIT_FACTORS[normalized][0]
    except KeyError as exc:
        raise ValueError(f"ไม่รองรับหน่วย {unit_code}") from exc


def expected_conversion_factor(source_unit: str, base_unit: str) -> Decimal:
    source = UNIT_FACTORS.get(normalized_unit(source_unit))
    target = UNIT_FACTORS.get(normalized_unit(base_unit))
    if source is None or target is None:
        raise ValueError("หน่วยต้นทางหรือหน่วยกลางยังไม่อยู่ในรายการที่รองรับ")
    if source[0] != target[0]:
        raise ValueError("หน่วยต้นทางและหน่วยกลางอยู่คนละมิติ")
    return (source[1] / target[1]).quantize(EIGHT_PLACES)


def plan_fifo_allocations(
    lots: Iterable[tuple[uuid.UUID, Decimal, Decimal]],
    requested_qty: Decimal,
) -> list[tuple[uuid.UUID, Decimal, Decimal]]:
    """Allocate from an already FIFO-sorted lot list without allowing a negative result."""
    remaining = q4(requested_qty)
    if remaining <= 0:
        return []
    allocations: list[tuple[uuid.UUID, Decimal, Decimal]] = []
    for lot_id, available, unit_cost in lots:
        available_qty = max(q4(available), Decimal("0"))
        if available_qty <= 0:
            continue
        issued = min(remaining, available_qty)
        allocations.append((lot_id, issued, q4(unit_cost)))
        remaining = q4(remaining - issued)
        if remaining <= 0:
            break
    if remaining > 0:
        raise ValueError(f"วัตถุดิบไม่พอ ขาด {remaining}")
    return allocations


def aggregate_demands(
    rows: Iterable[tuple[uuid.UUID, uuid.UUID, date, Decimal]],
) -> dict[tuple[uuid.UUID, uuid.UUID, date], Decimal]:
    grouped: dict[tuple[uuid.UUID, uuid.UUID, date], Decimal] = defaultdict(lambda: Decimal("0"))
    for brand_id, product_id, needed_on, qty in rows:
        key = (brand_id, product_id, needed_on)
        grouped[key] = q4(grouped[key] + q4(qty))
    return dict(grouped)


class SharedKitchenService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _transaction_lock(self, company_id: uuid.UUID, key: str) -> None:
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"shared-kitchen:{company_id}:{key}"},
        )

    async def _kitchen(self, company_id: uuid.UUID, *, lock: bool = False) -> CompanyKitchen:
        statement = select(CompanyKitchen).where(
            CompanyKitchen.company_id == company_id,
            CompanyKitchen.is_active.is_(True),
        )
        if lock:
            statement = statement.with_for_update()
        kitchen = await self.db.scalar(statement)
        if kitchen is None:
            raise HTTPException(status_code=409, detail="กรุณาตั้งค่าครัวกลางของบริษัทก่อน")
        return kitchen

    @staticmethod
    def _ingredient_data(row: CompanyIngredient, qty_on_hand: Decimal = Decimal("0")) -> dict[str, Any]:
        return {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "canonical_product_id": row.canonical_product_id,
            "base_unit_code": row.base_unit_code,
            "unit_dimension": row.unit_dimension,
            "qty_on_hand": q4(qty_on_hand),
            "is_active": row.is_active,
        }

    @staticmethod
    def _demand_data(row: CompanyProductionDemand) -> dict[str, Any]:
        return {
            "id": row.id,
            "brand_id": row.brand_id,
            "brand_name": row.brand.name if row.brand else "",
            "branch_id": row.branch_id,
            "branch_name": row.branch.name if row.branch else "",
            "output_product_id": row.output_product_id,
            "output_product_name": row.output_product.name if row.output_product else "",
            "needed_on": row.needed_on,
            "requested_qty": row.requested_qty,
            "unit_code": row.unit_code,
            "status": row.status,
            "source_type": row.source_type,
            "source_id": row.source_id,
            "note": row.note,
        }

    @staticmethod
    def _order_data(row: CompanyProductionOrder) -> dict[str, Any]:
        return {
            "id": row.id,
            "order_number": row.order_number,
            "brand_id": row.brand_id,
            "brand_name": row.brand.name if row.brand else "",
            "output_product_id": row.output_product_id,
            "output_product_name": row.output_product.name if row.output_product else "",
            "planned_date": row.planned_date,
            "status": row.status,
            "planned_qty": row.planned_qty,
            "actual_output_qty": row.actual_output_qty,
            "waste_qty": row.waste_qty,
            "output_unit_code": row.output_unit_code,
            "total_input_cost": row.total_input_cost,
            "output_cost_per_unit": row.output_cost_per_unit,
            "demand_id": row.demand_id,
            "recipe_id": row.recipe_id,
            "note": row.note,
            "inputs": [
                {
                    "id": item.id,
                    "ingredient_id": item.ingredient_id,
                    "ingredient_name": item.ingredient.name if item.ingredient else "",
                    "planned_qty": item.planned_qty,
                    "actual_qty": item.actual_qty,
                    "base_unit_code": item.base_unit_code,
                    "actual_cost": item.actual_cost,
                }
                for item in row.inputs
            ],
        }

    async def configure(
        self,
        company_id: uuid.UUID,
        actor_id: uuid.UUID,
        payload: CompanyKitchenConfigureRequest,
    ) -> dict[str, Any]:
        await self._transaction_lock(company_id, "configuration")
        try:
            ZoneInfo(payload.timezone.strip())
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status_code=400, detail="timezone ของครัวกลางไม่ถูกต้อง") from exc
        branch = await self.db.scalar(
            select(Branch).where(
                Branch.id == payload.branch_id,
                Branch.company_id == company_id,
                Branch.deleted_at.is_(None),
                Branch.is_active.is_(True),
            )
        )
        location = await self.db.scalar(
            select(StockLocation).where(
                StockLocation.id == payload.raw_location_id,
                StockLocation.company_id == company_id,
                StockLocation.branch_id == payload.branch_id,
                StockLocation.deleted_at.is_(None),
                StockLocation.is_active.is_(True),
            )
        )
        if branch is None or location is None:
            raise HTTPException(status_code=400, detail="สาขาหรือคลังวัตถุดิบกลางไม่ถูกต้อง")
        kitchen = await self.db.scalar(
            select(CompanyKitchen).where(CompanyKitchen.company_id == company_id).with_for_update()
        )
        if kitchen is None:
            kitchen = CompanyKitchen(
                company_id=company_id,
                branch_id=payload.branch_id,
                raw_location_id=payload.raw_location_id,
                name=payload.name.strip(),
                timezone=payload.timezone.strip(),
                costing_method="fifo",
                allow_negative_stock=False,
                is_active=True,
                created_by=actor_id,
            )
            self.db.add(kitchen)
        else:
            if kitchen.raw_location_id != payload.raw_location_id:
                lot_count = int(
                    await self.db.scalar(
                        select(func.count(CompanyIngredientLot.id)).where(
                            CompanyIngredientLot.company_id == company_id,
                            CompanyIngredientLot.kitchen_id == kitchen.id,
                        )
                    )
                    or 0
                )
                if lot_count:
                    raise HTTPException(
                        status_code=409,
                        detail="เปลี่ยน RAW location ไม่ได้หลังเริ่มสร้าง Lot; ต้องปิดและทำ migration plan แยก",
                    )
            kitchen.branch_id = payload.branch_id
            kitchen.raw_location_id = payload.raw_location_id
            kitchen.name = payload.name.strip()
            kitchen.timezone = payload.timezone.strip()
            kitchen.costing_method = "fifo"
            kitchen.allow_negative_stock = False
            kitchen.is_active = True
        await self.db.flush()
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=payload.branch_id,
                user_id=actor_id,
                action="company_kitchen.configured",
                resource="CompanyKitchen",
                resource_id=str(kitchen.id),
                new_value={"raw_location_id": str(payload.raw_location_id), "costing_method": "fifo"},
            )
        )
        await self.db.commit()
        await self.db.refresh(kitchen)
        return {
            "id": kitchen.id,
            "name": kitchen.name,
            "branch_id": kitchen.branch_id,
            "branch_name": branch.name,
            "raw_location_id": kitchen.raw_location_id,
            "raw_location_name": location.name,
            "timezone": kitchen.timezone,
            "costing_method": kitchen.costing_method,
            "allow_negative_stock": kitchen.allow_negative_stock,
            "is_active": kitchen.is_active,
        }

    async def create_ingredient(
        self,
        company_id: uuid.UUID,
        actor_id: uuid.UUID,
        payload: CompanyIngredientCreateRequest,
    ) -> dict[str, Any]:
        await self._transaction_lock(company_id, f"ingredient:{payload.code.strip().lower()}")
        existing_ingredient = await self.db.scalar(
            select(CompanyIngredient).where(
                CompanyIngredient.company_id == company_id,
                (
                    (CompanyIngredient.code == payload.code.strip().upper())
                    | (CompanyIngredient.canonical_product_id == payload.canonical_product_id)
                ),
            )
        )
        if existing_ingredient is not None:
            raise HTTPException(status_code=409, detail="รหัสหรือสินค้า Company นี้เป็นวัตถุดิบกลางแล้ว")
        try:
            detected_dimension = unit_dimension(payload.base_unit_code)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if detected_dimension != payload.unit_dimension:
            raise HTTPException(status_code=400, detail="มิติของหน่วยกลางไม่ตรงกับหน่วยที่เลือก")
        product = await self.db.scalar(
            select(Product).options(selectinload(Product.unit)).where(
                Product.id == payload.canonical_product_id,
                Product.company_id == company_id,
                Product.deleted_at.is_(None),
                Product.is_active.is_(True),
            )
        )
        if product is None or product.brand_id is not None or product.inventory_role != "central_raw":
            raise HTTPException(
                status_code=400,
                detail="วัตถุดิบกลางต้องเป็นสินค้า Company ที่ไม่ผูก Brand และมีบทบาท central_raw",
            )
        if product.unit is None or normalized_unit(product.unit.code) != normalized_unit(
            payload.base_unit_code
        ):
            raise HTTPException(
                status_code=400,
                detail="หน่วยกลางต้องตรงกับหน่วยของสินค้า Company",
            )
        ingredient = CompanyIngredient(
            company_id=company_id,
            canonical_product_id=product.id,
            code=payload.code.strip().upper(),
            name=payload.name.strip(),
            base_unit_code=normalized_unit(payload.base_unit_code),
            unit_dimension=payload.unit_dimension,
            is_active=True,
        )
        self.db.add(ingredient)
        await self.db.flush()
        self.db.add(
            AuditLog(
                company_id=company_id,
                user_id=actor_id,
                action="company_ingredient.created",
                resource="CompanyIngredient",
                resource_id=str(ingredient.id),
                new_value={"code": ingredient.code, "product_id": str(product.id)},
            )
        )
        await self.db.commit()
        await self.db.refresh(ingredient)
        return self._ingredient_data(ingredient)

    async def create_alias(
        self,
        company_id: uuid.UUID,
        actor_id: uuid.UUID,
        payload: CompanyIngredientAliasCreateRequest,
    ) -> dict[str, Any]:
        await self._transaction_lock(
            company_id, f"alias:{payload.brand_id}:{payload.source_product_id}"
        )
        existing_alias = await self.db.scalar(
            select(CompanyIngredientAlias).where(
                CompanyIngredientAlias.company_id == company_id,
                CompanyIngredientAlias.brand_id == payload.brand_id,
                CompanyIngredientAlias.source_product_id == payload.source_product_id,
            )
        )
        if existing_alias is not None:
            raise HTTPException(status_code=409, detail="สินค้าในสูตรของแบรนด์นี้มี Mapping แล้ว")
        ingredient = await self.db.scalar(
            select(CompanyIngredient).where(
                CompanyIngredient.id == payload.ingredient_id,
                CompanyIngredient.company_id == company_id,
                CompanyIngredient.is_active.is_(True),
            )
        )
        brand = await self.db.scalar(
            select(Brand).where(
                Brand.id == payload.brand_id,
                Brand.company_id == company_id,
                Brand.is_active.is_(True),
            )
        )
        product = await self.db.scalar(
            select(Product).options(selectinload(Product.unit)).where(
                Product.id == payload.source_product_id,
                Product.company_id == company_id,
                Product.deleted_at.is_(None),
                Product.is_active.is_(True),
            )
        )
        if ingredient is None or brand is None or product is None:
            raise HTTPException(status_code=404, detail="ไม่พบวัตถุดิบกลาง แบรนด์ หรือสินค้าในบริษัทนี้")
        if product.brand_id not in {None, brand.id} or product.inventory_role != "central_raw":
            raise HTTPException(status_code=400, detail="สินค้าต้นทางต้องเป็นวัตถุดิบ central_raw ของแบรนด์นี้")
        if product.unit is None or normalized_unit(product.unit.code) != normalized_unit(
            payload.source_unit_code
        ):
            raise HTTPException(status_code=400, detail="หน่วยต้นทางต้องตรงกับหน่วยของสินค้าในสูตร")
        try:
            expected = expected_conversion_factor(
                payload.source_unit_code, ingredient.base_unit_code
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        supplied = Decimal(str(payload.conversion_factor)).quantize(EIGHT_PLACES)
        if supplied != expected:
            raise HTTPException(
                status_code=400,
                detail=f"conversion factor ไม่ตรงกับหน่วย ค่าที่ถูกต้องคือ {expected}",
            )
        alias = CompanyIngredientAlias(
            company_id=company_id,
            ingredient_id=ingredient.id,
            brand_id=brand.id,
            source_product_id=product.id,
            source_unit_code=normalized_unit(payload.source_unit_code),
            conversion_factor=supplied,
            supplier_sku=(payload.supplier_sku or "").strip() or None,
            is_active=True,
        )
        self.db.add(alias)
        await self.db.flush()
        self.db.add(
            AuditLog(
                company_id=company_id,
                user_id=actor_id,
                action="company_ingredient.alias_created",
                resource="CompanyIngredientAlias",
                resource_id=str(alias.id),
                new_value={
                    "brand_id": str(brand.id),
                    "source_product_id": str(product.id),
                    "ingredient_id": str(ingredient.id),
                },
            )
        )
        await self.db.commit()
        return {
            "id": alias.id,
            "ingredient_id": ingredient.id,
            "ingredient_name": ingredient.name,
            "brand_id": brand.id,
            "brand_name": brand.name,
            "source_product_id": product.id,
            "source_product_name": product.name,
            "source_unit_code": alias.source_unit_code,
            "conversion_factor": alias.conversion_factor,
            "supplier_sku": alias.supplier_sku,
        }

    async def receive(
        self,
        company_id: uuid.UUID,
        actor_id: uuid.UUID,
        payload: CompanyIngredientReceiptRequest,
    ) -> dict[str, Any]:
        await self._transaction_lock(company_id, f"receipt:{payload.idempotency_key}")
        existing = await self.db.scalar(
            select(CompanyKitchenMovement).options(selectinload(CompanyKitchenMovement.lot)).where(
                CompanyKitchenMovement.company_id == company_id,
                CompanyKitchenMovement.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            if (
                existing.movement_type != "receipt"
                or existing.ingredient_id != payload.ingredient_id
                or q4(existing.qty) != q4(payload.qty)
                or q4(existing.unit_cost) != q4(payload.unit_cost)
                or existing.lot.lot_code != payload.lot_code.strip().upper()
                or existing.reference_type != payload.reference_type.strip()
                or existing.reference_id != payload.reference_id.strip()
            ):
                raise HTTPException(status_code=409, detail="idempotency key ถูกใช้กับข้อมูลรับเข้าคนละรายการ")
            return {"movement_id": existing.id, "qty_after": existing.qty_after, "replayed": True}
        kitchen = await self._kitchen(company_id, lock=True)
        ingredient = await self.db.scalar(
            select(CompanyIngredient).where(
                CompanyIngredient.id == payload.ingredient_id,
                CompanyIngredient.company_id == company_id,
                CompanyIngredient.is_active.is_(True),
            )
        )
        if ingredient is None:
            raise HTTPException(status_code=404, detail="ไม่พบวัตถุดิบกลาง")
        await self._transaction_lock(
            company_id, f"lot:{ingredient.id}:{payload.lot_code.strip().upper()}"
        )
        lot = await self.db.scalar(
            select(CompanyIngredientLot)
            .where(
                CompanyIngredientLot.kitchen_id == kitchen.id,
                CompanyIngredientLot.ingredient_id == ingredient.id,
                CompanyIngredientLot.lot_code == payload.lot_code.strip().upper(),
            )
            .with_for_update()
        )
        qty = q4(payload.qty)
        unit_cost = q4(payload.unit_cost)
        if lot is None:
            lot = CompanyIngredientLot(
                company_id=company_id,
                kitchen_id=kitchen.id,
                ingredient_id=ingredient.id,
                lot_code=payload.lot_code.strip().upper(),
                expires_on=payload.expires_on,
                qty_on_hand=Decimal("0"),
                unit_cost=unit_cost,
            )
            self.db.add(lot)
            await self.db.flush()
        before = q4(lot.qty_on_hand)
        after = q4(before + qty)
        if after > 0:
            lot.unit_cost = q4(((before * q4(lot.unit_cost)) + (qty * unit_cost)) / after)
        lot.qty_on_hand = after
        if payload.expires_on is not None:
            lot.expires_on = payload.expires_on
        movement = CompanyKitchenMovement(
            company_id=company_id,
            kitchen_id=kitchen.id,
            ingredient_id=ingredient.id,
            lot_id=lot.id,
            location_id=kitchen.raw_location_id,
            movement_type="receipt",
            qty=qty,
            qty_before=before,
            qty_after=after,
            unit_cost=unit_cost,
            idempotency_key=payload.idempotency_key,
            reference_type=payload.reference_type.strip(),
            reference_id=payload.reference_id.strip(),
            note=(payload.note or "").strip() or None,
            actor_id=actor_id,
        )
        self.db.add(movement)
        await self.db.commit()
        return {"movement_id": movement.id, "lot_id": lot.id, "qty_after": after, "replayed": False}

    async def create_demand(
        self,
        company_id: uuid.UUID,
        actor_id: uuid.UUID,
        payload: CompanyProductionDemandCreateRequest,
    ) -> dict[str, Any]:
        await self._transaction_lock(company_id, f"demand:{payload.idempotency_key}")
        statement = (
            select(CompanyProductionDemand)
            .options(
                selectinload(CompanyProductionDemand.brand),
                selectinload(CompanyProductionDemand.branch),
                selectinload(CompanyProductionDemand.output_product),
            )
            .where(
                CompanyProductionDemand.company_id == company_id,
                CompanyProductionDemand.idempotency_key == payload.idempotency_key,
            )
        )
        existing = await self.db.scalar(statement)
        if existing is not None:
            if (
                existing.brand_id != payload.brand_id
                or existing.branch_id != payload.branch_id
                or existing.output_product_id != payload.output_product_id
                or existing.needed_on != payload.needed_on
                or q4(existing.requested_qty) != q4(payload.requested_qty)
                or existing.unit_code != normalized_unit(payload.unit_code)
                or existing.source_type != payload.source_type.strip()
                or existing.source_id != payload.source_id.strip()
            ):
                raise HTTPException(status_code=409, detail="idempotency key ถูกใช้กับ Demand คนละรายการ")
            return {**self._demand_data(existing), "replayed": True}
        mapping = await self.db.scalar(
            select(BrandBranch).where(
                BrandBranch.company_id == company_id,
                BrandBranch.brand_id == payload.brand_id,
                BrandBranch.branch_id == payload.branch_id,
                BrandBranch.is_active.is_(True),
            )
        )
        product = await self.db.scalar(
            select(Product).options(selectinload(Product.unit)).where(
                Product.id == payload.output_product_id,
                Product.company_id == company_id,
                Product.brand_id == payload.brand_id,
                Product.inventory_role == "central_ready",
                Product.deleted_at.is_(None),
                Product.is_active.is_(True),
            )
        )
        if mapping is None or product is None:
            raise HTTPException(status_code=400, detail="สาขา/แบรนด์หรือสินค้าสำเร็จรูปไม่ถูกต้อง")
        if product.unit is None or normalized_unit(product.unit.code) != normalized_unit(
            payload.unit_code
        ):
            raise HTTPException(status_code=400, detail="หน่วย Demand ต้องตรงกับหน่วยสินค้าสำเร็จรูป")
        demand = CompanyProductionDemand(
            company_id=company_id,
            brand_id=payload.brand_id,
            branch_id=payload.branch_id,
            output_product_id=product.id,
            needed_on=payload.needed_on,
            requested_qty=q4(payload.requested_qty),
            unit_code=normalized_unit(payload.unit_code),
            status="submitted",
            source_type=payload.source_type.strip(),
            source_id=payload.source_id.strip(),
            idempotency_key=payload.idempotency_key,
            requested_by=actor_id,
            note=(payload.note or "").strip() or None,
        )
        self.db.add(demand)
        await self.db.commit()
        saved = await self.db.scalar(statement)
        return {**self._demand_data(saved), "replayed": False}  # type: ignore[arg-type]

    async def _recipe_for_order(
        self,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        output_product_id: uuid.UUID,
        recipe_id: uuid.UUID | None,
    ) -> Recipe:
        filters = [
            Recipe.company_id == company_id,
            Recipe.brand_id == brand_id,
            Recipe.product_id == output_product_id,
            Recipe.recipe_type == "production_recipe",
            Recipe.is_active.is_(True),
        ]
        if recipe_id is not None:
            filters.append(Recipe.id == recipe_id)
        recipe = await self.db.scalar(
            select(Recipe)
            .options(selectinload(Recipe.ingredients))
            .where(*filters)
            .order_by(Recipe.version_no.desc())
            .limit(1)
        )
        if recipe is None:
            raise HTTPException(status_code=400, detail="ไม่พบสูตรผลิตของแบรนด์สำหรับสินค้านี้")
        if q4(recipe.yield_qty) <= 0 or not recipe.ingredients:
            raise HTTPException(status_code=400, detail="สูตรผลิตไม่มี yield หรือวัตถุดิบที่ถูกต้อง")
        return recipe

    async def create_order(
        self,
        company_id: uuid.UUID,
        actor_id: uuid.UUID,
        payload: CompanyProductionOrderCreateRequest,
    ) -> dict[str, Any]:
        await self._transaction_lock(company_id, f"order:{payload.idempotency_key}")
        existing = await self._load_order_by_key(company_id, payload.idempotency_key)
        if existing is not None:
            if (
                existing.brand_id != payload.brand_id
                or existing.output_product_id != payload.output_product_id
                or existing.planned_date != payload.planned_date
                or q4(existing.planned_qty) != q4(payload.planned_qty)
                or existing.demand_id != payload.demand_id
                or (payload.recipe_id is not None and existing.recipe_id != payload.recipe_id)
            ):
                raise HTTPException(status_code=409, detail="idempotency key ถูกใช้กับใบผลิตคนละรายการ")
            return {**self._order_data(existing), "replayed": True}
        kitchen = await self._kitchen(company_id, lock=True)
        brand = await self.db.scalar(
            select(Brand).where(
                Brand.id == payload.brand_id,
                Brand.company_id == company_id,
                Brand.is_active.is_(True),
            )
        )
        product = await self.db.scalar(
            select(Product)
            .options(selectinload(Product.unit))
            .where(
                Product.id == payload.output_product_id,
                Product.company_id == company_id,
                Product.brand_id == payload.brand_id,
                Product.inventory_role == "central_ready",
                Product.deleted_at.is_(None),
                Product.is_active.is_(True),
            )
        )
        if brand is None or product is None or brand.central_ready_location_id is None:
            raise HTTPException(
                status_code=400,
                detail="แบรนด์ สินค้าสำเร็จรูป หรือคลัง READY ของแบรนด์ยังไม่พร้อม",
            )
        ready_location = await self.db.scalar(
            select(StockLocation).where(
                StockLocation.id == brand.central_ready_location_id,
                StockLocation.company_id == company_id,
                StockLocation.deleted_at.is_(None),
                StockLocation.is_active.is_(True),
            )
        )
        if ready_location is None:
            raise HTTPException(status_code=400, detail="คลัง READY ของแบรนด์ไม่ถูกต้อง")
        demand: CompanyProductionDemand | None = None
        if payload.demand_id is not None:
            demand = await self.db.scalar(
                select(CompanyProductionDemand)
                .where(
                    CompanyProductionDemand.id == payload.demand_id,
                    CompanyProductionDemand.company_id == company_id,
                    CompanyProductionDemand.brand_id == brand.id,
                    CompanyProductionDemand.output_product_id == product.id,
                    CompanyProductionDemand.status == "submitted",
                )
                .with_for_update()
            )
            if demand is None:
                raise HTTPException(status_code=409, detail="Demand ถูกใช้แล้วหรือไม่ตรงกับแบรนด์/สินค้า")
            if q4(demand.requested_qty) != q4(payload.planned_qty):
                raise HTTPException(
                    status_code=409,
                    detail="WP5 ต้องสร้างใบผลิตเท่ากับจำนวน Demand; การแบ่งผลิตต้องวางแผนแยก",
                )
        recipe = await self._recipe_for_order(
            company_id, brand.id, product.id, payload.recipe_id
        )
        source_ids = [item.ingredient_id for item in recipe.ingredients]
        aliases = list(
            (
                await self.db.scalars(
                    select(CompanyIngredientAlias)
                    .options(selectinload(CompanyIngredientAlias.ingredient))
                    .where(
                        CompanyIngredientAlias.company_id == company_id,
                        CompanyIngredientAlias.brand_id == brand.id,
                        CompanyIngredientAlias.source_product_id.in_(source_ids),
                        CompanyIngredientAlias.is_active.is_(True),
                    )
                )
            ).all()
        )
        aliases_by_product = {item.source_product_id: item for item in aliases}
        planned_by_ingredient: dict[uuid.UUID, Decimal] = defaultdict(lambda: Decimal("0"))
        ingredient_rows: dict[uuid.UUID, CompanyIngredient] = {}
        production_ratio = q4(payload.planned_qty) / q4(recipe.yield_qty)
        for line in recipe.ingredients:
            alias = aliases_by_product.get(line.ingredient_id)
            if alias is None:
                raise HTTPException(
                    status_code=409,
                    detail=f"วัตถุดิบในสูตร {line.ingredient_id} ยังไม่ได้ map เป็น Company ingredient",
                )
            if normalized_unit(line.unit) != alias.source_unit_code:
                raise HTTPException(
                    status_code=409,
                    detail=f"หน่วยในสูตร {line.unit} ไม่ตรงกับ alias {alias.source_unit_code}",
                )
            planned_base = q4(
                q4(line.quantity) * production_ratio * Decimal(alias.conversion_factor)
            )
            planned_by_ingredient[alias.ingredient_id] = q4(
                planned_by_ingredient[alias.ingredient_id] + planned_base
            )
            ingredient_rows[alias.ingredient_id] = alias.ingredient
        if any(qty <= 0 for qty in planned_by_ingredient.values()):
            raise HTTPException(status_code=400, detail="สูตรคำนวณวัตถุดิบได้ไม่ถูกต้อง")
        order = CompanyProductionOrder(
            company_id=company_id,
            kitchen_id=kitchen.id,
            brand_id=brand.id,
            demand_id=demand.id if demand else None,
            recipe_id=recipe.id,
            output_product_id=product.id,
            ready_location_id=ready_location.id,
            order_number=f"CK-{payload.planned_date:%y%m%d}-{uuid.uuid4().hex[:6].upper()}",
            planned_date=payload.planned_date,
            status="planned",
            planned_qty=q4(payload.planned_qty),
            output_unit_code=product.unit.code if product.unit else recipe.yield_unit,
            idempotency_key=payload.idempotency_key,
            planned_by=actor_id,
            note=(payload.note or "").strip() or None,
        )
        self.db.add(order)
        await self.db.flush()
        for ingredient_id, planned_qty in planned_by_ingredient.items():
            ingredient = ingredient_rows[ingredient_id]
            self.db.add(
                CompanyProductionInput(
                    company_id=company_id,
                    order_id=order.id,
                    ingredient_id=ingredient_id,
                    planned_qty=planned_qty,
                    base_unit_code=ingredient.base_unit_code,
                )
            )
        if demand is not None:
            demand.status = "converted"
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=kitchen.branch_id,
                user_id=actor_id,
                action="company_production_order.created",
                resource="CompanyProductionOrder",
                resource_id=str(order.id),
                new_value={"brand_id": str(brand.id), "output_product_id": str(product.id)},
            )
        )
        await self.db.commit()
        saved = await self._load_order(company_id, order.id)
        return {**self._order_data(saved), "replayed": False}

    async def _load_order_by_key(
        self, company_id: uuid.UUID, idempotency_key: str
    ) -> CompanyProductionOrder | None:
        return await self.db.scalar(
            select(CompanyProductionOrder)
            .options(
                selectinload(CompanyProductionOrder.brand),
                selectinload(CompanyProductionOrder.kitchen),
                selectinload(CompanyProductionOrder.output_product),
                selectinload(CompanyProductionOrder.inputs).selectinload(
                    CompanyProductionInput.ingredient
                ),
            )
            .where(
                CompanyProductionOrder.company_id == company_id,
                CompanyProductionOrder.idempotency_key == idempotency_key,
            )
        )

    async def _load_order(
        self, company_id: uuid.UUID, order_id: uuid.UUID, *, lock: bool = False
    ) -> CompanyProductionOrder:
        statement = (
            select(CompanyProductionOrder)
            .options(
                selectinload(CompanyProductionOrder.brand),
                selectinload(CompanyProductionOrder.kitchen),
                selectinload(CompanyProductionOrder.output_product),
                selectinload(CompanyProductionOrder.inputs).selectinload(
                    CompanyProductionInput.ingredient
                ),
            )
            .where(
                CompanyProductionOrder.id == order_id,
                CompanyProductionOrder.company_id == company_id,
            )
        )
        if lock:
            statement = statement.with_for_update()
        order = await self.db.scalar(statement)
        if order is None:
            raise HTTPException(status_code=404, detail="ไม่พบใบผลิตของครัวกลาง")
        return order

    async def start_order(
        self, company_id: uuid.UUID, actor_id: uuid.UUID, order_id: uuid.UUID
    ) -> dict[str, Any]:
        await self._transaction_lock(company_id, f"order-state:{order_id}")
        order = await self._load_order(company_id, order_id, lock=True)
        if order.status == "in_progress":
            return self._order_data(order)
        if order.status != "planned":
            raise HTTPException(status_code=409, detail="เริ่มผลิตได้เฉพาะใบผลิตที่วางแผนไว้")
        order.status = "in_progress"
        order.started_by = actor_id
        order.started_at = datetime.now(timezone.utc)
        await self.db.commit()
        return self._order_data(await self._load_order(company_id, order_id))

    async def complete_order(
        self,
        company_id: uuid.UUID,
        actor_id: uuid.UUID,
        order_id: uuid.UUID,
        payload: CompanyProductionCompleteRequest,
    ) -> dict[str, Any]:
        await self._transaction_lock(company_id, f"complete:{order_id}")
        order = await self._load_order(company_id, order_id, lock=True)
        if order.status == "completed" and order.completion_key == payload.completion_key:
            replay_inputs = {item.input_id: q4(item.actual_qty) for item in payload.inputs}
            stored_inputs = {item.id: q4(item.actual_qty) for item in order.inputs}
            if (
                q4(order.actual_output_qty) != q4(payload.actual_output_qty)
                or q4(order.waste_qty) != q4(payload.waste_qty)
                or any(stored_inputs.get(input_id) != qty for input_id, qty in replay_inputs.items())
            ):
                raise HTTPException(status_code=409, detail="completion key ถูกใช้กับผลผลิตคนละรายการ")
            return {**self._order_data(order), "replayed": True}
        if order.status != "in_progress":
            raise HTTPException(status_code=409, detail="ยืนยันผลิตได้เฉพาะใบที่กำลังผลิต")
        overrides = {item.input_id: q4(item.actual_qty) for item in payload.inputs}
        if len(overrides) != len(payload.inputs):
            raise HTTPException(status_code=400, detail="มี actual input ซ้ำ")
        input_ids = {item.id for item in order.inputs}
        if not set(overrides).issubset(input_ids):
            raise HTTPException(status_code=400, detail="มี actual input ที่ไม่อยู่ในใบผลิต")
        actual_by_input = {
            item.id: overrides.get(item.id, q4(item.planned_qty)) for item in order.inputs
        }
        if not any(value > 0 for value in actual_by_input.values()):
            raise HTTPException(status_code=400, detail="ต้องใช้วัตถุดิบจริงอย่างน้อย 1 รายการ")
        ingredient_ids = sorted(
            {item.ingredient_id for item in order.inputs if actual_by_input[item.id] > 0},
            key=str,
        )
        lots = list(
            (
                await self.db.scalars(
                    select(CompanyIngredientLot)
                    .where(
                        CompanyIngredientLot.company_id == company_id,
                        CompanyIngredientLot.kitchen_id == order.kitchen_id,
                        CompanyIngredientLot.ingredient_id.in_(ingredient_ids),
                        CompanyIngredientLot.qty_on_hand > 0,
                    )
                    .order_by(
                        CompanyIngredientLot.ingredient_id,
                        nulls_last(CompanyIngredientLot.expires_on.asc()),
                        CompanyIngredientLot.received_at.asc(),
                        CompanyIngredientLot.id.asc(),
                    )
                    .with_for_update()
                )
            ).all()
        )
        lots_by_ingredient: dict[uuid.UUID, list[CompanyIngredientLot]] = defaultdict(list)
        for lot in lots:
            lots_by_ingredient[lot.ingredient_id].append(lot)
        total_cost = Decimal("0")
        try:
            for item in sorted(order.inputs, key=lambda value: str(value.ingredient_id)):
                actual_qty = actual_by_input[item.id]
                item.actual_qty = actual_qty
                allocations = plan_fifo_allocations(
                    [
                        (lot.id, q4(lot.qty_on_hand), q4(lot.unit_cost))
                        for lot in lots_by_ingredient[item.ingredient_id]
                    ],
                    actual_qty,
                )
                item_cost = Decimal("0")
                lots_by_id = {lot.id: lot for lot in lots_by_ingredient[item.ingredient_id]}
                for lot_id, issued_qty, unit_cost in allocations:
                    lot = lots_by_id[lot_id]
                    before = q4(lot.qty_on_hand)
                    after = q4(before - issued_qty)
                    lot.qty_on_hand = after
                    item_cost += issued_qty * unit_cost
                    self.db.add(
                        CompanyKitchenMovement(
                            company_id=company_id,
                            kitchen_id=order.kitchen_id,
                            ingredient_id=item.ingredient_id,
                            lot_id=lot.id,
                            location_id=order.kitchen.raw_location_id,
                            brand_id=order.brand_id,
                            production_order_id=order.id,
                            movement_type="production_issue",
                            qty=-issued_qty,
                            qty_before=before,
                            qty_after=after,
                            unit_cost=unit_cost,
                            idempotency_key=f"{payload.completion_key}:{item.id}:{lot.id}",
                            reference_type="company_production_order",
                            reference_id=str(order.id),
                            note=(payload.note or order.note or "").strip() or None,
                            actor_id=actor_id,
                        )
                    )
                item.actual_cost = q4(item_cost)
                total_cost += item_cost
        except ValueError as exc:
            await self.db.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        # Lock the Brand output product so parallel orders cannot create duplicate READY balances.
        await self.db.scalar(
            select(Product).where(Product.id == order.output_product_id).with_for_update()
        )
        output_balance = await self.db.scalar(
            select(StockBalance)
            .where(
                StockBalance.company_id == company_id,
                StockBalance.location_id == order.ready_location_id,
                StockBalance.product_id == order.output_product_id,
                StockBalance.variant_id.is_(None),
            )
            .with_for_update()
        )
        if output_balance is None:
            ready_location = await self.db.get(StockLocation, order.ready_location_id)
            if ready_location is None:
                await self.db.rollback()
                raise HTTPException(status_code=409, detail="ไม่พบคลัง READY ของแบรนด์")
            output_balance = StockBalance(
                company_id=company_id,
                branch_id=ready_location.branch_id,
                location_id=ready_location.id,
                product_id=order.output_product_id,
                variant_id=None,
                qty_on_hand=Decimal("0"),
                qty_reserved=Decimal("0"),
                cost_per_unit=Decimal("0"),
            )
            self.db.add(output_balance)
            await self.db.flush()
        output_qty = q4(payload.actual_output_qty)
        output_cost = q4(total_cost / output_qty)
        await StockService(self.db)._record_movement(
            balance=output_balance,
            movement_type="receive",
            qty_delta=output_qty,
            user_id=actor_id,
            cost_per_unit=output_cost,
            reference_type="company_production_order",
            reference_id=str(order.id),
            note=(payload.note or order.note or "").strip() or None,
        )
        order.status = "completed"
        order.completion_key = payload.completion_key
        order.actual_output_qty = output_qty
        order.waste_qty = q4(payload.waste_qty)
        order.total_input_cost = q4(total_cost)
        order.output_cost_per_unit = output_cost
        order.completed_by = actor_id
        order.completed_at = datetime.now(timezone.utc)
        if payload.note:
            order.note = payload.note.strip()
        self.db.add(
            AuditLog(
                company_id=company_id,
                user_id=actor_id,
                action="company_production_order.completed",
                resource="CompanyProductionOrder",
                resource_id=str(order.id),
                old_value={"status": "in_progress"},
                new_value={
                    "status": "completed",
                    "brand_id": str(order.brand_id),
                    "input_cost": str(q4(total_cost)),
                    "output_qty": str(output_qty),
                    "waste_qty": str(q4(payload.waste_qty)),
                },
            )
        )
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        saved = await self._load_order(company_id, order.id)
        return {**self._order_data(saved), "replayed": False}

    async def reverse_order(
        self,
        company_id: uuid.UUID,
        actor_id: uuid.UUID,
        order_id: uuid.UUID,
        reversal_key: str,
        reason: str,
    ) -> dict[str, Any]:
        await self._transaction_lock(company_id, f"reverse:{order_id}")
        order = await self._load_order(company_id, order_id, lock=True)
        if order.status == "reversed" and order.reversal_key == reversal_key:
            return {**self._order_data(order), "replayed": True}
        if order.status != "completed" or order.actual_output_qty is None:
            raise HTTPException(status_code=409, detail="ย้อนรายการได้เฉพาะใบผลิตที่สำเร็จแล้ว")
        issues = list(
            (
                await self.db.scalars(
                    select(CompanyKitchenMovement).where(
                        CompanyKitchenMovement.company_id == company_id,
                        CompanyKitchenMovement.production_order_id == order.id,
                        CompanyKitchenMovement.movement_type == "production_issue",
                    )
                )
            ).all()
        )
        lot_ids = sorted({movement.lot_id for movement in issues}, key=str)
        lots = list(
            (
                await self.db.scalars(
                    select(CompanyIngredientLot)
                    .where(CompanyIngredientLot.id.in_(lot_ids))
                    .order_by(CompanyIngredientLot.id)
                    .with_for_update()
                )
            ).all()
        )
        lots_by_id = {lot.id: lot for lot in lots}
        if len(lots_by_id) != len(lot_ids):
            raise HTTPException(status_code=409, detail="Lot ต้นทางของใบผลิตไม่ครบ")
        await self.db.scalar(
            select(Product).where(Product.id == order.output_product_id).with_for_update()
        )
        output_balance = await self.db.scalar(
            select(StockBalance)
            .where(
                StockBalance.company_id == company_id,
                StockBalance.location_id == order.ready_location_id,
                StockBalance.product_id == order.output_product_id,
                StockBalance.variant_id.is_(None),
            )
            .with_for_update()
        )
        available_output = q4(output_balance.qty_on_hand if output_balance else 0) - q4(
            output_balance.qty_reserved if output_balance else 0
        )
        if output_balance is None or available_output < q4(order.actual_output_qty):
            raise HTTPException(
                status_code=409,
                detail="สินค้าสำเร็จรูปถูกใช้หรือโอนไปแล้ว จึงย้อนใบผลิตอัตโนมัติไม่ได้",
            )
        for issue in issues:
            lot = lots_by_id[issue.lot_id]
            before = q4(lot.qty_on_hand)
            restored = abs(q4(issue.qty))
            after = q4(before + restored)
            lot.qty_on_hand = after
            self.db.add(
                CompanyKitchenMovement(
                    company_id=company_id,
                    kitchen_id=order.kitchen_id,
                    ingredient_id=issue.ingredient_id,
                    lot_id=lot.id,
                    location_id=issue.location_id,
                    brand_id=order.brand_id,
                    production_order_id=order.id,
                    reversal_of_id=issue.id,
                    movement_type="production_reversal",
                    qty=restored,
                    qty_before=before,
                    qty_after=after,
                    unit_cost=issue.unit_cost,
                    idempotency_key=f"{reversal_key}:{issue.id}",
                    reference_type="company_production_reversal",
                    reference_id=str(order.id),
                    note=reason.strip(),
                    actor_id=actor_id,
                )
            )
        await StockService(self.db)._record_movement(
            balance=output_balance,
            movement_type="issue",
            qty_delta=-q4(order.actual_output_qty),
            user_id=actor_id,
            cost_per_unit=q4(order.output_cost_per_unit),
            reference_type="company_production_reversal",
            reference_id=str(order.id),
            note=reason.strip(),
        )
        order.status = "reversed"
        order.reversal_key = reversal_key
        order.reversed_by = actor_id
        order.reversed_at = datetime.now(timezone.utc)
        self.db.add(
            AuditLog(
                company_id=company_id,
                user_id=actor_id,
                action="company_production_order.reversed",
                resource="CompanyProductionOrder",
                resource_id=str(order.id),
                old_value={"status": "completed"},
                new_value={"status": "reversed", "reason": reason.strip()},
            )
        )
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return {**self._order_data(await self._load_order(company_id, order.id)), "replayed": False}

    async def cancel_order(
        self, company_id: uuid.UUID, actor_id: uuid.UUID, order_id: uuid.UUID, reason: str
    ) -> dict[str, Any]:
        await self._transaction_lock(company_id, f"cancel:{order_id}")
        order = await self._load_order(company_id, order_id, lock=True)
        if order.status == "cancelled":
            return self._order_data(order)
        if order.status not in {"planned", "in_progress"}:
            raise HTTPException(status_code=409, detail="ยกเลิกใบผลิตในสถานะนี้ไม่ได้")
        order.status = "cancelled"
        order.note = f"{order.note + ' · ' if order.note else ''}ยกเลิก: {reason.strip()}"
        if order.demand_id is not None:
            demand = await self.db.get(CompanyProductionDemand, order.demand_id)
            if demand is not None and demand.status == "converted":
                demand.status = "submitted"
        self.db.add(
            AuditLog(
                company_id=company_id,
                user_id=actor_id,
                action="company_production_order.cancelled",
                resource="CompanyProductionOrder",
                resource_id=str(order.id),
                new_value={"reason": reason.strip()},
            )
        )
        await self.db.commit()
        return self._order_data(await self._load_order(company_id, order.id))

    async def dashboard(self, company_id: uuid.UUID) -> dict[str, Any]:
        kitchen = await self.db.scalar(
            select(CompanyKitchen).where(CompanyKitchen.company_id == company_id)
        )
        ingredient_rows = list(
            (
                await self.db.execute(
                    select(
                        CompanyIngredient,
                        func.coalesce(func.sum(CompanyIngredientLot.qty_on_hand), 0),
                    )
                    .outerjoin(
                        CompanyIngredientLot,
                        (CompanyIngredientLot.ingredient_id == CompanyIngredient.id)
                        & (CompanyIngredientLot.company_id == company_id),
                    )
                    .where(CompanyIngredient.company_id == company_id)
                    .group_by(CompanyIngredient.id)
                    .order_by(CompanyIngredient.name)
                )
            ).all()
        )
        aliases = list(
            (
                await self.db.scalars(
                    select(CompanyIngredientAlias)
                    .options(
                        selectinload(CompanyIngredientAlias.ingredient),
                        selectinload(CompanyIngredientAlias.brand),
                        selectinload(CompanyIngredientAlias.source_product),
                    )
                    .where(CompanyIngredientAlias.company_id == company_id)
                    .order_by(CompanyIngredientAlias.created_at.desc())
                )
            ).all()
        )
        demands = list(
            (
                await self.db.scalars(
                    select(CompanyProductionDemand)
                    .options(
                        selectinload(CompanyProductionDemand.brand),
                        selectinload(CompanyProductionDemand.branch),
                        selectinload(CompanyProductionDemand.output_product),
                    )
                    .where(CompanyProductionDemand.company_id == company_id)
                    .order_by(
                        CompanyProductionDemand.needed_on,
                        CompanyProductionDemand.created_at.desc(),
                    )
                    .limit(100)
                )
            ).all()
        )
        orders = list(
            (
                await self.db.scalars(
                    select(CompanyProductionOrder)
                    .options(
                        selectinload(CompanyProductionOrder.brand),
                        selectinload(CompanyProductionOrder.output_product),
                        selectinload(CompanyProductionOrder.inputs).selectinload(
                            CompanyProductionInput.ingredient
                        ),
                    )
                    .where(CompanyProductionOrder.company_id == company_id)
                    .order_by(CompanyProductionOrder.created_at.desc())
                    .limit(100)
                )
            ).all()
        )
        branches = list(
            (
                await self.db.scalars(
                    select(Branch)
                    .where(
                        Branch.company_id == company_id,
                        Branch.deleted_at.is_(None),
                        Branch.is_active.is_(True),
                    )
                    .order_by(Branch.name)
                )
            ).all()
        )
        locations = list(
            (
                await self.db.scalars(
                    select(StockLocation)
                    .where(
                        StockLocation.company_id == company_id,
                        StockLocation.deleted_at.is_(None),
                        StockLocation.is_active.is_(True),
                    )
                    .order_by(StockLocation.name)
                )
            ).all()
        )
        brands = list(
            (
                await self.db.scalars(
                    select(Brand)
                    .where(Brand.company_id == company_id, Brand.is_active.is_(True))
                    .order_by(Brand.name)
                )
            ).all()
        )
        brand_branches = list(
            (
                await self.db.scalars(
                    select(BrandBranch)
                    .where(
                        BrandBranch.company_id == company_id,
                        BrandBranch.is_active.is_(True),
                    )
                    .order_by(BrandBranch.brand_id, BrandBranch.branch_id)
                )
            ).all()
        )
        products = list(
            (
                await self.db.scalars(
                    select(Product)
                    .options(selectinload(Product.unit))
                    .where(
                        Product.company_id == company_id,
                        Product.inventory_role.in_(["central_raw", "central_ready"]),
                        Product.deleted_at.is_(None),
                        Product.is_active.is_(True),
                    )
                    .order_by(Product.name)
                )
            ).all()
        )
        kitchen_data = None
        if kitchen is not None:
            branch = await self.db.get(Branch, kitchen.branch_id)
            location = await self.db.get(StockLocation, kitchen.raw_location_id)
            kitchen_data = {
                "id": kitchen.id,
                "name": kitchen.name,
                "branch_id": kitchen.branch_id,
                "branch_name": branch.name if branch else "",
                "raw_location_id": kitchen.raw_location_id,
                "raw_location_name": location.name if location else "",
                "timezone": kitchen.timezone,
                "costing_method": kitchen.costing_method,
                "allow_negative_stock": kitchen.allow_negative_stock,
                "is_active": kitchen.is_active,
            }
        return {
            "kitchen": kitchen_data,
            "ingredients": [
                self._ingredient_data(ingredient, Decimal(str(qty)))
                for ingredient, qty in ingredient_rows
            ],
            "aliases": [
                {
                    "id": alias.id,
                    "ingredient_id": alias.ingredient_id,
                    "ingredient_name": alias.ingredient.name,
                    "brand_id": alias.brand_id,
                    "brand_name": alias.brand.name,
                    "source_product_id": alias.source_product_id,
                    "source_product_name": alias.source_product.name,
                    "source_unit_code": alias.source_unit_code,
                    "conversion_factor": alias.conversion_factor,
                    "supplier_sku": alias.supplier_sku,
                }
                for alias in aliases
            ],
            "demands": [self._demand_data(row) for row in demands],
            "orders": [self._order_data(row) for row in orders],
            "setup_options": {
                "branches": [
                    {"id": row.id, "name": row.name, "code": row.code}
                    for row in branches
                ],
                "locations": [
                    {
                        "id": row.id,
                        "branch_id": row.branch_id,
                        "name": row.name,
                        "code": row.code,
                    }
                    for row in locations
                ],
                "brands": [
                    {"id": row.id, "name": row.name, "business_type": row.business_type}
                    for row in brands
                ],
                "brand_branches": [
                    {"brand_id": row.brand_id, "branch_id": row.branch_id}
                    for row in brand_branches
                ],
                "products": [
                    {
                        "id": row.id,
                        "name": row.name,
                        "sku": row.sku,
                        "brand_id": row.brand_id,
                        "inventory_role": row.inventory_role,
                        "unit_code": row.unit.code if row.unit else None,
                    }
                    for row in products
                ],
            },
        }

    async def report(
        self, company_id: uuid.UUID, date_from: date, date_to: date
    ) -> dict[str, Any]:
        if date_from > date_to:
            raise HTTPException(status_code=400, detail="วันที่เริ่มต้องไม่เกินวันที่สิ้นสุด")
        if (date_to - date_from).days > 92:
            raise HTTPException(status_code=400, detail="ช่วงรายงานต้องไม่เกิน 93 วัน")
        kitchen = await self.db.scalar(
            select(CompanyKitchen).where(CompanyKitchen.company_id == company_id)
        )
        timezone_name = kitchen.timezone if kitchen else "Asia/Bangkok"
        try:
            business_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status_code=409, detail="timezone ของครัวกลางไม่ถูกต้อง") from exc
        start = datetime.combine(date_from, time.min, business_timezone).astimezone(timezone.utc)
        end = datetime.combine(date_to, time.max, business_timezone).astimezone(timezone.utc)
        movements = list(
            (
                await self.db.scalars(
                    select(CompanyKitchenMovement)
                    .options(
                        selectinload(CompanyKitchenMovement.ingredient),
                        selectinload(CompanyKitchenMovement.brand),
                    )
                    .where(
                        CompanyKitchenMovement.company_id == company_id,
                        CompanyKitchenMovement.created_at >= start,
                        CompanyKitchenMovement.created_at <= end,
                    )
                    .order_by(CompanyKitchenMovement.created_at.desc())
                )
            ).all()
        )
        by_brand_ingredient: dict[tuple[str, str], dict[str, Any]] = {}
        for movement in movements:
            if movement.brand_id is None:
                continue
            key = (str(movement.brand_id), str(movement.ingredient_id))
            row = by_brand_ingredient.setdefault(
                key,
                {
                    "brand_id": movement.brand_id,
                    "brand_name": movement.brand.name if movement.brand else "",
                    "ingredient_id": movement.ingredient_id,
                    "ingredient_name": movement.ingredient.name,
                    "consumed_qty": Decimal("0"),
                    "reversed_qty": Decimal("0"),
                    "net_cost": Decimal("0"),
                    "unit_code": movement.ingredient.base_unit_code,
                },
            )
            if movement.movement_type == "production_issue":
                qty = abs(q4(movement.qty))
                row["consumed_qty"] += qty
                row["net_cost"] += qty * q4(movement.unit_cost)
            elif movement.movement_type == "production_reversal":
                qty = q4(movement.qty)
                row["reversed_qty"] += qty
                row["net_cost"] -= qty * q4(movement.unit_cost)
        orders = list(
            (
                await self.db.scalars(
                    select(CompanyProductionOrder)
                    .options(
                        selectinload(CompanyProductionOrder.brand),
                        selectinload(CompanyProductionOrder.output_product),
                        selectinload(CompanyProductionOrder.inputs).selectinload(
                            CompanyProductionInput.ingredient
                        ),
                    )
                    .where(
                        CompanyProductionOrder.company_id == company_id,
                        CompanyProductionOrder.planned_date >= date_from,
                        CompanyProductionOrder.planned_date <= date_to,
                    )
                    .order_by(CompanyProductionOrder.planned_date.desc())
                )
            ).all()
        )
        production_by_brand: dict[str, dict[str, Any]] = {}
        for order in orders:
            key = str(order.brand_id)
            row = production_by_brand.setdefault(
                key,
                {
                    "brand_id": order.brand_id,
                    "brand_name": order.brand.name,
                    "order_count": 0,
                    "completed_count": 0,
                    "output_qty": Decimal("0"),
                    "waste_qty": Decimal("0"),
                    "input_cost": Decimal("0"),
                },
            )
            row["order_count"] += 1
            if order.status in {"completed", "reversed"}:
                row["completed_count"] += 1
            if order.status == "completed":
                row["output_qty"] += q4(order.actual_output_qty)
                row["waste_qty"] += q4(order.waste_qty)
                row["input_cost"] += q4(order.total_input_cost)
        return {
            "date_from": date_from,
            "date_to": date_to,
            "production_by_brand": list(production_by_brand.values()),
            "ingredient_usage": list(by_brand_ingredient.values()),
            "orders": [self._order_data(row) for row in orders],
        }
