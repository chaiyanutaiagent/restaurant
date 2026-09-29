"""Signed, least-privilege Takeaway Store session boundary (web roles unchanged)."""
from __future__ import annotations

import re
from fastapi import HTTPException

MOBILE_STORE_SURFACE = "takeaway_store"
STORE_PERMISSIONS = frozenset({
    "takeaway.store.access",
    "takeaway.catalog.view", "takeaway.sale.view", "takeaway.sale.create",
    "takeaway.shift.manage", "takeaway.pickup.manage", "takeaway.kitchen.manage",
    "takeaway.stock.view", "takeaway.stock.manage", "takeaway.central_order.create",
    "takeaway.transfer.manage", "takeaway.credit.manage",
})
STORE_ENTRY_PERMISSIONS = frozenset({
    "takeaway.sale.create", "takeaway.central_order.create", "takeaway.stock.view",
})

# Explicit methods and full paths: central approvals, credit adjustments, user
# administration and switching to a broader web session are never included.
STORE_API_ROUTES = (
    ("GET", r"/api/v1/auth/me"),
    ("GET", r"/api/v1/takeaway/(status|catalog/categories|catalog/items|shifts|orders|stock|stock/locations|stock/movements|store/transfers)"),
    ("GET", r"/api/v1/takeaway/shifts/[0-9a-f-]+/summary"),
    ("GET", r"/api/v1/takeaway/orders/[0-9a-f-]+/receipt"),
    ("POST", r"/api/v1/takeaway/(sales|sales/offline-sync|shifts/open|ordering-links|stock/movements|store/central-orders)"),
    ("POST", r"/api/v1/takeaway/shifts/[0-9a-f-]+/close"),
    ("POST", r"/api/v1/takeaway/orders/[0-9a-f-]+/(capture-payment|picked-up|receipt/prints)"),
    ("POST", r"/api/v1/takeaway/fulfillment/orders/[0-9a-f-]+/(preparing|ready)"),
    ("GET", r"/api/v1/takeaway/store/central-orders"),
    ("POST", r"/api/v1/takeaway/store/central-orders/[0-9a-f-]+/(receive|receive-quantities)"),
    ("POST", r"/api/v1/takeaway/transfers/[0-9a-f-]+/receive"),
    ("GET", r"/api/v1/takeaway/credit/(accounts|topups|payment-config)"),
    ("GET", r"/api/v1/takeaway/credit/accounts/[0-9a-f-]+/entries"),
    ("POST", r"/api/v1/takeaway/credit/accounts/[0-9a-f-]+/topups"),
)


def store_permissions(*, user, context, permissions: list[str], device_id: str | None) -> list[str]:
    if (user.is_superuser or "*" in permissions or not context
            or context.business_type != "takeaway" or context.target_database != "takeaway"
            or not context.branch_id or not device_id):
        raise HTTPException(403, "A non-superuser Takeaway branch assignment is required")
    allowed = sorted(STORE_PERMISSIONS.intersection(permissions))
    if "takeaway.store.access" not in allowed or not STORE_ENTRY_PERMISSIONS.intersection(allowed):
        raise HTTPException(403, "No Takeaway Store role is assigned")
    return allowed


def enforce_store_request(payload: dict, method: str, path: str, headers) -> None:
    if payload.get("client_surface") != MOBILE_STORE_SURFACE:
        return
    if not any(method == verb and re.fullmatch(pattern, path) for verb, pattern in STORE_API_ROUTES):
        raise HTTPException(403, "This endpoint is outside the Takeaway Store surface")
    for header, claim in (("x-company-id", "company_id"), ("x-branch-id", "branch_id"), ("x-store-device-id", "store_device_id")):
        if not payload.get(claim) or headers.get(header) != str(payload[claim]):
            raise HTTPException(403, "Takeaway Store context does not match the signed session")
