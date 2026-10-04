"""Native POS sessions may operate one signed branch and product, never ERP admin."""
from __future__ import annotations

import re
from fastapi import HTTPException

POS_SURFACES = {"restaurant_pos": "restaurant", "retail_pos": "retail_pos"}
COMMON_PERMISSIONS = frozenset({
    "pos.sale.view", "pos.sale.create", "pos.sale.void", "pos.sale.void.request",
    "pos.discount.apply", "pos.discount.override", "pos.price.override", "pos.price.override.request",
    "pos.draft.view", "pos.draft.create", "pos.draft.update", "pos.draft.resume", "pos.draft.discard", "pos.draft.reassign",
    "pos.refund.create", "pos.refund.request", "pos.cashier.open_shift", "pos.cashier.close_shift", "pos.cashier.handover",
    "pos.cash_movement.create", "pos.cash_movement.approve", "pos.shift.variance.approve",
    "inventory.product.view", "inventory.stock.view",
})
RESTAURANT_PERMISSIONS = frozenset({
    "fb.menu.view", "fb.order.create", "fb.order.cancel", "fb.order.cancel.request", "fb.order.cancel.approve",
    "fb.order.cancel.reopen.request", "fb.order.cancel.reopen", "fb.kitchen.manage", "fb.kitchen.ticket.manage", "fb.table.manage",
})
_ID = r"[0-9a-f-]+"
COMMON_ROUTES = (
    ("GET", r"/api/v1/(auth/me|mobile-pos/context|categories|units|products|stock/locations|stock/balances|stock/low-stock)"),
    ("GET", rf"/api/v1/products/{_ID}(/price)?"),
    ("GET", r"/api/v1/products/retail/lookup"),
    ("GET", r"/api/v1/mobile-pos/customers/search"),
    ("GET", rf"/api/v1/system/branches/{_ID}/(settings|replacement-rules)"),
    ("GET", r"/api/v1/pos/(shifts|shifts/current|sales|drafts|refunds|promptpay/qr)"),
    ("GET", rf"/api/v1/pos/shifts/{_ID}/summary"),
    ("GET", rf"/api/v1/pos/(sales|refunds)/{_ID}"),
    ("GET", rf"/api/v1/pos/drafts/{_ID}(/audit)?"),
    ("POST", r"/api/v1/pos/(shifts/open|sales|sales/sync|pricing/calculate|drafts|refunds|refunds/quotes)"),
    ("POST", rf"/api/v1/pos/shifts/{_ID}/(close|handover|cash-movements)"),
    ("PATCH", rf"/api/v1/pos/drafts/{_ID}"),
    ("POST", rf"/api/v1/pos/drafts/{_ID}/(claim|resume|release|discard|reopen)"),
    ("POST", rf"/api/v1/pos/sales/{_ID}/void"),
    ("POST", rf"/api/v1/pos/refunds/{_ID}/(cash-confirm|inquire|retry)"),
    ("POST", r"/api/v1/approvals/sessions"),
    ("GET", r"/api/v1/crm/(settings|tiers|tags|customers)"),
    ("GET", rf"/api/v1/crm/customers/{_ID}(/(history|points))?"),
    ("POST", r"/api/v1/crm/(customers|points/redeem)"),
    ("PATCH", rf"/api/v1/crm/customers/{_ID}"),
)
RESTAURANT_ROUTES = (
    ("GET", r"/api/v1/restaurant/(tables|sessions|kitchen|kitchen-cancellation-events|pickup-queue|settings|wap/menu|cancellations)"),
    ("GET", rf"/api/v1/restaurant/(tables|sessions)/{_ID}(/(detail|payment-qr))?"),
    ("POST", r"/api/v1/restaurant/(tables|sessions|cancellations|cancellations/preview|wap/orders|wap/orders/sync|qs-qr/generate)"),
    ("GET", rf"/api/v1/restaurant/offline-sync/{_ID}"),
    ("POST", rf"/api/v1/restaurant/sessions/{_ID}/(orders|bill|checkout|close)"),
    ("PATCH", rf"/api/v1/restaurant/(tables/{_ID}|kitchen/{_ID}|order-items/{_ID}/status)"),
    ("DELETE", rf"/api/v1/restaurant/tables/{_ID}"),
    ("POST", rf"/api/v1/restaurant/(cancellations/{_ID}/reopen|kitchen-cancellation-events/{_ID}/acknowledge|pickup-queue/{_ID}/served)"),
    ("GET", rf"/api/v1/restaurant/wap/orders/{_ID}"),
    ("POST", rf"/api/v1/restaurant/wap/orders/{_ID}/(customer-slip|kitchen-slip)"),
)


def pos_permissions(*, surface, user, context, permissions, device_id):
    product = POS_SURFACES.get(surface)
    if (not product or user.is_superuser or "*" in permissions or not context or not device_id
            or not context.branch_id or context.business_type != product or context.target_database != product):
        raise HTTPException(403, "A named employee assigned to this POS product and branch is required")
    allow = COMMON_PERMISSIONS | (RESTAURANT_PERMISSIONS if product == "restaurant" else frozenset())
    result = sorted(allow.intersection(permissions))
    entry = {"pos.sale.create", "pos.sale.view"} | ({"fb.order.create", "fb.kitchen.manage", "fb.kitchen.ticket.manage", "fb.table.manage"} if product == "restaurant" else set())
    if not entry.intersection(result):
        raise HTTPException(403, "No POS role is assigned to this branch")
    return result


def enforce_pos_request(payload, request, context):
    product = POS_SURFACES[payload["client_surface"]]
    for claim in ("brand_id", "business_type", "target_database"):
        if str(payload.get(claim)) != str(getattr(context, claim)):
            raise HTTPException(403, "POS assignment changed; sign in again")
    for header, claim in (("x-company-id", "company_id"), ("x-branch-id", "branch_id"), ("x-store-device-id", "store_device_id")):
        if not payload.get(claim) or request.headers.get(header) != str(payload[claim]):
            raise HTTPException(403, "POS context does not match the signed session")
    for name in ("company_id", "branch_id", "brand_id"):
        values = request.query_params.getlist(name)
        if any(value != str(payload.get(name)) for value in values):
            raise HTTPException(403, "Cross-context POS query denied")
    path = request.url.path
    if path == "/api/v1/products":
        expected = "restaurant_menu" if product == "restaurant" else "retail_sale"
        if request.query_params.getlist("catalog_scope") != [expected]:
            raise HTTPException(403, "POS product catalog scope is required")
    branch_path = re.fullmatch(rf"/api/v1/system/branches/({_ID})/(settings|replacement-rules)", path)
    if branch_path and branch_path[1] != str(payload["branch_id"]):
        raise HTTPException(403, "Other branch settings denied")
    rules = COMMON_ROUTES + (RESTAURANT_ROUTES if product == "restaurant" else ())
    if not any(request.method == method and re.fullmatch(pattern, path) for method, pattern in rules):
        raise HTTPException(403, "This endpoint is outside the native POS surface")
