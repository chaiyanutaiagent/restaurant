from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, require_permission
from app.models.api_integration import APIKey, ExternalOrder, WebhookDelivery, WebhookEndpoint
from app.models.audit import AuditLog
from app.models.product import Product
from app.schemas.api_integration import (
    APIKeyCreate,
    APIKeyCreatedResponse,
    APIKeyRead,
    APIKeyRotate,
    ExternalOrderReview,
    ExternalOrderRead,
    WebhookDeliveryRead,
    WebhookEndpointCreate,
    WebhookEndpointRead,
    WebhookSecretRotate,
)
from app.schemas.pos import CartItem, CreateSaleRequest
from app.services.sale_service import SaleService
from app.utils.api_key_auth import generate_api_key
from app.utils.integration_security import encrypt_integration_secret
from app.utils.webhook_dispatcher import dispatch_webhook

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])
ALLOWED_API_SCOPES = {"products:read", "orders:read", "orders:write"}


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


class WebhookEndpointUpdate(BaseModel):
    is_active: bool | None = None
    events: list[str] | None = None


def _validate_expiry(value: datetime) -> datetime:
    expiry = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if expiry <= now or expiry > now + timedelta(days=365):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Expiry must be within the next 365 days")
    return expiry


def _audit(current: TokenData, action: str, resource: str, resource_id: uuid.UUID, value: dict[str, Any]) -> AuditLog:
    return AuditLog(
        company_id=current.company_id,
        branch_id=current.branch_id,
        user_id=current.user_id,
        action=action,
        resource=resource,
        resource_id=str(resource_id),
        new_value=value,
    )


@router.get("/api-keys")
async def list_api_keys(
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = (
        await db.scalars(
            select(APIKey)
            .where(APIKey.company_id == current.company_id)
            .order_by(APIKey.created_at.desc())
        )
    ).all()
    return ok([APIKeyRead.model_validate(row).model_dump() for row in rows])


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: APIKeyCreate,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    unknown_scopes = sorted(set(payload.scopes) - ALLOWED_API_SCOPES)
    if unknown_scopes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unsupported scopes: {', '.join(unknown_scopes)}")
    full_key, key_prefix, key_hash = generate_api_key()
    row = APIKey(
        company_id=current.company_id,
        name=payload.name,
        purpose=payload.purpose,
        owner_contact=payload.owner_contact,
        key_prefix=key_prefix,
        key_hash=key_hash,
        scopes=payload.scopes,
        expires_at=_validate_expiry(payload.expires_at),
        created_by=current.user_id,
    )
    db.add(row)
    await db.flush()
    db.add(_audit(current, "integration.api_key.create", "APIKey", row.id, {"prefix": row.key_prefix, "purpose": row.purpose, "owner_contact": row.owner_contact, "scopes": row.scopes, "expires_at": row.expires_at.isoformat()}))
    await db.commit()
    await db.refresh(row)
    data = APIKeyCreatedResponse(key=APIKeyRead.model_validate(row), full_key=full_key)
    return ok(data.model_dump(mode="json"))


@router.post("/api-keys/{key_id}/revoke")
async def revoke_api_key(
    key_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await db.scalar(select(APIKey).where(APIKey.id == key_id, APIKey.company_id == current.company_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    row.is_active = False
    row.revoked_at = datetime.now(timezone.utc)
    row.revoked_by = current.user_id
    db.add(_audit(current, "integration.api_key.revoke", "APIKey", row.id, {"prefix": row.key_prefix}))
    await db.commit()
    await db.refresh(row)
    return ok(APIKeyRead.model_validate(row).model_dump(mode="json"))


@router.post("/api-keys/{key_id}/rotate", status_code=status.HTTP_201_CREATED)
async def rotate_api_key(
    key_id: uuid.UUID,
    payload: APIKeyRotate,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    old = await db.scalar(select(APIKey).where(APIKey.id == key_id, APIKey.company_id == current.company_id))
    if old is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    if not old.is_active or old.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only an active API key can be rotated")
    full_key, key_prefix, key_hash = generate_api_key()
    replacement = APIKey(
        company_id=current.company_id,
        name=old.name,
        purpose=old.purpose,
        owner_contact=old.owner_contact,
        key_prefix=key_prefix,
        key_hash=key_hash,
        scopes=list(old.scopes or []),
        expires_at=_validate_expiry(payload.expires_at),
        created_by=current.user_id,
        rotated_from_id=old.id,
    )
    db.add(replacement)
    await db.flush()
    old.is_active = False
    old.revoked_at = datetime.now(timezone.utc)
    old.revoked_by = current.user_id
    db.add(_audit(current, "integration.api_key.rotate", "APIKey", replacement.id, {"old_prefix": old.key_prefix, "new_prefix": replacement.key_prefix, "reason": payload.reason}))
    await db.commit()
    await db.refresh(replacement)
    return ok(APIKeyCreatedResponse(key=APIKeyRead.model_validate(replacement), full_key=full_key).model_dump(mode="json"))


@router.get("/webhooks")
async def list_webhooks(
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = (
        await db.scalars(
            select(WebhookEndpoint)
            .where(WebhookEndpoint.company_id == current.company_id)
            .order_by(WebhookEndpoint.created_at.desc())
        )
    ).all()
    return ok([WebhookEndpointRead.model_validate(row).model_dump() for row in rows])


@router.post("/webhooks", status_code=status.HTTP_201_CREATED)
async def create_webhook(
    payload: WebhookEndpointCreate,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if payload.incoming_source:
        existing = await db.scalar(
            select(WebhookEndpoint.id).where(
                WebhookEndpoint.incoming_source == payload.incoming_source,
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Incoming webhook source is already registered",
            )
    values = payload.model_dump(exclude={"secret"})
    row = WebhookEndpoint(
        company_id=current.company_id,
        **values,
        secret_ciphertext=encrypt_integration_secret(payload.secret),
        secret_rotated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()
    db.add(_audit(current, "integration.webhook.create", "WebhookEndpoint", row.id, {"name": row.name, "events": row.events, "incoming_source": row.incoming_source, "secret_configured": True}))
    await db.commit()
    await db.refresh(row)
    return ok(WebhookEndpointRead.model_validate(row).model_dump(mode="json"))


@router.post("/webhooks/{webhook_id}/rotate-secret")
async def rotate_webhook_secret(
    webhook_id: uuid.UUID,
    payload: WebhookSecretRotate,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id, WebhookEndpoint.company_id == current.company_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    row.secret_ciphertext = encrypt_integration_secret(payload.secret)
    row.secret_rotated_at = datetime.now(timezone.utc)
    row.failure_count = 0
    db.add(_audit(current, "integration.webhook.secret.rotate", "WebhookEndpoint", row.id, {"reason": payload.reason, "secret_rotated_at": row.secret_rotated_at.isoformat()}))
    await db.commit()
    await db.refresh(row)
    return ok(WebhookEndpointRead.model_validate(row).model_dump(mode="json"))


@router.patch("/webhooks/{webhook_id}")
async def update_webhook(
    webhook_id: uuid.UUID,
    payload: WebhookEndpointUpdate,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id, WebhookEndpoint.company_id == current.company_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return ok(WebhookEndpointRead.model_validate(row).model_dump(mode="json"))


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    row = await db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id, WebhookEndpoint.company_id == current.company_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    await db.delete(row)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/webhooks/{webhook_id}/deliveries")
async def list_deliveries(
    webhook_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    webhook = await db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id, WebhookEndpoint.company_id == current.company_id))
    if webhook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    rows = (
        await db.scalars(
            select(WebhookDelivery)
            .where(WebhookDelivery.webhook_id == webhook_id, WebhookDelivery.company_id == current.company_id)
            .order_by(WebhookDelivery.created_at.desc())
            .limit(50)
        )
    ).all()
    return ok([WebhookDeliveryRead.model_validate(row).model_dump(mode="json") for row in rows])


@router.post("/webhooks/{webhook_id}/test")
async def test_webhook(
    webhook_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    webhook = await db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id, WebhookEndpoint.company_id == current.company_id))
    if webhook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    payload = {"event": "test.ping", "timestamp": datetime.now(timezone.utc).isoformat()}
    delivery = WebhookDelivery(
        webhook_id=webhook.id,
        company_id=current.company_id,
        event_type="test.ping",
        payload=payload,
    )
    db.add(delivery)
    await db.flush()
    await dispatch_webhook(delivery, webhook, db)
    await db.commit()
    return ok({"status": delivery.status, "response_status": delivery.response_status, "delivery_id": str(delivery.id)})


@router.post("/webhook-deliveries/{delivery_id}/retry")
async def retry_webhook_delivery(
    delivery_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    delivery = await db.scalar(select(WebhookDelivery).where(WebhookDelivery.id == delivery_id, WebhookDelivery.company_id == current.company_id))
    if delivery is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")
    if delivery.status == "delivered":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Delivered webhook cannot be retried")
    webhook = await db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.id == delivery.webhook_id, WebhookEndpoint.company_id == current.company_id, WebhookEndpoint.is_active.is_(True)))
    if webhook is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Webhook endpoint is inactive or missing")
    await dispatch_webhook(delivery, webhook, db)
    db.add(_audit(current, "integration.webhook.delivery.retry", "WebhookDelivery", delivery.id, {"status": delivery.status, "attempt_count": delivery.attempt_count, "error_code": delivery.last_error_code}))
    await db.commit()
    await db.refresh(delivery)
    return ok(WebhookDeliveryRead.model_validate(delivery).model_dump(mode="json"))


@router.get("/external-orders")
async def list_external_orders(
    status_value: str | None = Query(default=None, alias="status"),
    source: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    filters = [ExternalOrder.company_id == current.company_id]
    if status_value:
        filters.append(ExternalOrder.status == status_value)
    if source:
        filters.append(ExternalOrder.source == source.strip().lower())
    total = int((await db.scalar(select(func.count(ExternalOrder.id)).where(*filters))) or 0)
    rows = (
        await db.scalars(
            select(ExternalOrder)
            .where(*filters)
            .order_by(ExternalOrder.received_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).all()
    return ok([ExternalOrderRead.model_validate(row).model_dump(mode="json") for row in rows], meta={"total": total, "page": page, "limit": limit})


async def _server_price_order(db: AsyncSession, order: ExternalOrder) -> tuple[list[dict[str, str]], Decimal | None, list[str]]:
    raw_items = order.items_json or []
    skus = list(dict.fromkeys(str(item.get("sku", "")).strip() for item in raw_items if item.get("sku")))
    products = list(
        (
            await db.scalars(
                select(Product).where(
                    Product.company_id == order.company_id,
                    Product.sku.in_(skus),
                    Product.deleted_at.is_(None),
                    Product.is_active.is_(True),
                    Product.is_for_sale.is_(True),
                )
            )
        ).all()
    )
    product_by_sku = {row.sku: row for row in products}
    normalized: list[dict[str, str]] = []
    reasons: list[str] = []
    total = Decimal("0")
    for index, item in enumerate(raw_items):
        sku = str(item.get("sku", "")).strip()
        product = product_by_sku.get(sku)
        if product is None:
            reasons.append(f"sku_not_found:{sku or index}")
            continue
        try:
            qty = Decimal(str(item.get("qty", "0")))
        except Exception:
            qty = Decimal("0")
        if qty <= 0:
            reasons.append(f"invalid_qty:{sku}")
            continue
        price = Decimal(str(product.selling_price)).quantize(Decimal("0.01"))
        line_total = (qty * price).quantize(Decimal("0.01"))
        total += line_total
        normalized.append({"sku": sku, "product_id": str(product.id), "qty": str(qty), "server_unit_price": str(price), "line_total": str(line_total)})
    if not raw_items:
        reasons.append("items_required")
    if (order.payment_status or "pending").strip().lower() not in {"paid", "pending", "unpaid", "cod"}:
        reasons.append("unsupported_payment_status")
    return normalized, total.quantize(Decimal("0.01")) if len(normalized) == len(raw_items) else None, reasons


@router.post("/external-orders/{order_id}/review")
async def review_external_order(
    order_id: uuid.UUID,
    payload: ExternalOrderReview,
    current: TokenData = Depends(require_permission("pos.sale.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await db.scalar(select(ExternalOrder).where(ExternalOrder.id == order_id, ExternalOrder.company_id == current.company_id))
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External order not found")
    if order.sale_order_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Fulfilled order cannot be reviewed")
    previous_reasons = list(order.review_reasons or [])
    if payload.decision == "reject":
        order.status = "rejected"
        order.review_reasons = [*previous_reasons, f"rejected:{payload.reason}"]
    else:
        items, server_total, blockers = await _server_price_order(db, order)
        if blockers or server_total is None:
            order.status = "needs_review"
            order.review_reasons = blockers
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"message": "Order mapping is not safe to accept", "reasons": blockers})
        order.items_json = items
        order.server_total_amount = server_total
        order.status = "accepted"
        order.review_reasons = []
    order.reviewed_at = datetime.now(timezone.utc)
    order.reviewed_by = current.user_id
    db.add(
        AuditLog(
            company_id=current.company_id,
            branch_id=current.branch_id,
            user_id=current.user_id,
            action=f"integration.external_order.{payload.decision}",
            resource="ExternalOrder",
            resource_id=str(order.id),
            old_value={"status": "needs_review", "review_reasons": previous_reasons},
            new_value={"status": order.status, "reason": payload.reason, "server_total_amount": str(order.server_total_amount) if order.server_total_amount is not None else None},
        )
    )
    await db.commit()
    await db.refresh(order)
    return ok(ExternalOrderRead.model_validate(order).model_dump(mode="json"))


@router.post("/external-orders/{order_id}/fulfill")
async def fulfill_external_order(
    order_id: uuid.UUID,
    current: TokenData = Depends(require_permission("pos.sale.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    order = await db.scalar(select(ExternalOrder).where(ExternalOrder.id == order_id, ExternalOrder.company_id == current.company_id))
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External order not found")
    if order.sale_order_id is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="External order already fulfilled")
    if order.status != "accepted":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="External order must be accepted before fulfillment")

    sale_service = SaleService(db)
    shift = await sale_service.get_open_shift(current.company_id, current.user_id, current.branch_id)
    if shift is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active shift required to fulfill order")

    items_payload = order.items_json or []
    if not items_payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="External order has no items")

    skus = [str(item.get("sku", "")).strip() for item in items_payload if item.get("sku")]
    products = (
        await db.scalars(
            select(Product).where(Product.company_id == current.company_id, Product.sku.in_(skus))
        )
    ).all()
    product_by_sku = {product.sku: product for product in products}
    cart_items: list[CartItem] = []
    for raw_item in items_payload:
        sku = str(raw_item.get("sku", "")).strip()
        product = product_by_sku.get(sku)
        if product is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Product not found for SKU: {sku}")
        unit_price = Decimal(str(product.selling_price)).quantize(Decimal("0.01"))
        qty = Decimal(str(raw_item.get("qty", 0)))
        cart_items.append(
            CartItem(
                product_id=product.id,
                qty=qty,
                unit_price=unit_price,
                original_price=unit_price,
                discount_amount=Decimal("0"),
                discount_type="amount",
                vat_type=product.vat_type,
                vat_rate=product.vat_rate,
            )
        )

    authoritative_total = sum((item.qty * item.unit_price for item in cart_items), Decimal("0")).quantize(Decimal("0.01"))
    if order.server_total_amount is None or Decimal(str(order.server_total_amount)).quantize(Decimal("0.01")) != authoritative_total:
        order.status = "needs_review"
        order.review_reasons = ["server_price_changed"]
        await db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Server price changed; review the order again")

    sale = await sale_service.create_sale(
        current.company_id,
        current.branch_id,
        current.user_id,
        CreateSaleRequest(
            shift_id=shift.id,
            location_id=shift.location_id,
            items=cart_items,
            discount_amount=Decimal("0"),
            discount_type="amount",
            payment_method=order.payment_method or "cash",
            paid_amount=authoritative_total,
            customer_name=order.customer_name,
            customer_phone=order.customer_phone,
            note=order.notes,
            client_order_id=f"external:{order.source}:{order.external_order_id}",
        ),
    )
    order.sale_order_id = sale.id
    order.status = "fulfilled"
    order.processed_at = datetime.now(timezone.utc)
    db.add(_audit(current, "integration.external_order.fulfill", "ExternalOrder", order.id, {"sale_order_id": str(sale.id), "server_total_amount": str(authoritative_total)}))
    await db.commit()
    await db.refresh(order)
    return ok(ExternalOrderRead.model_validate(order).model_dump(mode="json"))
