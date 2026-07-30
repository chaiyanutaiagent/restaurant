from __future__ import annotations

from datetime import datetime, timezone
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
from app.models.product import Product
from app.schemas.api_integration import (
    APIKeyCreate,
    APIKeyCreatedResponse,
    APIKeyRead,
    ExternalOrderRead,
    WebhookDeliveryRead,
    WebhookEndpointCreate,
    WebhookEndpointRead,
)
from app.schemas.pos import CartItem, CreateSaleRequest
from app.services.sale_service import SaleService
from app.utils.api_key_auth import generate_api_key
from app.utils.webhook_dispatcher import dispatch_webhook

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


class WebhookEndpointUpdate(BaseModel):
    is_active: bool | None = None
    events: list[str] | None = None


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
    full_key, key_prefix, key_hash = generate_api_key()
    row = APIKey(
        company_id=current.company_id,
        name=payload.name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        scopes=payload.scopes,
        expires_at=payload.expires_at,
        created_by=current.user_id,
    )
    db.add(row)
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
    await db.commit()
    await db.refresh(row)
    return ok(APIKeyRead.model_validate(row).model_dump(mode="json"))


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
    row = WebhookEndpoint(company_id=current.company_id, **payload.model_dump())
    db.add(row)
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
    return ok({"status": "sent", "response_status": delivery.response_status})


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
        unit_price = Decimal(str(raw_item.get("unit_price", product.selling_price)))
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
            paid_amount=order.total_amount,
            customer_name=order.customer_name,
            customer_phone=order.customer_phone,
            note=order.notes,
            client_order_id=f"external:{order.source}:{order.external_order_id}",
        ),
    )
    order.sale_order_id = sale.id
    order.status = "fulfilled"
    order.processed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(order)
    return ok(ExternalOrderRead.model_validate(order).model_dump(mode="json"))
