from __future__ import annotations

from decimal import Decimal
from datetime import date
import uuid

from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.business_context import RESTAURANT
from app.models.product import Product
from app.models.audit import AuditLog
from app.models.purchase import PurchaseOrder, PurchaseOrderItem
from app.models.restaurant import (
    Brand,
    BrandBranch,
    BranchReplenishmentPolicy,
    Recipe,
    RecipeIngredient,
)
from app.models.pos import SaleOrder, SaleOrderItem
from app.models.stock import StockBalance, StockLocation
from app.schemas.restaurant import (
    RecipeCreate,
    RecipeUpdate,
    RecipeIngredientRead,
    RecipeListItem,
    RecipeRead,
    IngredientUsageItem,
    IngredientUsageReport,
    RecipeInventoryUpdate,
)


UNIT_ALIASES = {
    "กรัม": "g",
    "gram": "g",
    "grams": "g",
    "ก": "g",
    "กก": "kg",
    "กิโล": "kg",
    "กิโลกรัม": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "มล": "ml",
    "มิลลิลิตร": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "ลิตร": "l",
    "liter": "l",
    "liters": "l",
    "ขีด": "heed",
}

UNIT_TO_BASE = {
    "g": ("weight", Decimal("1")),
    "kg": ("weight", Decimal("1000")),
    "heed": ("weight", Decimal("100")),
    "ml": ("volume", Decimal("1")),
    "l": ("volume", Decimal("1000")),
}


def _normalize_unit(unit: str | None) -> str:
    raw = (unit or "").strip().lower()
    return UNIT_ALIASES.get(raw, raw)


def convert_quantity(value: Decimal, from_unit: str | None, to_unit: str | None) -> Decimal:
    source = _normalize_unit(from_unit)
    target = _normalize_unit(to_unit)
    if not source or not target or source == target:
        return value
    source_base = UNIT_TO_BASE.get(source)
    target_base = UNIT_TO_BASE.get(target)
    if not source_base or not target_base or source_base[0] != target_base[0]:
        return value
    return (value * source_base[1] / target_base[1]).quantize(Decimal("0.0001"))


def _effective_yield(recipe: Recipe) -> Decimal:
    loss_rate = min(max(Decimal(str(recipe.loss_percent or 0)), Decimal("0")), Decimal("100"))
    effective = Decimal(str(recipe.yield_qty or 1)) * (Decimal("1") - (loss_rate / Decimal("100")))
    return effective.quantize(Decimal("0.0001")) if effective > 0 else Decimal("0.0001")


def resolve_recipe_inventory_role(
    recipe_type: str,
    *,
    is_output: bool,
    current_role: str | None,
    has_production_recipe: bool = False,
) -> str | None:
    if recipe_type not in {"production_recipe", "menu_recipe"}:
        raise ValueError("ประเภทสูตรไม่ถูกต้อง")
    if is_output and recipe_type == "menu_recipe":
        return None

    if is_output:
        if current_role not in {None, "central_ready"}:
            raise ValueError("สินค้าที่ได้จากสูตรผลิตต้องใช้ inventory role เป็น CENTRAL-READY")
        return "central_ready"

    if recipe_type == "production_recipe":
        if current_role is None:
            return "central_ready" if has_production_recipe else "central_raw"
        if current_role not in {"central_raw", "central_ready"}:
            raise ValueError("วัตถุดิบสูตรผลิตต้องอยู่ใน CENTRAL-RAW หรือ CENTRAL-READY")
        return current_role

    if current_role is None:
        return "central_ready"
    if current_role not in {"central_ready", "store_local"}:
        raise ValueError("วัตถุดิบสูตรหน้าร้านต้องอยู่ใน CENTRAL-READY หรือ STORE-STOCK")
    return current_role


class RecipeService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _latest_unit_cost(self, company_id: uuid.UUID, ingredient_id: uuid.UUID) -> Decimal:
        """ดึงราคาต่อหน่วยล่าสุดจาก PurchaseOrderItem"""
        row = await self.db.scalar(
            select(PurchaseOrderItem.unit_cost)
            .join(PurchaseOrder, PurchaseOrderItem.po_id == PurchaseOrder.id)
            .where(
                PurchaseOrderItem.company_id == company_id,
                PurchaseOrderItem.product_id == ingredient_id,
                PurchaseOrder.status == "received",
            )
            .order_by(desc(PurchaseOrder.created_at))
            .limit(1)
        )
        if row is not None:
            return Decimal(str(row))
        # fallback: ดึงจาก cost_price ของ Product
        cost = await self.db.scalar(
            select(Product.cost_price).where(Product.id == ingredient_id)
        )
        return Decimal(str(cost or 0))

    async def _enrich_recipe(
        self,
        recipe: Recipe,
        company_id: uuid.UUID,
        inventory_updates: list[RecipeInventoryUpdate] | None = None,
    ) -> RecipeRead:
        product = recipe.product
        total_cost = Decimal("0")
        ingredients_out: list[RecipeIngredientRead] = []

        for ing in recipe.ingredients:
            unit_cost = await self._latest_unit_cost(company_id, ing.ingredient_id)
            product_unit = ing.ingredient.unit.code if ing.ingredient and ing.ingredient.unit else ing.unit
            cost_qty = convert_quantity(Decimal(str(ing.quantity)), ing.unit, product_unit)
            cost_line = (cost_qty * unit_cost).quantize(Decimal("0.0001"))
            total_cost += cost_line
            ingredients_out.append(
                RecipeIngredientRead(
                    id=ing.id,
                    recipe_id=ing.recipe_id,
                    ingredient_id=ing.ingredient_id,
                    ingredient_name=ing.ingredient.name if ing.ingredient else "",
                    ingredient_sku=ing.ingredient.sku if ing.ingredient else "",
                    image_url=ing.ingredient.image_url if ing.ingredient else None,
                    quantity=ing.quantity,
                    unit=ing.unit,
                    sort_order=ing.sort_order,
                    notes=ing.notes,
                    latest_unit_cost=unit_cost,
                    cost_per_recipe=cost_line,
                )
            )

        effective_yield_qty = _effective_yield(recipe)
        cost_per_yield = (total_cost / effective_yield_qty).quantize(Decimal("0.01")) if effective_yield_qty else total_cost
        selling_price = Decimal(str(product.selling_price)) if product else Decimal("0")
        margin = (
            ((selling_price - cost_per_yield) / selling_price * 100).quantize(Decimal("0.01"))
            if selling_price > 0
            else Decimal("0")
        )

        return RecipeRead(
            id=recipe.id,
            company_id=recipe.company_id,
            branch_id=recipe.branch_id,
            brand_id=recipe.brand_id,
            product_id=recipe.product_id,
            product_name=product.name if product else "",
            product_sku=product.sku if product else "",
            recipe_type=recipe.recipe_type,
            version_no=recipe.version_no,
            effective_from=recipe.effective_from,
            effective_to=recipe.effective_to,
            name=recipe.name,
            yield_qty=recipe.yield_qty,
            yield_unit=recipe.yield_unit,
            loss_percent=recipe.loss_percent,
            effective_yield_qty=effective_yield_qty,
            notes=recipe.notes,
            is_active=recipe.is_active,
            ingredients=ingredients_out,
            total_cost=total_cost.quantize(Decimal("0.01")),
            cost_per_yield=cost_per_yield,
            selling_price=selling_price,
            gross_margin_pct=margin,
            inventory_updates=inventory_updates or [],
        )

    async def list_recipes(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None = None,
        brand_id: uuid.UUID | None = None,
        include_inactive: bool = False,
    ) -> list[RecipeListItem]:
        q = (
            select(Recipe)
            .options(
                selectinload(Recipe.product),
                selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient).selectinload(Product.unit),
            )
            .where(Recipe.company_id == company_id)
        )
        if branch_id:
            q = q.where(
                (Recipe.branch_id == branch_id) | (Recipe.branch_id.is_(None))
            )
        if brand_id:
            q = q.where(Recipe.brand_id == brand_id)
        else:
            q = q.where(Recipe.brand_id.is_(None))
        if not include_inactive:
            q = q.where(Recipe.is_active.is_(True))

        rows = (await self.db.scalars(q)).all()
        result: list[RecipeListItem] = []
        for recipe in rows:
            enriched = await self._enrich_recipe(recipe, company_id)
            result.append(
                RecipeListItem(
                    id=enriched.id,
                    product_id=enriched.product_id,
                    brand_id=enriched.brand_id,
                    product_name=enriched.product_name,
                    name=enriched.name,
                    recipe_type=enriched.recipe_type,
                    version_no=enriched.version_no,
                    yield_unit=enriched.yield_unit,
                    is_active=enriched.is_active,
                    total_cost=enriched.total_cost,
                    cost_per_yield=enriched.cost_per_yield,
                    selling_price=enriched.selling_price,
                    gross_margin_pct=enriched.gross_margin_pct,
                )
            )
        return result

    async def get_recipe(self, recipe_id: uuid.UUID, company_id: uuid.UUID) -> Recipe | None:
        return await self.db.scalar(
            select(Recipe)
            .options(
                selectinload(Recipe.product),
                selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient).selectinload(Product.unit),
            )
            .where(Recipe.id == recipe_id, Recipe.company_id == company_id)
        )

    async def get_recipe_by_product(
        self,
        product_id: uuid.UUID,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None = None,
        recipe_type: str = "menu_recipe",
        brand_id: uuid.UUID | None = None,
    ) -> Recipe | None:
        """ดึงสูตรที่ match branch ก่อน ถ้าไม่มีใช้สูตร global"""
        ingredient_options = selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient).selectinload(Product.unit)
        brand_filters = [Recipe.brand_id == brand_id] if brand_id is not None else []
        if branch_id:
            branch_recipe = await self.db.scalar(
                select(Recipe)
                .options(ingredient_options)
                .where(
                    Recipe.product_id == product_id,
                    Recipe.company_id == company_id,
                    *brand_filters,
                    Recipe.branch_id == branch_id,
                    Recipe.recipe_type == recipe_type,
                    Recipe.is_active.is_(True),
                )
                .order_by(Recipe.version_no.desc(), Recipe.effective_from.desc().nullslast(), Recipe.created_at.desc())
                .limit(1)
            )
            if branch_recipe:
                return branch_recipe
        return await self.db.scalar(
            select(Recipe)
            .options(ingredient_options)
            .where(
                Recipe.product_id == product_id,
                Recipe.company_id == company_id,
                *brand_filters,
                Recipe.branch_id.is_(None),
                Recipe.recipe_type == recipe_type,
                Recipe.is_active.is_(True),
            )
            .order_by(Recipe.version_no.desc(), Recipe.effective_from.desc().nullslast(), Recipe.created_at.desc())
            .limit(1)
        )

    async def _latest_production_recipe(
        self,
        company_id: uuid.UUID,
        product_id: uuid.UUID,
        branch_id: uuid.UUID | None,
        brand_id: uuid.UUID | None,
        exclude_recipe_id: uuid.UUID | None = None,
    ) -> Recipe | None:
        conditions = [
            Recipe.product_id == product_id,
            Recipe.company_id == company_id,
            Recipe.recipe_type == "production_recipe",
            Recipe.is_active.is_(True),
        ]
        if branch_id:
            conditions.append((Recipe.branch_id == branch_id) | (Recipe.branch_id.is_(None)))
        else:
            conditions.append(Recipe.branch_id.is_(None))
        if brand_id:
            conditions.append(Recipe.brand_id == brand_id)
        else:
            conditions.append(Recipe.brand_id.is_(None))
        if exclude_recipe_id:
            conditions.append(Recipe.id != exclude_recipe_id)
        return await self.db.scalar(
            select(Recipe)
            .options(selectinload(Recipe.ingredients))
            .where(*conditions)
            .order_by(Recipe.version_no.desc(), Recipe.effective_from.desc().nullslast(), Recipe.created_at.desc())
            .limit(1)
        )

    async def _validate_no_recipe_cycle(
        self,
        company_id: uuid.UUID,
        recipe_product_id: uuid.UUID,
        ingredient_ids: list[uuid.UUID],
        branch_id: uuid.UUID | None = None,
        brand_id: uuid.UUID | None = None,
        exclude_recipe_id: uuid.UUID | None = None,
    ) -> None:
        if recipe_product_id in ingredient_ids:
            raise ValueError("สูตรวน loop: ห้ามใช้สินค้าที่ผูกสูตรเป็นวัตถุดิบของตัวเอง")

        visited: set[uuid.UUID] = set()

        async def walk(product_id: uuid.UUID, path: set[uuid.UUID]) -> bool:
            if product_id == recipe_product_id:
                return True
            if product_id in path or product_id in visited:
                return False
            path.add(product_id)
            visited.add(product_id)
            nested = await self._latest_production_recipe(
                company_id,
                product_id,
                branch_id,
                brand_id,
                exclude_recipe_id,
            )
            try:
                if not nested:
                    return False
                for nested_ing in nested.ingredients:
                    if await walk(nested_ing.ingredient_id, path):
                        return True
                return False
            finally:
                path.remove(product_id)

        for ingredient_id in ingredient_ids:
            if await walk(ingredient_id, set()):
                raise ValueError("สูตรวน loop: สูตรผลิตซ้อนกันย้อนกลับมาหาสินค้าเดิม")

    async def ensure_recipe_inventory_items(
        self,
        recipe: Recipe,
        company_id: uuid.UUID,
        ingredient_ids: list[uuid.UUID],
        actor_id: uuid.UUID | None = None,
    ) -> list[RecipeInventoryUpdate]:
        if recipe.brand_id is None or not recipe.is_active:
            return []

        brand = await self.db.scalar(
            select(Brand)
            .where(
                Brand.id == recipe.brand_id,
                Brand.company_id == company_id,
                Brand.business_type == RESTAURANT,
                Brand.is_active.is_(True),
            )
            .with_for_update()
        )
        if brand is None:
            raise ValueError("ไม่พบแบรนด์สำหรับสูตรนี้")

        unique_ingredient_ids = list(dict.fromkeys(ingredient_ids))
        product_ids = list(unique_ingredient_ids)
        product_ids.append(recipe.product_id)
        product_ids = list(dict.fromkeys(product_ids))

        products = list(
            (
                await self.db.scalars(
                    select(Product)
                    .where(
                        Product.id.in_(product_ids),
                        Product.company_id == company_id,
                        Product.deleted_at.is_(None),
                        Product.is_active.is_(True),
                    )
                    .with_for_update()
                )
            ).all()
        )
        products_by_id = {product.id: product for product in products}
        missing_ids = [product_id for product_id in product_ids if product_id not in products_by_id]
        if missing_ids:
            raise ValueError("พบสินค้าหรือวัตถุดิบที่ไม่อยู่ในบริษัท หรือถูกปิดใช้งาน")
        for product in products:
            if product.brand_id not in {None, brand.id}:
                raise ValueError(f"สินค้า {product.name} เป็นของแบรนด์อื่น")

        production_output_ids = set(
            (
                await self.db.scalars(
                    select(Recipe.product_id).where(
                        Recipe.company_id == company_id,
                        Recipe.brand_id == brand.id,
                        Recipe.recipe_type == "production_recipe",
                        Recipe.is_active.is_(True),
                        Recipe.product_id.in_(unique_ingredient_ids),
                        Recipe.id != recipe.id,
                    )
                )
            ).all()
        )

        location_cache: dict[uuid.UUID, StockLocation] = {}

        async def load_location(
            location_id: uuid.UUID | None,
            label: str,
            expected_branch_id: uuid.UUID | None = None,
        ) -> StockLocation:
            if location_id is None:
                raise ValueError(f"กรุณาตั้งค่า{label}ก่อนบันทึกสูตร")
            cached = location_cache.get(location_id)
            if cached is not None:
                if expected_branch_id is not None and cached.branch_id != expected_branch_id:
                    raise ValueError(f"{label}ไม่อยู่ในสาขาครัวกลาง")
                return cached
            location = await self.db.scalar(
                select(StockLocation).where(
                    StockLocation.id == location_id,
                    StockLocation.company_id == company_id,
                    StockLocation.deleted_at.is_(None),
                    StockLocation.is_active.is_(True),
                )
            )
            if location is None:
                raise ValueError(f"ไม่พบ{label}ที่เปิดใช้งาน")
            if expected_branch_id is not None and location.branch_id != expected_branch_id:
                raise ValueError(f"{label}ไม่อยู่ในสาขาครัวกลาง")
            location_cache[location.id] = location
            return location

        async def locations_for_role(role: str) -> list[StockLocation]:
            if role == "central_raw":
                if brand.central_branch_id is None:
                    raise ValueError("กรุณาตั้งค่าสาขาครัวกลางก่อนบันทึกสูตร")
                return [
                    await load_location(
                        brand.central_location_id,
                        "คลังวัตถุดิบ RAW",
                        brand.central_branch_id,
                    )
                ]
            if role == "central_ready":
                if brand.central_branch_id is None:
                    raise ValueError("กรุณาตั้งค่าสาขาครัวกลางก่อนบันทึกสูตร")
                return [
                    await load_location(
                        brand.central_ready_location_id,
                        "คลังพร้อมส่ง READY",
                        brand.central_branch_id,
                    )
                ]
            if role == "store_local":
                store_location_ids = list(
                    (
                        await self.db.scalars(
                            select(BrandBranch.store_location_id).where(
                                BrandBranch.company_id == company_id,
                                BrandBranch.brand_id == brand.id,
                                BrandBranch.is_active.is_(True),
                                BrandBranch.store_location_id.is_not(None),
                            )
                        )
                    ).all()
                )
                if not store_location_ids:
                    raise ValueError("ยังไม่ได้ตั้งค่าคลังหน้าร้านสำหรับวัตถุดิบ STORE-STOCK")
                return [
                    await load_location(location_id, "คลังหน้าร้าน")
                    for location_id in dict.fromkeys(store_location_ids)
                ]
            raise ValueError("inventory role ของวัตถุดิบไม่ถูกต้อง")

        if (
            brand.central_location_id is not None
            and brand.central_location_id == brand.central_ready_location_id
        ):
            raise ValueError("คลังวัตถุดิบ RAW และคลังพร้อมส่ง READY ต้องเป็นคนละคลัง")

        targets: list[tuple[Product, bool]] = [
            (products_by_id[ingredient_id], False)
            for ingredient_id in unique_ingredient_ids
        ]
        if recipe.recipe_type == "production_recipe":
            targets.append((products_by_id[recipe.product_id], True))

        updates: list[RecipeInventoryUpdate] = []
        replenishment_branches: list[BrandBranch] | None = None
        for product, is_output in targets:
            desired_role = resolve_recipe_inventory_role(
                recipe.recipe_type,
                is_output=is_output,
                current_role=product.inventory_role,
                has_production_recipe=product.id in production_output_ids,
            )
            if desired_role is None:
                continue
            role_assigned = product.inventory_role is None
            if role_assigned:
                product.inventory_role = desired_role

            locations = await locations_for_role(desired_role)
            for location in locations:
                balance = await self.db.scalar(
                    select(StockBalance).where(
                        StockBalance.company_id == company_id,
                        StockBalance.branch_id == location.branch_id,
                        StockBalance.location_id == location.id,
                        StockBalance.product_id == product.id,
                        StockBalance.variant_id.is_(None),
                    )
                )
                balance_created = balance is None
                if balance_created:
                    self.db.add(
                        StockBalance(
                            company_id=company_id,
                            branch_id=location.branch_id,
                            location_id=location.id,
                            product_id=product.id,
                            variant_id=None,
                            qty_on_hand=Decimal("0"),
                            qty_reserved=Decimal("0"),
                            cost_per_unit=Decimal(str(product.cost_price or 0)),
                        )
                    )
                if role_assigned or balance_created:
                    updates.append(
                        RecipeInventoryUpdate(
                            product_id=product.id,
                            product_name=product.name,
                            inventory_role=desired_role,  # type: ignore[arg-type]
                            location_id=location.id,
                            location_name=location.name,
                            role_assigned=role_assigned,
                            balance_created=balance_created,
                        )
                    )

            if desired_role == "central_ready" and recipe.recipe_type == "menu_recipe" and not is_output:
                if replenishment_branches is None:
                    replenishment_branches = list(
                        (
                            await self.db.scalars(
                                select(BrandBranch).where(
                                    BrandBranch.company_id == company_id,
                                    BrandBranch.brand_id == brand.id,
                                    BrandBranch.is_active.is_(True),
                                )
                            )
                        ).all()
                    )
                for brand_branch in replenishment_branches:
                    existing_policy = await self.db.scalar(
                        select(BranchReplenishmentPolicy.id).where(
                            BranchReplenishmentPolicy.brand_id == brand.id,
                            BranchReplenishmentPolicy.branch_id == brand_branch.branch_id,
                            BranchReplenishmentPolicy.product_id == product.id,
                        )
                    )
                    if existing_policy is None:
                        self.db.add(
                            BranchReplenishmentPolicy(
                                company_id=company_id,
                                brand_id=brand.id,
                                branch_id=brand_branch.branch_id,
                                product_id=product.id,
                            )
                        )

        if updates:
            self.db.add(
                AuditLog(
                    company_id=company_id,
                    branch_id=brand.central_branch_id,
                    user_id=actor_id,
                    action="recipe.inventory_provisioned",
                    resource="Recipe",
                    resource_id=str(recipe.id),
                    new_value={
                        "brand_id": str(brand.id),
                        "items": [item.model_dump(mode="json") for item in updates],
                    },
                )
            )
        await self.db.flush()
        return updates

    async def create_recipe(
        self,
        company_id: uuid.UUID,
        payload: RecipeCreate,
        actor_id: uuid.UUID | None = None,
    ) -> tuple[Recipe, list[RecipeInventoryUpdate]]:
        await self._validate_no_recipe_cycle(
            company_id,
            payload.product_id,
            [ing.ingredient_id for ing in payload.ingredients],
            payload.branch_id,
            payload.brand_id,
        )
        if payload.selling_price is not None:
            product = await self.db.scalar(
                select(Product).where(Product.id == payload.product_id, Product.company_id == company_id)
            )
            if product is not None:
                product.selling_price = payload.selling_price

        recipe = Recipe(
            company_id=company_id,
            branch_id=payload.branch_id,
            brand_id=payload.brand_id,
            product_id=payload.product_id,
            recipe_type=payload.recipe_type,
            version_no=payload.version_no,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            name=payload.name,
            yield_qty=payload.yield_qty,
            yield_unit=payload.yield_unit,
            loss_percent=payload.loss_percent,
            notes=payload.notes,
        )
        self.db.add(recipe)
        await self.db.flush()

        for idx, ing_data in enumerate(payload.ingredients):
            ing = RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_id=ing_data.ingredient_id,
                quantity=ing_data.quantity,
                unit=ing_data.unit,
                sort_order=ing_data.sort_order if ing_data.sort_order else idx,
                notes=ing_data.notes,
            )
            self.db.add(ing)

        inventory_updates = await self.ensure_recipe_inventory_items(
            recipe,
            company_id,
            [ingredient.ingredient_id for ingredient in payload.ingredients],
            actor_id,
        )
        await self.db.commit()
        await self.db.refresh(recipe)
        saved = await self.get_recipe(recipe.id, company_id)
        return saved, inventory_updates  # type: ignore[return-value]

    async def update_recipe(
        self,
        recipe: Recipe,
        company_id: uuid.UUID,
        payload: RecipeUpdate,
        actor_id: uuid.UUID | None = None,
    ) -> tuple[Recipe, list[RecipeInventoryUpdate]]:
        if payload.name is not None:
            recipe.name = payload.name
        if payload.selling_price is not None and recipe.product is not None:
            recipe.product.selling_price = payload.selling_price
        if payload.recipe_type is not None:
            recipe.recipe_type = payload.recipe_type
        if payload.version_no is not None:
            recipe.version_no = payload.version_no
        if "effective_from" in payload.model_fields_set:
            recipe.effective_from = payload.effective_from
        if "effective_to" in payload.model_fields_set:
            recipe.effective_to = payload.effective_to
        if payload.yield_qty is not None:
            recipe.yield_qty = payload.yield_qty
        if payload.yield_unit is not None:
            recipe.yield_unit = payload.yield_unit
        if payload.loss_percent is not None:
            recipe.loss_percent = payload.loss_percent
        if "notes" in payload.model_fields_set:
            recipe.notes = payload.notes
        if payload.is_active is not None:
            recipe.is_active = payload.is_active

        if payload.ingredients is not None:
            await self._validate_no_recipe_cycle(
                company_id,
                recipe.product_id,
                [ing.ingredient_id for ing in payload.ingredients],
                recipe.branch_id,
                recipe.brand_id,
                recipe.id,
            )
            # replace all ingredients
            for ing in recipe.ingredients:
                await self.db.delete(ing)
            await self.db.flush()
            for idx, ing_data in enumerate(payload.ingredients):
                ing = RecipeIngredient(
                    recipe_id=recipe.id,
                    ingredient_id=ing_data.ingredient_id,
                    quantity=ing_data.quantity,
                    unit=ing_data.unit,
                    sort_order=ing_data.sort_order if ing_data.sort_order else idx,
                    notes=ing_data.notes,
                )
                self.db.add(ing)

        ingredient_ids = (
            [ingredient.ingredient_id for ingredient in payload.ingredients]
            if payload.ingredients is not None
            else [ingredient.ingredient_id for ingredient in recipe.ingredients]
        )
        inventory_updates = await self.ensure_recipe_inventory_items(
            recipe,
            company_id,
            ingredient_ids,
            actor_id,
        )
        await self.db.commit()
        saved = await self.get_recipe(recipe.id, company_id)
        return saved, inventory_updates  # type: ignore[return-value]

    async def delete_recipe(self, recipe: Recipe) -> None:
        await self.db.delete(recipe)
        await self.db.commit()

    async def get_ingredient_usage_report(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: date,
        date_to: date,
    ) -> IngredientUsageReport:
        """คำนวณการใช้วัตถุดิบจาก SaleOrderItems × Recipe ingredients"""
        sales_q = (
            select(SaleOrderItem.product_id, func.sum(SaleOrderItem.qty).label("total_qty"))
            .join(SaleOrder, SaleOrderItem.order_id == SaleOrder.id)
            .where(
                SaleOrder.company_id == company_id,
                SaleOrder.branch_id == branch_id,
                SaleOrder.status.in_(["completed", "partially_refunded"]),
                func.date(SaleOrder.created_at) >= date_from,
                func.date(SaleOrder.created_at) <= date_to,
            )
            .group_by(SaleOrderItem.product_id)
        )
        sold_rows = (await self.db.execute(sales_q)).all()

        # ingredient_id → {qty, unit, name, sku}
        usage: dict[uuid.UUID, dict] = {}

        for product_id, total_qty in sold_rows:
            recipe = await self.get_recipe_by_product(product_id, company_id, branch_id)
            if not recipe:
                continue
            sold = Decimal(str(total_qty)) / _effective_yield(recipe)
            for ing in recipe.ingredients:
                theoretical = (ing.quantity * sold).quantize(Decimal("0.0001"))
                product_unit = ing.ingredient.unit.code if ing.ingredient and ing.ingredient.unit else ing.unit
                theoretical = convert_quantity(theoretical, ing.unit, product_unit)
                if ing.ingredient_id not in usage:
                    usage[ing.ingredient_id] = {
                        "name": ing.ingredient.name if ing.ingredient else "",
                        "sku": ing.ingredient.sku if ing.ingredient else "",
                        "unit": product_unit,
                        "qty": Decimal("0"),
                    }
                usage[ing.ingredient_id]["qty"] += theoretical

        items: list[IngredientUsageItem] = []
        grand_total = Decimal("0")
        for ingredient_id, data in usage.items():
            unit_cost = await self._latest_unit_cost(company_id, ingredient_id)
            total_cost = (data["qty"] * unit_cost).quantize(Decimal("0.01"))
            grand_total += total_cost
            items.append(
                IngredientUsageItem(
                    ingredient_id=ingredient_id,
                    ingredient_name=data["name"],
                    ingredient_sku=data["sku"],
                    theoretical_qty=data["qty"].quantize(Decimal("0.0001")),
                    unit=data["unit"],
                    latest_unit_cost=unit_cost,
                    total_cost=total_cost,
                )
            )

        items.sort(key=lambda x: x.total_cost, reverse=True)
        return IngredientUsageReport(
            branch_id=branch_id,
            date_from=str(date_from),
            date_to=str(date_to),
            items=items,
            grand_total_cost=grand_total.quantize(Decimal("0.01")),
        )
