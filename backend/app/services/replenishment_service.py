from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.product import Product
from app.models.restaurant import (
    BranchReplenishmentPolicy,
    Recipe,
    RecipeIngredient,
    WapShiftClosure,
)
from app.models.stock import StockBalance, StockMovement
from app.models.transfer import TransferOrder, TransferOrderItem


BANGKOK = ZoneInfo("Asia/Bangkok")
FOURPLACES = Decimal("0.0001")
DEFAULT_SAFETY_STOCK_PERCENT = Decimal("10")
DEFAULT_SAFETY_STOCK_QTY = Decimal("0")
DEFAULT_PACK_SIZE = Decimal("1")
DEFAULT_LEAD_TIME_DAYS = 1
DEFAULT_MINIMUM_ORDER_QTY = Decimal("0")
DEFAULT_FORECAST_METHOD = "auto"


def q4(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(FOURPLACES, rounding=ROUND_HALF_UP)


def average_usage(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0.0000")
    return q4(sum((Decimal(value) for value in values), Decimal("0")) / Decimal(len(values)))


def choose_forecast_usage(
    *,
    latest_day_usage: Decimal,
    open_day_usage: list[Decimal],
    method: str = DEFAULT_FORECAST_METHOD,
) -> tuple[Decimal, str]:
    """Choose the MVP forecast while keeping closed days out of the average."""
    latest = max(q4(latest_day_usage), Decimal("0"))
    seven_day_average = average_usage(open_day_usage[:7])
    if method == "latest_day":
        return latest, "latest_day"
    if method == "average_7_open_days":
        return (seven_day_average if open_day_usage else latest), "average_7_open_days"
    if len(open_day_usage) >= 7:
        return seven_day_average, "average_7_open_days"
    return latest, "latest_day"


def calculate_suggested_order(
    *,
    forecast_qty: Decimal,
    safety_stock_percent: Decimal = DEFAULT_SAFETY_STOCK_PERCENT,
    safety_stock_qty: Decimal = DEFAULT_SAFETY_STOCK_QTY,
    store_on_hand: Decimal = Decimal("0"),
    confirmed_incoming: Decimal = Decimal("0"),
    pack_size: Decimal = DEFAULT_PACK_SIZE,
    minimum_order_qty: Decimal = DEFAULT_MINIMUM_ORDER_QTY,
) -> dict[str, Decimal]:
    forecast = max(q4(forecast_qty), Decimal("0"))
    percent = max(q4(safety_stock_percent), Decimal("0"))
    fixed_safety = max(q4(safety_stock_qty), Decimal("0"))
    safety = q4((forecast * percent / Decimal("100")) + fixed_safety)
    target = q4(forecast + safety)
    raw = q4(max(target - q4(store_on_hand) - max(q4(confirmed_incoming), Decimal("0")), Decimal("0")))
    if raw <= 0:
        suggested = Decimal("0.0000")
    else:
        pack = max(q4(pack_size), FOURPLACES)
        minimum = max(q4(minimum_order_qty), Decimal("0"))
        quantity_before_rounding = max(raw, minimum)
        suggested = q4(
            (quantity_before_rounding / pack).to_integral_value(rounding=ROUND_CEILING) * pack
        )
    return {
        "safety_stock_qty": safety,
        "target_qty": target,
        "raw_suggested_qty": raw,
        "suggested_qty": suggested,
    }


class ReplenishmentService:
    """Calculate STORE-STOCK replenishment without exposing central balances."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _open_business_dates(
        self,
        *,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        branch_id: uuid.UUID,
        business_date: date,
    ) -> list[str]:
        rows = list(
            (
                await self.db.scalars(
                    select(WapShiftClosure.business_date)
                    .where(
                        WapShiftClosure.company_id == company_id,
                        WapShiftClosure.brand_id == brand_id,
                        WapShiftClosure.branch_id == branch_id,
                        WapShiftClosure.business_date <= business_date.isoformat(),
                    )
                    .distinct()
                    .order_by(WapShiftClosure.business_date.desc())
                    .limit(7)
                )
            ).all()
        )
        return [str(value) for value in rows]

    async def suggestion(
        self,
        *,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        branch_id: uuid.UUID,
        location_id: uuid.UUID,
        business_date: date,
        include_disabled: bool = False,
    ) -> dict:
        recipe_ingredient_ids = set(
            (
                await self.db.scalars(
                    select(RecipeIngredient.ingredient_id)
                    .join(Recipe, RecipeIngredient.recipe_id == Recipe.id)
                    .where(
                        Recipe.company_id == company_id,
                        Recipe.brand_id == brand_id,
                        Recipe.recipe_type == "menu_recipe",
                        Recipe.is_active.is_(True),
                    )
                    .distinct()
                )
            ).all()
        )
        policies = list(
            (
                await self.db.scalars(
                    select(BranchReplenishmentPolicy)
                    .where(
                        BranchReplenishmentPolicy.company_id == company_id,
                        BranchReplenishmentPolicy.brand_id == brand_id,
                        BranchReplenishmentPolicy.branch_id == branch_id,
                    )
                )
            ).all()
        )
        policies_by_product = {policy.product_id: policy for policy in policies}
        candidate_ids = recipe_ingredient_ids | set(policies_by_product)
        if not candidate_ids:
            return self._empty_summary(brand_id, branch_id, location_id, business_date)

        products = list(
            (
                await self.db.scalars(
                    select(Product)
                    .options(selectinload(Product.unit))
                    .where(
                        Product.company_id == company_id,
                        Product.id.in_(candidate_ids),
                        Product.inventory_role == "central_ready",
                        Product.deleted_at.is_(None),
                        Product.is_active.is_(True),
                    )
                    .order_by(Product.name.asc())
                )
            ).all()
        )
        products = [
            product
            for product in products
            if product.brand_id in {None, brand_id}
        ]
        product_ids = [product.id for product in products]
        if not product_ids:
            return self._empty_summary(brand_id, branch_id, location_id, business_date)

        balances = list(
            (
                await self.db.scalars(
                    select(StockBalance).where(
                        StockBalance.company_id == company_id,
                        StockBalance.branch_id == branch_id,
                        StockBalance.location_id == location_id,
                        StockBalance.product_id.in_(product_ids),
                        StockBalance.variant_id.is_(None),
                    )
                )
            ).all()
        )
        balance_by_product = {balance.product_id: balance for balance in balances}

        open_dates = await self._open_business_dates(
            company_id=company_id,
            brand_id=brand_id,
            branch_id=branch_id,
            business_date=business_date,
        )
        history_dates = open_dates or [business_date.isoformat()]
        history_start_date = min(date.fromisoformat(value) for value in history_dates)
        history_start = datetime.combine(history_start_date, time.min, BANGKOK).astimezone(timezone.utc)
        history_end = datetime.combine(business_date, time.max, BANGKOK).astimezone(timezone.utc)
        movements = list(
            (
                await self.db.scalars(
                    select(StockMovement).where(
                        StockMovement.company_id == company_id,
                        StockMovement.branch_id == branch_id,
                        StockMovement.location_id == location_id,
                        StockMovement.product_id.in_(product_ids),
                        StockMovement.created_at >= history_start,
                        StockMovement.created_at <= history_end,
                    )
                )
            ).all()
        )

        usage_by_product: dict[uuid.UUID, dict[str, Decimal]] = {}
        received_today_by_product: dict[uuid.UUID, Decimal] = {}
        selected_date = business_date.isoformat()
        for movement in movements:
            created_at = movement.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            movement_date = created_at.astimezone(BANGKOK).date().isoformat()
            product_usage = usage_by_product.setdefault(movement.product_id, {})
            if movement.movement_type == "sale" and Decimal(movement.qty or 0) < 0:
                product_usage[movement_date] = product_usage.get(movement_date, Decimal("0")) - Decimal(movement.qty)
            elif movement.movement_type == "sale_return" and Decimal(movement.qty or 0) > 0:
                product_usage[movement_date] = product_usage.get(movement_date, Decimal("0")) - Decimal(movement.qty)
            if (
                movement_date == selected_date
                and movement.movement_type in {"receive", "transfer_in", "opening"}
                and Decimal(movement.qty or 0) > 0
            ):
                received_today_by_product[movement.product_id] = (
                    received_today_by_product.get(movement.product_id, Decimal("0")) + Decimal(movement.qty)
                )

        incoming_by_product: dict[uuid.UUID, Decimal] = {}
        transfer_items = list(
            (
                await self.db.scalars(
                    select(TransferOrderItem)
                    .join(TransferOrder, TransferOrderItem.to_id == TransferOrder.id)
                    .where(
                        TransferOrder.company_id == company_id,
                        TransferOrder.to_branch_id == branch_id,
                        TransferOrder.to_location_id == location_id,
                        TransferOrder.status.in_(["in_transit", "partially_received"]),
                        TransferOrderItem.product_id.in_(product_ids),
                    )
                )
            ).all()
        )
        for item in transfer_items:
            incoming_by_product[item.product_id] = q4(
                incoming_by_product.get(item.product_id, Decimal("0")) + item.qty_in_transit
            )

        lines: list[dict] = []
        for product in products:
            policy = policies_by_product.get(product.id)
            if policy is not None and not policy.is_enabled and not include_disabled:
                continue
            safety_percent = Decimal(policy.safety_stock_percent) if policy else DEFAULT_SAFETY_STOCK_PERCENT
            fixed_safety = Decimal(policy.safety_stock_qty) if policy else DEFAULT_SAFETY_STOCK_QTY
            pack_size = Decimal(policy.pack_size) if policy else DEFAULT_PACK_SIZE
            lead_time_days = int(policy.lead_time_days) if policy else DEFAULT_LEAD_TIME_DAYS
            minimum_order = Decimal(policy.minimum_order_qty) if policy else DEFAULT_MINIMUM_ORDER_QTY
            configured_method = policy.forecast_method if policy else DEFAULT_FORECAST_METHOD
            usage_by_date = usage_by_product.get(product.id, {})
            yesterday_usage = max(q4(usage_by_date.get(selected_date, Decimal("0"))), Decimal("0"))
            open_day_usage = [max(q4(usage_by_date.get(value, Decimal("0"))), Decimal("0")) for value in open_dates]
            average_7 = average_usage(open_day_usage)
            forecast, effective_method = choose_forecast_usage(
                latest_day_usage=yesterday_usage,
                open_day_usage=open_day_usage,
                method=configured_method,
            )
            balance = balance_by_product.get(product.id)
            on_hand = q4(balance.qty_on_hand if balance else 0)
            incoming = q4(incoming_by_product.get(product.id, Decimal("0")))
            calculation = calculate_suggested_order(
                forecast_qty=forecast,
                safety_stock_percent=safety_percent,
                safety_stock_qty=fixed_safety,
                store_on_hand=on_hand,
                confirmed_incoming=incoming,
                pack_size=pack_size,
                minimum_order_qty=minimum_order,
            )
            lines.append(
                {
                    "product_id": str(product.id),
                    "sku": product.sku,
                    "product_name": product.name,
                    "unit": product.unit.code if product.unit else "ชิ้น",
                    "inventory_role": product.inventory_role,
                    "store_on_hand_qty": float(on_hand),
                    "received_today_qty": float(q4(received_today_by_product.get(product.id, 0))),
                    "yesterday_usage_qty": float(yesterday_usage),
                    "average_7_day_qty": float(average_7),
                    "forecast_qty": float(forecast),
                    "confirmed_incoming_qty": float(incoming),
                    "safety_stock_percent": float(q4(safety_percent)),
                    "fixed_safety_stock_qty": float(q4(fixed_safety)),
                    "safety_stock_qty": float(calculation["safety_stock_qty"]),
                    "target_qty": float(calculation["target_qty"]),
                    "raw_suggested_qty": float(calculation["raw_suggested_qty"]),
                    "suggested_qty": float(calculation["suggested_qty"]),
                    "pack_size": float(q4(pack_size)),
                    "minimum_order_qty": float(q4(minimum_order)),
                    "lead_time_days": lead_time_days,
                    "target_date": (business_date + timedelta(days=lead_time_days)).isoformat(),
                    "configured_forecast_method": configured_method,
                    "forecast_method": effective_method,
                    "open_day_count": len(open_dates),
                    "policy_id": str(policy.id) if policy else None,
                    "is_enabled": policy.is_enabled if policy else True,
                    "uses_default_policy": policy is None,
                    "source": f"replenishment_{effective_method}",
                }
            )

        return {
            "date": selected_date,
            "default_target_date": (business_date + timedelta(days=1)).isoformat(),
            "brand_id": str(brand_id),
            "branch_id": str(branch_id),
            "location_id": str(location_id),
            "open_business_dates": open_dates,
            "formula": "forecast + safety_stock - store_on_hand - confirmed_incoming",
            "items": lines,
        }

    @staticmethod
    def _empty_summary(
        brand_id: uuid.UUID,
        branch_id: uuid.UUID,
        location_id: uuid.UUID,
        business_date: date,
    ) -> dict:
        return {
            "date": business_date.isoformat(),
            "default_target_date": (business_date + timedelta(days=1)).isoformat(),
            "brand_id": str(brand_id),
            "branch_id": str(branch_id),
            "location_id": str(location_id),
            "open_business_dates": [],
            "formula": "forecast + safety_stock - store_on_hand - confirmed_incoming",
            "items": [],
        }


def serialize_replenishment_policy(policy: BranchReplenishmentPolicy) -> dict:
    return {
        "id": str(policy.id),
        "company_id": str(policy.company_id),
        "brand_id": str(policy.brand_id),
        "branch_id": str(policy.branch_id),
        "product_id": str(policy.product_id),
        "is_enabled": policy.is_enabled,
        "safety_stock_percent": float(q4(policy.safety_stock_percent)),
        "safety_stock_qty": float(q4(policy.safety_stock_qty)),
        "pack_size": float(q4(policy.pack_size)),
        "lead_time_days": policy.lead_time_days,
        "forecast_method": policy.forecast_method,
        "minimum_order_qty": float(q4(policy.minimum_order_qty)),
    }
