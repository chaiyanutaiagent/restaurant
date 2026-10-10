"""Store sales are an explicit projection, not the central supply inventory."""
from decimal import Decimal, InvalidOperation

SALE_KINDS = frozenset({"menu_item", "finished_goods", "finished_good", "finished", "fg"})


def sale_eligible(metadata: dict | None, price: object, *, active: bool, assigned: bool) -> bool:
    meta = metadata or {}
    kind = str(meta.get("item_kind") or meta.get("product_type") or "").lower()
    if not active or not assigned or meta.get("is_for_sale") is not True:
        return False
    if kind not in SALE_KINDS or meta.get("central_only") is True:
        return False
    if meta.get("inventory_role") in {"central_raw", "central_only"} or meta.get("brand_scope") == "central":
        return False
    try:
        amount = Decimal(str(price))
        return amount.is_finite() and amount > 0
    except (InvalidOperation, ValueError, TypeError):
        return False
