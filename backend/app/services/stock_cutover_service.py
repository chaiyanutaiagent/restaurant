from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.product import Product
from app.models.restaurant import (
    Brand,
    BrandBranch,
    CentralOrder,
    ProductionBatch,
    Recipe,
    RecipeIngredient,
    StockCutoverItem,
    StockCutoverRun,
)
from app.models.stock import StockBalance, StockLocation
from app.models.transfer import TransferOrder, TransferOrderItem
from app.services.stock_service import StockService


FOURPLACES = Decimal("0.0001")
ACTIVE_CENTRAL_ORDER_STATUSES = {"submitted", "reserved_credit", "approved", "packed"}
ACTIVE_TRANSFER_STATUSES = {"approved", "in_transit", "partially_received"}


def q4(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(FOURPLACES, rounding=ROUND_HALF_UP)


def make_preview_token(snapshot: dict) -> str:
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _issue(code: str, message: str, **details) -> dict:
    return {"code": code, "message": message, "details": details}


class StockCutoverService:
    """Preview and execute the one-time audited RAW → READY stock cutover."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.stock_service = StockService(db)

    async def preview(
        self,
        *,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        lock: bool = False,
    ) -> dict:
        brand_statement = select(Brand).where(
            Brand.id == brand_id,
            Brand.company_id == company_id,
            Brand.is_active.is_(True),
        )
        if lock:
            brand_statement = brand_statement.with_for_update()
        brand = await self.db.scalar(brand_statement)
        if brand is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบแบรนด์")

        blockers: list[dict] = []
        warnings: list[dict] = []
        central_location_ids = [
            location_id
            for location_id in [brand.central_location_id, brand.central_ready_location_id]
            if location_id is not None
        ]
        locations = list(
            (
                await self.db.scalars(
                    select(StockLocation).where(
                        StockLocation.id.in_(central_location_ids),
                        StockLocation.company_id == company_id,
                        StockLocation.deleted_at.is_(None),
                    )
                )
            ).all()
        ) if central_location_ids else []
        locations_by_id = {location.id: location for location in locations}
        raw_location = locations_by_id.get(brand.central_location_id)
        ready_location = locations_by_id.get(brand.central_ready_location_id)

        if brand.central_branch_id is None:
            blockers.append(_issue("missing_central_branch", "ยังไม่ได้ตั้งสาขาครัวกลาง"))
        if raw_location is None:
            blockers.append(_issue("missing_raw_location", "ยังไม่ได้ตั้งคลัง CENTRAL-RAW ที่เปิดใช้งาน"))
        if ready_location is None:
            blockers.append(_issue("missing_ready_location", "ยังไม่ได้ตั้งคลัง CENTRAL-READY ที่เปิดใช้งาน"))
        if raw_location is not None and ready_location is not None and raw_location.id == ready_location.id:
            blockers.append(_issue("same_central_locations", "คลัง RAW และ READY ต้องเป็นคนละคลัง"))
        for label, location in (("RAW", raw_location), ("READY", ready_location)):
            if location is not None and brand.central_branch_id is not None and location.branch_id != brand.central_branch_id:
                blockers.append(
                    _issue(
                        "central_location_wrong_branch",
                        f"คลัง {label} ไม่อยู่ในสาขาครัวกลาง",
                        location_id=str(location.id),
                        branch_id=str(location.branch_id),
                    )
                )

        mapping_rows = list(
            (
                await self.db.execute(
                    select(BrandBranch, Branch, StockLocation)
                    .join(Branch, BrandBranch.branch_id == Branch.id)
                    .outerjoin(StockLocation, BrandBranch.store_location_id == StockLocation.id)
                    .where(
                        BrandBranch.company_id == company_id,
                        BrandBranch.brand_id == brand.id,
                        BrandBranch.is_active.is_(True),
                        Branch.deleted_at.is_(None),
                        Branch.is_active.is_(True),
                    )
                    .order_by(Branch.name.asc())
                )
            ).all()
        )
        store_locations: list[dict] = []
        store_location_ids: list[uuid.UUID] = []
        for mapping, branch, location in mapping_rows:
            item = {
                "branch_id": str(branch.id),
                "branch_code": branch.code,
                "branch_name": branch.name,
                "branch_type": mapping.branch_type,
                "store_location_id": str(location.id) if location else None,
                "store_location_code": location.code if location else None,
                "store_location_name": location.name if location else None,
                "is_valid": bool(
                    location
                    and location.company_id == company_id
                    and location.branch_id == branch.id
                    and location.is_active
                    and location.deleted_at is None
                    and location.id not in {brand.central_location_id, brand.central_ready_location_id}
                ),
            }
            store_locations.append(item)
            if location is None:
                blockers.append(
                    _issue(
                        "missing_store_location",
                        f"สาขา {branch.name} ยังไม่ได้ตั้ง STORE-STOCK",
                        branch_id=str(branch.id),
                    )
                )
            elif location.branch_id != branch.id or location.company_id != company_id:
                blockers.append(
                    _issue(
                        "store_location_wrong_branch",
                        f"STORE-STOCK ของ {branch.name} อยู่ผิดสาขา",
                        branch_id=str(branch.id),
                        location_id=str(location.id),
                    )
                )
            elif not location.is_active or location.deleted_at is not None:
                blockers.append(
                    _issue(
                        "inactive_store_location",
                        f"STORE-STOCK ของ {branch.name} ถูกปิดใช้งาน",
                        branch_id=str(branch.id),
                        location_id=str(location.id),
                    )
                )
            elif location.id in {brand.central_location_id, brand.central_ready_location_id}:
                blockers.append(
                    _issue(
                        "store_location_is_central",
                        f"STORE-STOCK ของ {branch.name} ต้องแยกจากคลังกลาง",
                        branch_id=str(branch.id),
                        location_id=str(location.id),
                    )
                )
            else:
                store_location_ids.append(location.id)

        recipe_products = list(
            (
                await self.db.execute(
                    select(Recipe.product_id, Recipe.recipe_type).where(
                        Recipe.company_id == company_id,
                        Recipe.brand_id == brand.id,
                        Recipe.is_active.is_(True),
                    )
                )
            ).all()
        )
        recipe_ingredients = list(
            (
                await self.db.execute(
                    select(RecipeIngredient.ingredient_id, Recipe.recipe_type)
                    .join(Recipe, RecipeIngredient.recipe_id == Recipe.id)
                    .where(
                        Recipe.company_id == company_id,
                        Recipe.brand_id == brand.id,
                        Recipe.is_active.is_(True),
                    )
                )
            ).all()
        )
        production_output_ids = {
            product_id for product_id, recipe_type in recipe_products if recipe_type == "production_recipe"
        }
        menu_ingredient_ids = {
            product_id for product_id, recipe_type in recipe_ingredients if recipe_type == "menu_recipe"
        }
        production_ingredient_ids = {
            product_id for product_id, recipe_type in recipe_ingredients if recipe_type == "production_recipe"
        }
        brand_product_ids = set(
            (
                await self.db.scalars(
                    select(Product.id).where(
                        Product.company_id == company_id,
                        Product.brand_id == brand.id,
                        Product.deleted_at.is_(None),
                    )
                )
            ).all()
        )
        relevant_product_ids = (
            brand_product_ids
            | production_output_ids
            | menu_ingredient_ids
            | production_ingredient_ids
        )
        audit_location_ids = list(dict.fromkeys(central_location_ids + store_location_ids))
        if central_location_ids:
            relevant_product_ids |= set(
                (
                    await self.db.scalars(
                        select(StockBalance.product_id).where(
                            StockBalance.company_id == company_id,
                            StockBalance.location_id.in_(central_location_ids),
                        )
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
                        Product.id.in_(relevant_product_ids),
                    )
                    .order_by(Product.name.asc())
                )
            ).all()
        ) if relevant_product_ids else []
        products_by_id = {product.id: product for product in products}

        balance_statement = (
            select(StockBalance)
            .options(
                selectinload(StockBalance.product).selectinload(Product.unit),
                selectinload(StockBalance.location),
            )
            .where(
                StockBalance.company_id == company_id,
                StockBalance.product_id.in_(relevant_product_ids),
                StockBalance.location_id.in_(audit_location_ids),
            )
            .order_by(StockBalance.location_id.asc(), StockBalance.product_id.asc())
        ) if relevant_product_ids and audit_location_ids else None
        if balance_statement is not None and lock:
            balance_statement = balance_statement.with_for_update()
        balances = list((await self.db.scalars(balance_statement)).all()) if balance_statement is not None else []
        balance_by_key = {
            (balance.location_id, balance.product_id, balance.variant_id): balance
            for balance in balances
        }

        for product_id in production_output_ids:
            product = products_by_id.get(product_id)
            if product is not None and product.inventory_role != "central_ready":
                blockers.append(
                    _issue(
                        "production_output_role_invalid",
                        f"ผลผลิต {product.name} ต้องเป็น CENTRAL-READY",
                        product_id=str(product.id),
                        inventory_role=product.inventory_role,
                    )
                )
        for product_id in production_ingredient_ids:
            product = products_by_id.get(product_id)
            if product is not None and product.inventory_role not in {"central_raw", "central_ready"}:
                blockers.append(
                    _issue(
                        "production_ingredient_role_invalid",
                        f"วัตถุดิบผลิต {product.name} ยังไม่มี role ที่ชัดเจน",
                        product_id=str(product.id),
                        inventory_role=product.inventory_role,
                    )
                )
        for product_id in menu_ingredient_ids:
            product = products_by_id.get(product_id)
            if product is not None and product.inventory_role not in {"central_ready", "store_local"}:
                blockers.append(
                    _issue(
                        "menu_ingredient_role_invalid",
                        f"วัตถุดิบหน้าร้าน {product.name} ต้องเป็น READY หรือ STORE-STOCK",
                        product_id=str(product.id),
                        inventory_role=product.inventory_role,
                    )
                )

        for balance in balances:
            product = balance.product
            location = balance.location
            qty_on_hand = q4(balance.qty_on_hand)
            if location is not None and balance.branch_id != location.branch_id:
                blockers.append(
                    _issue(
                        "balance_branch_mismatch",
                        f"Balance ของ {product.name} มี branch ไม่ตรง location",
                        balance_id=str(balance.id),
                        product_id=str(product.id),
                        location_id=str(balance.location_id),
                    )
                )
            if qty_on_hand == 0:
                continue
            if balance.location_id in central_location_ids and product.inventory_role is None:
                blockers.append(
                    _issue(
                        "central_balance_unclassified",
                        f"{product.name} มียอดกลางแต่ยังไม่มี inventory role",
                        product_id=str(product.id),
                        location_id=str(balance.location_id),
                        qty=float(qty_on_hand),
                    )
                )
            if balance.location_id in central_location_ids and product.deleted_at is not None:
                blockers.append(
                    _issue(
                        "deleted_product_has_central_balance",
                        f"{product.name} ถูกลบแล้วแต่ยังมียอดในคลังกลาง",
                        product_id=str(product.id),
                        location_id=str(balance.location_id),
                        qty=float(qty_on_hand),
                    )
                )
            recipe_related = product.id in (
                production_output_ids | production_ingredient_ids | menu_ingredient_ids
            )
            if (
                balance.location_id in central_location_ids
                and product.brand_id is None
                and not recipe_related
            ):
                blockers.append(
                    _issue(
                        "central_product_brand_ambiguous",
                        f"{product.name} มียอดกลางแต่ยังไม่ผูกแบรนด์หรือสูตรของแบรนด์นี้",
                        product_id=str(product.id),
                        location_id=str(balance.location_id),
                        qty=float(qty_on_hand),
                    )
                )
            if (
                balance.location_id in central_location_ids
                and product.brand_id is not None
                and product.brand_id != brand.id
            ):
                blockers.append(
                    _issue(
                        "central_product_wrong_brand",
                        f"{product.name} เป็นสินค้าของแบรนด์อื่นแต่พบในคลังกลางนี้",
                        product_id=str(product.id),
                        product_brand_id=str(product.brand_id),
                        location_id=str(balance.location_id),
                        qty=float(qty_on_hand),
                    )
                )
            if (
                balance.location_id in central_location_ids
                and product.inventory_role == "not_stocked"
            ):
                blockers.append(
                    _issue(
                        "not_stocked_product_has_balance",
                        f"{product.name} ตั้งเป็นไม่ตัด stock แต่ยังมียอดในคลังกลาง",
                        product_id=str(product.id),
                        location_id=str(balance.location_id),
                        qty=float(qty_on_hand),
                    )
                )
            if ready_location is not None and balance.location_id == ready_location.id:
                if qty_on_hand < 0:
                    blockers.append(
                        _issue(
                            "negative_ready_balance",
                            f"READY ของ {product.name} ติดลบ",
                            product_id=str(product.id),
                            qty=float(qty_on_hand),
                        )
                    )
                if product.inventory_role != "central_ready":
                    blockers.append(
                        _issue(
                            "wrong_product_in_ready",
                            f"{product.name} อยู่ READY แต่ role ไม่ใช่ CENTRAL-READY",
                            product_id=str(product.id),
                            inventory_role=product.inventory_role,
                            qty=float(qty_on_hand),
                        )
                    )
            if raw_location is not None and balance.location_id == raw_location.id:
                if product.inventory_role == "central_ready" and qty_on_hand < 0:
                    blockers.append(
                        _issue(
                            "negative_cutover_source",
                            f"ยอดต้นทางของ {product.name} ติดลบ",
                            product_id=str(product.id),
                            qty=float(qty_on_hand),
                        )
                    )
                if product.inventory_role == "store_local":
                    blockers.append(
                        _issue(
                            "store_local_in_central",
                            f"สินค้า STORE-STOCK {product.name} มียอดในคลังกลาง",
                            product_id=str(product.id),
                            qty=float(qty_on_hand),
                        )
                    )
            if balance.location_id in store_location_ids and product.inventory_role == "central_raw":
                blockers.append(
                    _issue(
                        "raw_product_in_store",
                        f"วัตถุดิบ RAW {product.name} มียอดใน STORE-STOCK",
                        product_id=str(product.id),
                        location_id=str(balance.location_id),
                        qty=float(qty_on_hand),
                    )
                )

        transfer_candidates: list[dict] = []
        if raw_location is not None and ready_location is not None:
            for balance in balances:
                if (
                    balance.location_id != raw_location.id
                    or balance.product.inventory_role != "central_ready"
                    or q4(balance.qty_on_hand) <= 0
                ):
                    continue
                if q4(balance.qty_reserved) > 0:
                    blockers.append(
                        _issue(
                            "cutover_source_reserved",
                            f"{balance.product.name} มียอดจอง ห้าม cutover ระหว่างมีงานค้าง",
                            product_id=str(balance.product_id),
                            qty_reserved=float(q4(balance.qty_reserved)),
                        )
                    )
                destination = balance_by_key.get(
                    (ready_location.id, balance.product_id, balance.variant_id)
                )
                transfer_candidates.append(
                    {
                        "source_balance_id": str(balance.id),
                        "product_id": str(balance.product_id),
                        "variant_id": str(balance.variant_id) if balance.variant_id else None,
                        "sku": balance.product.sku,
                        "product_name": balance.product.name,
                        "unit": balance.product.unit.code if balance.product.unit else None,
                        "qty": float(q4(balance.qty_on_hand)),
                        "qty_reserved": float(q4(balance.qty_reserved)),
                        "cost_per_unit": float(q4(balance.cost_per_unit)),
                        "destination_qty_before": float(q4(destination.qty_on_hand if destination else 0)),
                    }
                )

        active_central_orders = int(
            await self.db.scalar(
                select(func.count(CentralOrder.id)).where(
                    CentralOrder.company_id == company_id,
                    CentralOrder.brand_id == brand.id,
                    CentralOrder.status.in_(ACTIVE_CENTRAL_ORDER_STATUSES),
                )
            ) or 0
        )
        active_production_batches = int(
            await self.db.scalar(
                select(func.count(ProductionBatch.id)).where(
                    ProductionBatch.company_id == company_id,
                    ProductionBatch.brand_id == brand.id,
                    ProductionBatch.status == "in_progress",
                )
            ) or 0
        )
        planned_production_batches = int(
            await self.db.scalar(
                select(func.count(ProductionBatch.id)).where(
                    ProductionBatch.company_id == company_id,
                    ProductionBatch.brand_id == brand.id,
                    ProductionBatch.status.in_(["draft", "planned"]),
                )
            ) or 0
        )
        active_transfers = 0
        if audit_location_ids:
            active_transfers = int(
                await self.db.scalar(
                    select(func.count(TransferOrder.id)).where(
                        TransferOrder.company_id == company_id,
                        TransferOrder.status.in_(ACTIVE_TRANSFER_STATUSES),
                        (TransferOrder.from_location_id.in_(audit_location_ids))
                        | (TransferOrder.to_location_id.in_(audit_location_ids)),
                    )
                ) or 0
            )
        if active_central_orders:
            blockers.append(
                _issue(
                    "active_central_orders",
                    "ยังมีใบสั่งกลางที่อาจเปลี่ยนยอด READY",
                    count=active_central_orders,
                )
            )
        if active_production_batches:
            blockers.append(
                _issue(
                    "active_production_batches",
                    "ยังมี Production Batch กำลังผลิต",
                    count=active_production_batches,
                )
            )
        if active_transfers:
            blockers.append(
                _issue(
                    "active_transfers",
                    "ยังมี Transfer ที่ยังไม่จบใน location ที่เกี่ยวข้อง",
                    count=active_transfers,
                )
            )
        if planned_production_batches:
            warnings.append(
                _issue(
                    "planned_production_batches",
                    "มี Production Batch ที่ยังไม่เริ่ม ควรตรวจทานหลัง cutover",
                    count=planned_production_batches,
                )
            )

        completed_run = await self.db.scalar(
            select(StockCutoverRun)
            .options(
                selectinload(StockCutoverRun.items).selectinload(StockCutoverItem.product)
            )
            .where(
                StockCutoverRun.company_id == company_id,
                StockCutoverRun.brand_id == brand.id,
                StockCutoverRun.status == "completed",
            )
            .order_by(StockCutoverRun.executed_at.desc().nullslast())
            .limit(1)
        )
        if completed_run is not None:
            blockers.append(
                _issue(
                    "cutover_already_completed",
                    "แบรนด์นี้เคย cutover สำเร็จแล้ว ห้ามย้ายซ้ำ",
                    run_id=str(completed_run.id),
                    executed_at=completed_run.executed_at.isoformat() if completed_run.executed_at else None,
                )
            )

        product_audit = []
        for product in products:
            product_balances = [balance for balance in balances if balance.product_id == product.id]
            involved = bool(
                product.id in production_output_ids
                or product.id in menu_ingredient_ids
                or product.id in production_ingredient_ids
                or any(q4(balance.qty_on_hand) != 0 for balance in product_balances)
            )
            if not involved:
                continue
            product_audit.append(
                {
                    "product_id": str(product.id),
                    "sku": product.sku,
                    "product_name": product.name,
                    "inventory_role": product.inventory_role,
                    "is_production_output": product.id in production_output_ids,
                    "is_production_ingredient": product.id in production_ingredient_ids,
                    "is_menu_ingredient": product.id in menu_ingredient_ids,
                    "balances": [
                        {
                            "balance_id": str(balance.id),
                            "branch_id": str(balance.branch_id),
                            "location_id": str(balance.location_id),
                            "location_code": balance.location.code if balance.location else None,
                            "location_name": balance.location.name if balance.location else None,
                            "qty_on_hand": float(q4(balance.qty_on_hand)),
                            "qty_reserved": float(q4(balance.qty_reserved)),
                            "cost_per_unit": float(q4(balance.cost_per_unit)),
                        }
                        for balance in product_balances
                    ],
                }
            )

        blockers = self._deduplicate_issues(blockers)
        warnings = self._deduplicate_issues(warnings)
        active_documents = {
            "central_orders": active_central_orders,
            "production_in_progress": active_production_batches,
            "production_planned": planned_production_batches,
            "transfers": active_transfers,
        }
        token_snapshot = {
            "brand_id": str(brand.id),
            "raw_location_id": str(raw_location.id) if raw_location else None,
            "ready_location_id": str(ready_location.id) if ready_location else None,
            "products": [
                {
                    "product_id": str(product.id),
                    "brand_id": str(product.brand_id) if product.brand_id else None,
                    "inventory_role": product.inventory_role,
                    "deleted_at": product.deleted_at.isoformat() if product.deleted_at else None,
                }
                for product in products
            ],
            "balances": [
                {
                    "balance_id": str(balance.id),
                    "branch_id": str(balance.branch_id),
                    "location_id": str(balance.location_id),
                    "product_id": str(balance.product_id),
                    "variant_id": str(balance.variant_id) if balance.variant_id else None,
                    "qty_on_hand": float(q4(balance.qty_on_hand)),
                    "qty_reserved": float(q4(balance.qty_reserved)),
                    "cost_per_unit": float(q4(balance.cost_per_unit)),
                }
                for balance in balances
            ],
            "recipe_product_ids": {
                "production_outputs": sorted(str(item) for item in production_output_ids),
                "production_ingredients": sorted(str(item) for item in production_ingredient_ids),
                "menu_ingredients": sorted(str(item) for item in menu_ingredient_ids),
            },
            "candidates": [
                {
                    "source_balance_id": item["source_balance_id"],
                    "product_id": item["product_id"],
                    "variant_id": item["variant_id"],
                    "qty": item["qty"],
                    "qty_reserved": item["qty_reserved"],
                    "cost_per_unit": item["cost_per_unit"],
                    "destination_qty_before": item["destination_qty_before"],
                }
                for item in transfer_candidates
            ],
            "blocker_codes": sorted(item["code"] for item in blockers),
            "active_documents": active_documents,
            "store_locations": [
                {
                    "branch_id": item["branch_id"],
                    "store_location_id": item["store_location_id"],
                    "is_valid": item["is_valid"],
                }
                for item in store_locations
            ],
        }
        preview_token = make_preview_token(token_snapshot)
        return {
            "brand_id": str(brand.id),
            "brand_slug": brand.slug,
            "brand_name": brand.name,
            "central_branch_id": str(brand.central_branch_id) if brand.central_branch_id else None,
            "raw_location": self._serialize_location(raw_location),
            "ready_location": self._serialize_location(ready_location),
            "store_locations": store_locations,
            "product_audit": product_audit,
            "transfer_candidates": transfer_candidates,
            "candidate_count": len(transfer_candidates),
            "candidate_total_qty": float(
                q4(sum((Decimal(str(item["qty"])) for item in transfer_candidates), Decimal("0")))
            ),
            "candidate_total_value": float(
                q4(
                    sum(
                        (
                            Decimal(str(item["qty"])) * Decimal(str(item["cost_per_unit"]))
                            for item in transfer_candidates
                        ),
                        Decimal("0"),
                    )
                )
            ),
            "active_documents": active_documents,
            "blockers": blockers,
            "warnings": warnings,
            "is_ready": not blockers,
            "preview_token": preview_token,
            "required_confirmation": f"CUTOVER {brand.slug.upper()}",
            "completed_run": self.serialize_run(completed_run) if completed_run else None,
            "token_snapshot": token_snapshot,
        }

    async def execute(
        self,
        *,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        user_id: uuid.UUID,
        preview_token: str,
        confirmation_text: str,
        note: str | None = None,
    ) -> dict:
        preview = await self.preview(
            company_id=company_id,
            brand_id=brand_id,
            lock=True,
        )
        if confirmation_text.strip() != preview["required_confirmation"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"กรุณาพิมพ์ {preview['required_confirmation']} เพื่อยืนยัน",
            )
        if preview["blockers"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "ยังมี blocker ห้าม cutover",
                    "blockers": preview["blockers"],
                },
            )
        if preview_token != preview["preview_token"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="ข้อมูล stock เปลี่ยนหลัง preview กรุณาโหลด preview ใหม่",
            )
        raw_location_id = uuid.UUID(preview["raw_location"]["id"])
        ready_location_id = uuid.UUID(preview["ready_location"]["id"])
        run = StockCutoverRun(
            company_id=company_id,
            brand_id=brand_id,
            source_location_id=raw_location_id,
            destination_location_id=ready_location_id,
            status="running",
            preview_token=preview["preview_token"],
            preview_snapshot={
                "candidate_count": preview["candidate_count"],
                "candidate_total_qty": preview["candidate_total_qty"],
                "candidate_total_value": preview["candidate_total_value"],
                "active_documents": preview["active_documents"],
                "store_locations": preview["store_locations"],
                "transfer_candidates": preview["transfer_candidates"],
                "warnings": preview["warnings"],
            },
            executed_by=user_id,
            note=note,
        )
        self.db.add(run)
        await self.db.flush()

        total_qty = Decimal("0")
        for candidate in preview["transfer_candidates"]:
            product_id = uuid.UUID(candidate["product_id"])
            variant_id = uuid.UUID(candidate["variant_id"]) if candidate["variant_id"] else None
            source_balance = await self.db.scalar(
                select(StockBalance)
                .where(StockBalance.id == uuid.UUID(candidate["source_balance_id"]))
                .with_for_update()
            )
            if source_balance is None:
                raise HTTPException(status_code=409, detail="ไม่พบ balance ต้นทาง กรุณา preview ใหม่")
            qty = q4(source_balance.qty_on_hand)
            if qty <= 0 or q4(source_balance.qty_reserved) > 0:
                raise HTTPException(status_code=409, detail="ยอดต้นทางเปลี่ยน กรุณา preview ใหม่")
            destination_balance = await self.stock_service._get_or_create_balance(
                company_id=company_id,
                branch_id=source_balance.branch_id,
                location_id=ready_location_id,
                product_id=product_id,
                variant_id=variant_id,
            )
            source_before = q4(source_balance.qty_on_hand)
            destination_before = q4(destination_balance.qty_on_hand)
            cost = q4(source_balance.cost_per_unit)
            movement_note = note or f"Stock separation cutover {preview['brand_slug']}"
            movement_out = await self.stock_service._record_movement(
                balance=source_balance,
                movement_type="transfer_out",
                qty_delta=-qty,
                user_id=user_id,
                cost_per_unit=cost,
                reference_type="stock_separation_cutover",
                reference_id=str(run.id),
                note=movement_note,
            )
            movement_in = await self.stock_service._record_movement(
                balance=destination_balance,
                movement_type="transfer_in",
                qty_delta=qty,
                user_id=user_id,
                cost_per_unit=cost,
                reference_type="stock_separation_cutover",
                reference_id=str(run.id),
                note=movement_note,
            )
            self.db.add(
                StockCutoverItem(
                    run_id=run.id,
                    company_id=company_id,
                    product_id=product_id,
                    variant_id=variant_id,
                    qty=qty,
                    cost_per_unit=cost,
                    source_qty_before=source_before,
                    source_qty_after=q4(source_balance.qty_on_hand),
                    destination_qty_before=destination_before,
                    destination_qty_after=q4(destination_balance.qty_on_hand),
                    source_movement_id=movement_out.id,
                    destination_movement_id=movement_in.id,
                )
            )
            total_qty += qty

        run.item_count = len(preview["transfer_candidates"])
        run.total_qty = q4(total_qty)
        run.status = "completed"
        run.executed_at = datetime.now(timezone.utc)
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=uuid.UUID(preview["central_branch_id"]),
                user_id=user_id,
                action="brand.stock.cutover.execute",
                resource="StockCutoverRun",
                resource_id=str(run.id),
                new_value={
                    "brand_id": str(brand_id),
                    "source_location_id": str(raw_location_id),
                    "destination_location_id": str(ready_location_id),
                    "preview_token": preview["preview_token"],
                    "item_count": run.item_count,
                    "total_qty": str(run.total_qty),
                },
            )
        )
        await self.db.commit()
        saved = await self._load_run(company_id, brand_id, run.id)
        return self.serialize_run(saved)

    async def list_runs(self, company_id: uuid.UUID, brand_id: uuid.UUID) -> list[dict]:
        runs = list(
            (
                await self.db.scalars(
                    select(StockCutoverRun)
                    .options(
                        selectinload(StockCutoverRun.items).selectinload(StockCutoverItem.product)
                    )
                    .where(
                        StockCutoverRun.company_id == company_id,
                        StockCutoverRun.brand_id == brand_id,
                    )
                    .order_by(StockCutoverRun.created_at.desc())
                )
            ).all()
        )
        return [self.serialize_run(run) for run in runs]

    async def dashboard(self, company_id: uuid.UUID, brand_id: uuid.UUID) -> dict:
        preview = await self.preview(company_id=company_id, brand_id=brand_id)
        raw_id = preview["raw_location"]["id"] if preview["raw_location"] else None
        ready_id = preview["ready_location"]["id"] if preview["ready_location"] else None
        store_by_location = {
            item["store_location_id"]: item
            for item in preview["store_locations"]
            if item["store_location_id"]
        }
        central = {
            "raw": self._empty_stock_summary(preview["raw_location"]),
            "ready": self._empty_stock_summary(preview["ready_location"]),
        }
        stores = {
            item["branch_id"]: {
                **item,
                "sku_count": 0,
                "total_qty": 0.0,
                "total_value": 0.0,
                "negative_count": 0,
            }
            for item in preview["store_locations"]
        }
        for product in preview["product_audit"]:
            for balance in product["balances"]:
                location_id = balance["location_id"]
                qty = Decimal(str(balance["qty_on_hand"]))
                value = qty * Decimal(str(balance["cost_per_unit"]))
                if location_id == raw_id:
                    self._add_stock_summary(central["raw"], product, balance, qty, value)
                elif location_id == ready_id:
                    self._add_stock_summary(central["ready"], product, balance, qty, value)
                elif location_id in store_by_location:
                    branch_id = store_by_location[location_id]["branch_id"]
                    store = stores[branch_id]
                    store["sku_count"] += 1
                    store["total_qty"] += float(q4(qty))
                    store["total_value"] += float(q4(value))
                    if qty < 0:
                        store["negative_count"] += 1

        product_ids = [uuid.UUID(item["product_id"]) for item in preview["product_audit"]]
        store_location_ids = [uuid.UUID(value) for value in store_by_location]
        in_transit_items: list[dict] = []
        if product_ids and store_location_ids:
            rows = list(
                (
                    await self.db.execute(
                        select(TransferOrderItem, TransferOrder, Branch)
                        .join(TransferOrder, TransferOrderItem.to_id == TransferOrder.id)
                        .join(Branch, TransferOrder.to_branch_id == Branch.id)
                        .where(
                            TransferOrder.company_id == company_id,
                            TransferOrder.status.in_(["in_transit", "partially_received"]),
                            TransferOrder.to_location_id.in_(store_location_ids),
                            TransferOrderItem.product_id.in_(product_ids),
                        )
                        .order_by(Branch.name.asc(), TransferOrder.to_number.asc())
                    )
                ).all()
            )
            for item, transfer, branch in rows:
                qty = q4(item.qty_in_transit)
                if qty <= 0:
                    continue
                in_transit_items.append(
                    {
                        "transfer_order_id": str(transfer.id),
                        "transfer_order_number": transfer.to_number,
                        "branch_id": str(branch.id),
                        "branch_name": branch.name,
                        "product_id": str(item.product_id),
                        "sku": item.sku,
                        "product_name": item.product_name,
                        "unit": item.unit_code,
                        "qty_in_transit": float(qty),
                        "expected_date": transfer.expected_date.isoformat() if transfer.expected_date else None,
                    }
                )
        return {
            "brand_id": preview["brand_id"],
            "brand_slug": preview["brand_slug"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "central": central,
            "stores": sorted(stores.values(), key=lambda item: item["branch_name"]),
            "in_transit": {
                "order_count": len({item["transfer_order_id"] for item in in_transit_items}),
                "total_qty": float(
                    q4(sum((Decimal(str(item["qty_in_transit"])) for item in in_transit_items), Decimal("0")))
                ),
                "items": in_transit_items,
            },
            "data_quality": {
                "blocker_count": len(preview["blockers"]),
                "warning_count": len(preview["warnings"]),
                "unconfigured_store_count": sum(1 for item in preview["store_locations"] if not item["is_valid"]),
                "negative_store_count": sum(item["negative_count"] for item in stores.values()),
            },
            "cutover": {
                "is_ready": preview["is_ready"],
                "candidate_count": preview["candidate_count"],
                "candidate_total_qty": preview["candidate_total_qty"],
                "completed_run": preview["completed_run"],
            },
        }

    async def _load_run(
        self,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> StockCutoverRun:
        run = await self.db.scalar(
            select(StockCutoverRun)
            .options(selectinload(StockCutoverRun.items).selectinload(StockCutoverItem.product))
            .where(
                StockCutoverRun.id == run_id,
                StockCutoverRun.company_id == company_id,
                StockCutoverRun.brand_id == brand_id,
            )
        )
        if run is None:
            raise HTTPException(status_code=404, detail="ไม่พบ cutover run")
        return run

    @staticmethod
    def serialize_run(run: StockCutoverRun | None) -> dict | None:
        if run is None:
            return None
        return {
            "id": str(run.id),
            "brand_id": str(run.brand_id),
            "source_location_id": str(run.source_location_id),
            "destination_location_id": str(run.destination_location_id),
            "status": run.status,
            "preview_token": run.preview_token,
            "preview_snapshot": run.preview_snapshot,
            "item_count": run.item_count,
            "total_qty": float(q4(run.total_qty)),
            "executed_by": str(run.executed_by),
            "executed_at": run.executed_at.isoformat() if run.executed_at else None,
            "note": run.note,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "items": [
                {
                    "id": str(item.id),
                    "product_id": str(item.product_id),
                    "sku": item.product.sku if item.product else None,
                    "product_name": item.product.name if item.product else None,
                    "variant_id": str(item.variant_id) if item.variant_id else None,
                    "qty": float(q4(item.qty)),
                    "cost_per_unit": float(q4(item.cost_per_unit)),
                    "source_qty_before": float(q4(item.source_qty_before)),
                    "source_qty_after": float(q4(item.source_qty_after)),
                    "destination_qty_before": float(q4(item.destination_qty_before)),
                    "destination_qty_after": float(q4(item.destination_qty_after)),
                    "source_movement_id": str(item.source_movement_id),
                    "destination_movement_id": str(item.destination_movement_id),
                }
                for item in run.items
            ],
        }

    @staticmethod
    def _serialize_location(location: StockLocation | None) -> dict | None:
        if location is None:
            return None
        return {
            "id": str(location.id),
            "branch_id": str(location.branch_id),
            "code": location.code,
            "name": location.name,
            "is_active": location.is_active,
        }

    @staticmethod
    def _deduplicate_issues(items: list[dict]) -> list[dict]:
        unique: dict[str, dict] = {}
        for item in items:
            key = json.dumps(item, sort_keys=True, ensure_ascii=False)
            unique[key] = item
        return list(unique.values())

    @staticmethod
    def _empty_stock_summary(location: dict | None) -> dict:
        return {
            "location": location,
            "sku_count": 0,
            "total_qty": 0.0,
            "total_reserved": 0.0,
            "total_value": 0.0,
            "negative_count": 0,
            "items": [],
        }

    @staticmethod
    def _add_stock_summary(
        summary: dict,
        product: dict,
        balance: dict,
        qty: Decimal,
        value: Decimal,
    ) -> None:
        summary["sku_count"] += 1
        summary["total_qty"] += float(q4(qty))
        summary["total_reserved"] += float(q4(balance["qty_reserved"]))
        summary["total_value"] += float(q4(value))
        if qty < 0:
            summary["negative_count"] += 1
        summary["items"].append(
            {
                "product_id": product["product_id"],
                "sku": product["sku"],
                "product_name": product["product_name"],
                "inventory_role": product["inventory_role"],
                "qty_on_hand": balance["qty_on_hand"],
                "qty_reserved": balance["qty_reserved"],
                "cost_per_unit": balance["cost_per_unit"],
                "stock_value": float(q4(value)),
            }
        )
