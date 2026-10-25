from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP


QUANTITY = Decimal("0.0001")
REORDER_REMAINING_RATIO = Decimal("0.30")


def target_replenishment_state(*, target_stock_qty: Decimal | None,
        on_hand_qty: Decimal, confirmed_incoming_qty: Decimal = Decimal("0"),
        pack_size: Decimal = Decimal("1"), minimum_order_qty: Decimal = Decimal("0")) -> dict:
    """Alert at <=30% of a fixed target; incoming reduces the order, not the alert."""
    target = Decimal(target_stock_qty) if target_stock_qty is not None else None
    configured = target is not None and target > 0
    threshold = target * REORDER_REMAINING_RATIO if configured else None
    low = bool(configured and Decimal(on_hand_qty) <= threshold)
    suggested = Decimal("0.0000")
    if low:
        shortage = max(target - Decimal(on_hand_qty) - max(Decimal(confirmed_incoming_qty), Decimal("0")), Decimal("0"))
        if shortage > 0:
            pack = Decimal(pack_size)
            if pack <= 0:
                raise ValueError("pack size must be greater than zero")
            suggested = ((max(shortage, Decimal(minimum_order_qty)) / pack)
                         .to_integral_value(rounding=ROUND_CEILING) * pack).quantize(QUANTITY)
    return {"target_stock_qty": target, "reorder_threshold_qty": threshold,
            "target_configured": configured, "is_low_stock": low, "suggested_qty": suggested}

_UNIT_FAMILY: dict[str, tuple[str, Decimal]] = {
    "mg": ("weight", Decimal("0.001")),
    "g": ("weight", Decimal("1")),
    "kg": ("weight", Decimal("1000")),
    "ml": ("volume", Decimal("1")),
    "l": ("volume", Decimal("1000")),
    "ชิ้น": ("count", Decimal("1")),
    "piece": ("count", Decimal("1")),
}


def convert_quantity(quantity: Decimal, from_unit: str, to_unit: str) -> Decimal:
    source = _UNIT_FAMILY.get(from_unit.strip().lower())
    target = _UNIT_FAMILY.get(to_unit.strip().lower())
    if source is None or target is None or source[0] != target[0]:
        raise ValueError(f"incompatible Takeaway units: {from_unit} -> {to_unit}")
    return (Decimal(quantity) * source[1] / target[1]).quantize(QUANTITY, rounding=ROUND_HALF_UP)


def recipe_cost_per_yield(
    ingredient_cost: Decimal,
    yield_qty: Decimal,
    loss_percent: Decimal,
) -> Decimal:
    usable_yield = Decimal(yield_qty) * (Decimal("1") - Decimal(loss_percent) / Decimal("100"))
    if usable_yield <= 0:
        raise ValueError("recipe usable yield must be greater than zero")
    return (Decimal(ingredient_cost) / usable_yield).quantize(QUANTITY, rounding=ROUND_HALF_UP)


def suggested_replenishment_quantity(
    *,
    average_daily_demand: Decimal,
    lead_time_days: int,
    safety_stock_percent: Decimal,
    safety_stock_qty: Decimal,
    on_hand_qty: Decimal,
    confirmed_incoming_qty: Decimal,
    pack_size: Decimal,
    minimum_order_qty: Decimal,
) -> Decimal:
    lead_demand = Decimal(average_daily_demand) * Decimal(max(lead_time_days, 1))
    safety = max(
        Decimal(safety_stock_qty),
        lead_demand * Decimal(safety_stock_percent) / Decimal("100"),
    )
    shortage = lead_demand + safety - Decimal(on_hand_qty) - Decimal(confirmed_incoming_qty)
    if shortage <= 0:
        return Decimal("0.0000")
    raw = max(shortage, Decimal(minimum_order_qty))
    pack = Decimal(pack_size)
    if pack <= 0:
        raise ValueError("pack size must be greater than zero")
    packs = (raw / pack).to_integral_value(rounding=ROUND_CEILING)
    return (packs * pack).quantize(QUANTITY, rounding=ROUND_HALF_UP)
