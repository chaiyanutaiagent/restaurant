"""Signed, least-privilege Takeaway Store session boundary (web roles unchanged)."""
from __future__ import annotations

import re

from fastapi import HTTPException

from app.config import settings
from app.utils.uat_host_policy import resolve_uat_public_host

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
    ("POST", r"/api/v1/takeaway/counter/orders/[0-9a-f-]+/(accept|handoff)"),
    ("GET", r"/api/v1/takeaway/store/central-orders"),
    ("POST", r"/api/v1/takeaway/store/central-orders/[0-9a-f-]+/(receive|receive-quantities)"),
    ("POST", r"/api/v1/takeaway/transfers/[0-9a-f-]+/receive"),
    ("GET", r"/api/v1/takeaway/credit/(accounts|topups|payment-config)"),
    ("GET", r"/api/v1/takeaway/credit/accounts/[0-9a-f-]+/entries"),
    ("POST", r"/api/v1/takeaway/credit/accounts/[0-9a-f-]+/topups"),
)


def uat_superadmin_store_access(user) -> bool:
    """Allow the named tenant superadmin into Store only on the explicit UAT gate."""
    configured_username = (settings.uat_superadmin_username or "").strip().lower()
    try:
        resolve_uat_public_host(settings.saas_public_base_url)
    except ValueError:
        return False
    return bool(
        settings.uat_superadmin_all_logins_enabled
        and settings.environment == "development"
        and bool(configured_username)
        and getattr(user, "is_superuser", False)
        and settings.uat_superadmin_company_id is not None
        and getattr(user, "company_id", None) == settings.uat_superadmin_company_id
        and getattr(user, "username", "").strip().lower() == configured_username
    )


def store_permissions(*, user, context, permissions: list[str], device_id: str | None) -> list[str]:
    uat_superadmin = uat_superadmin_store_access(user)
    if ((user.is_superuser and not uat_superadmin)
            or ("*" in permissions and not uat_superadmin) or not context
            or context.business_type != "takeaway" or context.target_database != "takeaway"
            or not context.branch_id or not device_id):
        raise HTTPException(403, "A non-superuser Takeaway branch assignment is required")
    allowed = sorted(STORE_PERMISSIONS if uat_superadmin else STORE_PERMISSIONS.intersection(permissions))
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
