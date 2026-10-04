from __future__ import annotations

from decimal import Decimal
import re
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.api_integration import APIKey, ExternalOrder
from app.models.product import Product
from app.models.stock import StockBalance
from app.schemas.api_integration import ExternalOrderRead, PublicOrderCreate, PublicProductRead, PublicStockLocationRead, PublicStockRead
from app.services.external_order_validation_service import validate_external_order
from app.utils.api_key_auth import require_scope
from app.utils.rate_limiter import is_webhook_rate_limited
from app.utils.webhook_dispatcher import trigger_event

router = APIRouter(prefix="/api/public/v1", tags=["public-api"])
SOURCE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,48}[a-z0-9]$")


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


def normalize_source(source: str) -> str:
    value = source.strip().lower()
    if not SOURCE_PATTERN.fullmatch(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source must be 3-50 chars using lowercase letters, numbers, underscores, or hyphens",
        )
    return value


def serialize_product(product: Product) -> dict[str, Any]:
    return PublicProductRead(
        id=product.id,
        sku=product.sku,
        barcode=product.barcode,
        name=product.name,
        name_en=product.name_en,
        description=product.description,
        selling_price=product.selling_price,
        vat_type=product.vat_type,
        vat_rate=product.vat_rate,
        category_id=product.category_id,
        category_name=product.category.name if product.category else None,
        unit_code=product.unit.code if product.unit else None,
        image_url=product.image_url,
        is_active=product.is_active,
    ).model_dump(mode="json")


@router.get("/products")
async def list_products(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    search: str | None = Query(default=None),
    category_id: uuid.UUID | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    api_key: APIKey = Depends(require_scope("products:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    filters = [Product.company_id == api_key.company_id, Product.deleted_at.is_(None)]
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                Product.sku.ilike(pattern),
                Product.barcode.ilike(pattern),
                Product.name.ilike(pattern),
                Product.name_en.ilike(pattern),
            )
        )
    if category_id is not None:
        filters.append(Product.category_id == category_id)
    if is_active is not None:
        filters.append(Product.is_active.is_(is_active))

    total = int((await db.scalar(select(func.count(Product.id)).where(*filters))) or 0)
    rows = (
        await db.scalars(
            select(Product)
            .where(*filters)
            .options(selectinload(Product.category), selectinload(Product.unit))
            .order_by(Product.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).all()
    return ok([serialize_product(row) for row in rows], meta={"total": total, "page": page, "limit": limit})


@router.get("/products/{sku}")
async def get_product(
    sku: str,
    api_key: APIKey = Depends(require_scope("products:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    product = await db.scalar(
        select(Product)
        .where(Product.company_id == api_key.company_id, Product.sku == sku, Product.deleted_at.is_(None))
        .options(selectinload(Product.category), selectinload(Product.unit))
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return ok(serialize_product(product))


@router.get("/stock/{sku}")
async def get_stock(
    sku: str,
    api_key: APIKey = Depends(require_scope("products:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    product = await db.scalar(
        select(Product)
        .where(Product.company_id == api_key.company_id, Product.sku == sku, Product.deleted_at.is_(None))
        .options(selectinload(Product.category), selectinload(Product.unit))
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    balances = (
        await db.scalars(
            select(StockBalance)
            .where(StockBalance.company_id == api_key.company_id, StockBalance.product_id == product.id)
            .options(selectinload(StockBalance.location), selectinload(StockBalance.branch))
        )
    ).all()
    locations: list[PublicStockLocationRead] = []
    total_qty_available = Decimal("0")
    for balance in balances:
        qty_available = Decimal(balance.qty_on_hand or 0) - Decimal(balance.qty_reserved or 0)
        total_qty_available += qty_available
        locations.append(
            PublicStockLocationRead(
                location_name=balance.location.name,
                branch_name=balance.branch.name,
                qty_available=qty_available,
            )
        )
    payload = PublicStockRead(
        product_id=product.id,
        sku=product.sku,
        name=product.name,
        total_qty_available=total_qty_available,
        locations=locations,
    )
    return ok(payload.model_dump(mode="json"))


@router.post("/orders", status_code=status.HTTP_201_CREATED)
async def create_external_order(
    payload: PublicOrderCreate,
    request: Request,
    source: str = Query(default="blifehealthy"),
    api_key: APIKey = Depends(require_scope("orders:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    source_value = normalize_source(source)
    source_ip = request.client.host if request.client else "unknown"
    is_limited, _remaining = await is_webhook_rate_limited(source_ip)
    if is_limited:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")

    existing = await db.scalar(
        select(ExternalOrder).where(
            ExternalOrder.company_id == api_key.company_id,
            ExternalOrder.source == source_value,
            ExternalOrder.external_order_id == payload.external_order_id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate external_order_id")

    items, server_total, review_reasons = await validate_external_order(db, api_key.company_id, payload)
    row = ExternalOrder(
        company_id=api_key.company_id,
        source=source_value,
        external_order_id=payload.external_order_id,
        status="needs_review" if review_reasons else "accepted",
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        customer_email=payload.customer_email,
        customer_address=payload.customer_address,
        items_json=items,
        total_amount=payload.total_amount,
        server_total_amount=server_total,
        review_reasons=review_reasons,
        payment_method=payload.payment_method,
        payment_status=payload.payment_status,
        notes=payload.notes,
        raw_payload=payload.model_dump(mode="json"),
    )
    db.add(row)
    await db.flush()
    try:
        await trigger_event(
            db,
            api_key.company_id,
            "order.received",
            {
                "external_order_id": row.external_order_id,
                "source": row.source,
                "total_amount": str(row.total_amount),
                "items_count": len(row.items_json),
            },
        )
    except Exception:
        pass
    await db.commit()
    return ok({"order_id": str(row.id), "status": row.status, "requires_review": bool(row.review_reasons)})


@router.get("/orders/{external_order_id}")
async def get_external_order(
    external_order_id: str,
    source: str = Query(default="blifehealthy"),
    api_key: APIKey = Depends(require_scope("orders:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    source_value = normalize_source(source)
    row = await db.scalar(
        select(ExternalOrder).where(
            ExternalOrder.company_id == api_key.company_id,
            ExternalOrder.source == source_value,
            ExternalOrder.external_order_id == external_order_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External order not found")
    return ok(ExternalOrderRead.model_validate(row).model_dump(mode="json"))
