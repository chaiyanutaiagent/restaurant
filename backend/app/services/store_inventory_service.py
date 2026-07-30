from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.pos import SaleOrder
from app.models.product import Product
from app.models.stock import StockBalance, StockMovement
from app.models.stock_count import StockCountSession
from app.schemas.restaurant import StoreStockAdjustmentRequest
from app.services.notification_service import NotificationService
from app.services.recipe_service import RecipeService, convert_quantity
from app.services.stock_service import StockService


FOURPLACES = Decimal("0.0001")
BANGKOK = ZoneInfo("Asia/Bangkok")


def q4(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(FOURPLACES, rounding=ROUND_HALF_UP)


def calculate_recipe_usage(
    ingredient_qty: Decimal,
    sold_qty: Decimal,
    yield_qty: Decimal,
    loss_percent: Decimal,
) -> Decimal:
    """Return ingredient usage for sold quantity using the recipe's effective yield."""
    loss_rate = min(max(Decimal(loss_percent or 0), Decimal("0")), Decimal("100"))
    effective_yield = Decimal(yield_qty or 1) * (Decimal("1") - loss_rate / Decimal("100"))
    if effective_yield <= 0:
        effective_yield = FOURPLACES
    return q4(Decimal(ingredient_qty) * Decimal(sold_qty) / effective_yield)


class StoreInventoryService:
    """Post recipe-based stock movements against a branch's STORE-STOCK only."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.stock_service = StockService(db)
        self.recipe_service = RecipeService(db)

    async def adjust_store_stock(
        self,
        *,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        branch_id: uuid.UUID,
        location_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: StoreStockAdjustmentRequest,
    ) -> StockMovement:
        product = await self.db.scalar(
            select(Product).where(
                Product.id == payload.product_id,
                Product.company_id == company_id,
                Product.deleted_at.is_(None),
                Product.is_active.is_(True),
            )
        )
        if product is None or product.brand_id not in {None, brand_id}:
            raise ValueError("ไม่พบสินค้าของแบรนด์นี้")
        balance = await self.db.scalar(
            select(StockBalance)
            .where(
                StockBalance.company_id == company_id,
                StockBalance.branch_id == branch_id,
                StockBalance.location_id == location_id,
                StockBalance.product_id == product.id,
                StockBalance.variant_id.is_(None),
            )
            .with_for_update()
        )
        if balance is None:
            raise ValueError("สินค้านี้ยังไม่มีใน STORE-STOCK ของสาขา")

        raw_qty = q4(payload.qty)
        if raw_qty == 0:
            raise ValueError("จำนวนต้องไม่เป็นศูนย์")
        if payload.kind == "waste":
            if raw_qty <= 0:
                raise ValueError("จำนวนของเสียต้องมากกว่าศูนย์")
            qty_delta = -raw_qty
            movement_type = "waste"
        else:
            qty_delta = raw_qty
            movement_type = "adjust"
            if payload.reason == "count_higher" and qty_delta < 0:
                raise ValueError("ตรวจนับเกินต้องปรับเพิ่มเป็นจำนวนบวก")
            if payload.reason == "count_lower" and qty_delta > 0:
                raise ValueError("ตรวจนับขาดต้องปรับลดเป็นจำนวนลบ")

        reason_labels = {
            "prep_waste": "เสียระหว่างเตรียม",
            "expired": "หมดอายุ",
            "staff_sample": "พนักงาน/ตัวอย่าง",
            "return_central": "คืนส่วนกลาง",
            "count_higher": "ตรวจนับเกิน",
            "count_lower": "ตรวจนับขาด",
            "other": "อื่น ๆ",
        }
        note = f"[{payload.reason}] {reason_labels[payload.reason]}"
        if payload.note and payload.note.strip():
            note += f" — {payload.note.strip()}"
        movement = await self.stock_service._record_movement(
            balance=balance,
            movement_type=movement_type,
            qty_delta=qty_delta,
            user_id=user_id,
            cost_per_unit=Decimal(balance.cost_per_unit or product.cost_price or 0),
            reference_type="store_stock_adjustment",
            reference_id=None,
            note=note,
        )
        movement.reference_id = str(movement.id)
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=branch_id,
                user_id=user_id,
                action=f"brand.store.stock.{payload.kind}",
                resource="StockMovement",
                resource_id=str(movement.id),
                new_value={
                    "brand_id": str(brand_id),
                    "location_id": str(location_id),
                    "product_id": str(product.id),
                    "qty": str(qty_delta),
                    "reason": payload.reason,
                    "note": payload.note,
                },
            )
        )
        await self.db.commit()
        return movement

    async def daily_summary(
        self,
        *,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        branch_id: uuid.UUID,
        location_id: uuid.UUID,
        business_date: date,
    ) -> dict:
        day_start = datetime.combine(business_date, time.min, BANGKOK).astimezone(timezone.utc)
        day_end = datetime.combine(business_date, time.max, BANGKOK).astimezone(timezone.utc)
        balances = list(
            (
                await self.db.scalars(
                    select(StockBalance)
                    .join(Product, Product.id == StockBalance.product_id)
                    .options(selectinload(StockBalance.product).selectinload(Product.unit))
                    .where(
                        StockBalance.company_id == company_id,
                        StockBalance.branch_id == branch_id,
                        StockBalance.location_id == location_id,
                        Product.deleted_at.is_(None),
                        Product.is_active.is_(True),
                        (Product.brand_id == brand_id) | (Product.brand_id.is_(None)),
                    )
                    .order_by(Product.name.asc())
                )
            ).all()
        )
        movements = list(
            (
                await self.db.scalars(
                    select(StockMovement).where(
                        StockMovement.company_id == company_id,
                        StockMovement.branch_id == branch_id,
                        StockMovement.location_id == location_id,
                        StockMovement.created_at >= day_start,
                        StockMovement.created_at <= day_end,
                    ).order_by(StockMovement.created_at.asc(), StockMovement.id.asc())
                )
            ).all()
        )
        completed_count = await self.db.scalar(
            select(StockCountSession)
            .options(selectinload(StockCountSession.items))
            .where(
                StockCountSession.company_id == company_id,
                StockCountSession.branch_id == branch_id,
                StockCountSession.location_id == location_id,
                StockCountSession.count_date == business_date,
                StockCountSession.status == "completed",
            )
            .order_by(StockCountSession.completed_at.desc().nullslast())
            .limit(1)
        )
        count_items = {
            (item.product_id, item.variant_id): item
            for item in completed_count.items
        } if completed_count else {}
        movements_by_product: dict[uuid.UUID, list[StockMovement]] = {}
        for movement in movements:
            movements_by_product.setdefault(movement.product_id, []).append(movement)

        lines: list[dict] = []
        for balance in balances:
            product = balance.product
            product_movements = movements_by_product.get(product.id, [])
            opening = Decimal(product_movements[0].qty_before) if product_movements else Decimal(balance.qty_on_hand or 0)
            received = sum(
                (Decimal(item.qty) for item in product_movements if item.movement_type in {"receive", "opening", "transfer_in"} and item.qty > 0),
                Decimal("0"),
            )
            used_sales = -sum(
                (Decimal(item.qty) for item in product_movements if item.movement_type == "sale" and item.qty < 0),
                Decimal("0"),
            )
            sale_returns = sum(
                (Decimal(item.qty) for item in product_movements if item.movement_type == "sale_return" and item.qty > 0),
                Decimal("0"),
            )
            waste = -sum(
                (Decimal(item.qty) for item in product_movements if item.movement_type == "waste" and item.qty < 0),
                Decimal("0"),
            )
            adjustment = sum(
                (Decimal(item.qty) for item in product_movements if item.movement_type == "adjust"),
                Decimal("0"),
            )
            known_types = {"receive", "opening", "transfer_in", "sale", "sale_return", "waste", "adjust"}
            other_net = sum(
                (Decimal(item.qty) for item in product_movements if item.movement_type not in known_types),
                Decimal("0"),
            )
            formula_close = q4(opening + received - used_sales + sale_returns - waste + adjustment + other_net)
            count_item = count_items.get((product.id, balance.variant_id))
            expected_close = q4(count_item.expected_qty) if count_item else formula_close
            physical_qty = q4(count_item.actual_qty) if count_item and count_item.actual_qty is not None else None
            variance_qty = q4(count_item.variance_qty) if count_item and count_item.variance_qty is not None else None
            lines.append(
                {
                    "product_id": str(product.id),
                    "sku": product.sku,
                    "product_name": product.name,
                    "inventory_role": product.inventory_role,
                    "unit_code": product.unit.code if product.unit else None,
                    "opening_qty": float(q4(opening)),
                    "received_qty": float(q4(received)),
                    "used_sales_qty": float(q4(used_sales)),
                    "sale_return_qty": float(q4(sale_returns)),
                    "waste_qty": float(q4(waste)),
                    "adjustment_qty": float(q4(adjustment)),
                    "other_net_qty": float(q4(other_net)),
                    "expected_closing_qty": float(expected_close),
                    "physical_qty": float(physical_qty) if physical_qty is not None else None,
                    "variance_qty": float(variance_qty) if variance_qty is not None else None,
                    "current_qty": float(q4(balance.qty_on_hand)),
                    "is_negative": Decimal(balance.qty_on_hand or 0) < 0,
                }
            )
        return {
            "date": business_date.isoformat(),
            "brand_id": str(brand_id),
            "branch_id": str(branch_id),
            "location_id": str(location_id),
            "stock_count_session_id": str(completed_count.id) if completed_count else None,
            "stock_count_status": completed_count.status if completed_count else None,
            "negative_count": sum(1 for item in lines if item["is_negative"]),
            "items": lines,
        }

    async def post_sale(
        self,
        *,
        order: SaleOrder,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        branch_id: uuid.UUID,
        location_id: uuid.UUID,
        user_id: uuid.UUID,
        items: list[tuple[Product, Decimal]],
    ) -> list[str]:
        locked_order = await self.db.scalar(
            select(SaleOrder).where(
                SaleOrder.id == order.id,
                SaleOrder.company_id == company_id,
            ).with_for_update()
        )
        if locked_order is not None:
            order = locked_order
        if order.recipe_stock_posted_at is not None:
            return self._decode_warnings(order.recipe_stock_warnings)

        existing = await self.db.scalar(
            select(func.count(StockMovement.id)).where(
                StockMovement.company_id == company_id,
                StockMovement.location_id == location_id,
                StockMovement.reference_type == "pos_sale_recipe",
                StockMovement.reference_id == str(order.id),
            )
        )
        if int(existing or 0) > 0:
            order.recipe_stock_status = order.recipe_stock_status or "posted"
            order.recipe_stock_posted_at = order.recipe_stock_posted_at or datetime.now(timezone.utc)
            return self._decode_warnings(order.recipe_stock_warnings)

        usage, warnings = await self._expand_items(
            company_id=company_id,
            brand_id=brand_id,
            branch_id=branch_id,
            items=items,
        )
        negative_items: list[tuple[Product, Decimal, Decimal]] = []
        for product, qty in usage.values():
            balance = await self.stock_service._get_or_create_balance(
                company_id=company_id,
                branch_id=branch_id,
                location_id=location_id,
                product_id=product.id,
                variant_id=None,
            )
            qty_before = Decimal(balance.qty_on_hand or 0)
            if qty_before < qty:
                shortage = q4(qty - qty_before)
                warnings.append(
                    f"{product.name} ไม่พอ {shortage} {product.unit.code if product.unit else ''}".strip()
                )
                negative_items.append((product, qty_before, q4(qty_before - qty)))
            await self.stock_service._record_movement(
                balance=balance,
                movement_type="sale",
                qty_delta=-qty,
                user_id=user_id,
                cost_per_unit=Decimal(balance.cost_per_unit or product.cost_price or 0),
                reference_type="pos_sale_recipe",
                reference_id=str(order.id),
                note=f"ตัดตามสูตรจากใบขาย {order.order_number}",
                allow_negative=True,
            )

        order.recipe_stock_status = "posted_with_warning" if warnings else "posted"
        order.recipe_stock_warnings = json.dumps(warnings, ensure_ascii=False) if warnings else None
        order.recipe_stock_posted_at = datetime.now(timezone.utc)
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=branch_id,
                user_id=user_id,
                action="brand.store.stock.sale_recipe_post",
                resource="SaleOrder",
                resource_id=str(order.id),
                new_value={
                    "brand_id": str(brand_id),
                    "location_id": str(location_id),
                    "movement_count": len(usage),
                    "warnings": warnings,
                },
            )
        )
        for product, qty_before, qty_after in negative_items:
            try:
                await NotificationService(self.db).notify_event(
                    company_id,
                    "stock.negative",
                    context={
                        "product_name": product.name,
                        "sku": product.sku,
                        "qty_before": str(qty_before),
                        "qty_after": str(qty_after),
                        "order_number": order.order_number,
                    },
                    reference_type="SaleOrder",
                    reference_id=str(order.id),
                )
            except Exception:
                # Notifications must not prevent a paid order from completing.
                pass
        return warnings

    async def reverse_items(
        self,
        *,
        order: SaleOrder,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        branch_id: uuid.UUID,
        location_id: uuid.UUID,
        user_id: uuid.UUID,
        items: list[tuple[Product, Decimal]],
        reference_type: str,
        note: str,
        mark_fully_reversed: bool = False,
    ) -> None:
        if order.recipe_stock_posted_at is None:
            return
        if mark_fully_reversed and order.recipe_stock_reversed_at is not None:
            return
        usage, _warnings = await self._expand_items(
            company_id=company_id,
            brand_id=brand_id,
            branch_id=branch_id,
            items=items,
        )
        for product, qty in usage.values():
            balance = await self.stock_service._get_or_create_balance(
                company_id=company_id,
                branch_id=branch_id,
                location_id=location_id,
                product_id=product.id,
                variant_id=None,
            )
            await self.stock_service._record_movement(
                balance=balance,
                movement_type="sale_return",
                qty_delta=qty,
                user_id=user_id,
                cost_per_unit=Decimal(balance.cost_per_unit or product.cost_price or 0),
                reference_type=reference_type,
                reference_id=str(order.id),
                note=note,
            )
        if mark_fully_reversed:
            order.recipe_stock_reversed_at = datetime.now(timezone.utc)

    async def _expand_items(
        self,
        *,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        branch_id: uuid.UUID,
        items: list[tuple[Product, Decimal]],
    ) -> tuple[dict[uuid.UUID, tuple[Product, Decimal]], list[str]]:
        usage: dict[uuid.UUID, tuple[Product, Decimal]] = {}
        warnings: list[str] = []
        for menu_product, sold_qty in items:
            recipe = await self.recipe_service.get_recipe_by_product(
                menu_product.id,
                company_id,
                branch_id,
                recipe_type="menu_recipe",
                brand_id=brand_id,
            )
            if recipe is None:
                warnings.append(f"เมนู {menu_product.name} ยังไม่มีสูตรหน้าร้าน")
                continue
            if not recipe.ingredients:
                warnings.append(f"สูตร {recipe.name} ยังไม่มีวัตถุดิบ")
                continue
            for ingredient in recipe.ingredients:
                product = ingredient.ingredient
                if product is None:
                    warnings.append(f"สูตร {recipe.name} มีวัตถุดิบที่ไม่พบในระบบ")
                    continue
                if product.inventory_role not in {"central_ready", "store_local"}:
                    warnings.append(f"{product.name} ยังไม่ได้กำหนดเป็น READY หรือ STORE-STOCK")
                    continue
                recipe_qty = calculate_recipe_usage(
                    Decimal(ingredient.quantity),
                    Decimal(sold_qty),
                    Decimal(recipe.yield_qty),
                    Decimal(recipe.loss_percent or 0),
                )
                base_unit = product.unit.code if product.unit else ingredient.unit
                required = q4(convert_quantity(recipe_qty, ingredient.unit, base_unit))
                current_qty = usage.get(product.id, (product, Decimal("0")))[1]
                usage[product.id] = (product, q4(current_qty + required))
        return usage, list(dict.fromkeys(warnings))

    @staticmethod
    def _decode_warnings(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            value = json.loads(raw)
            return [str(item) for item in value] if isinstance(value, list) else [str(value)]
        except (TypeError, ValueError):
            return [raw]
