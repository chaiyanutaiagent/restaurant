from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any
import uuid

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import TokenData, get_legacy_model_operational_db as get_db, require_permission
from app.models.product import Product
from app.schemas.product import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    PriceListCreate,
    PriceListItemCreate,
    PriceListItemRead,
    PriceListRead,
    ProductCreate,
    ProductListItem,
    ProductRead,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantRead,
    ProductVariantUpdate,
    UnitCreate,
    UnitRead,
    UnitUpdate,
)
from app.services.product_service import ProductService
from app.services.upload_service import UploadService

router = APIRouter(prefix="/api/v1", tags=["products"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


def serialize_category(category: Any, include_children: bool = False) -> dict[str, Any]:
    return {
        "id": category.id,
        "company_id": category.company_id,
        "code": category.code,
        "name": category.name,
        "name_en": category.name_en,
        "parent_id": category.parent_id,
        "sort_order": category.sort_order,
        "is_active": category.is_active,
        "image_url": category.image_url,
        "created_at": category.created_at,
        "children": [serialize_category(child, True) for child in getattr(category, "children", [])] if include_children else [],
    }


@router.get("/units")
async def list_units(
    current: TokenData = Depends(require_permission("inventory.product.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ProductService(db)
    units = await service.list_units(current.company_id)
    return ok([UnitRead.model_validate(unit).model_dump() for unit in units])


@router.post("/units", status_code=status.HTTP_201_CREATED)
async def create_unit(
    payload: UnitCreate,
    current: TokenData = Depends(require_permission("inventory.product.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ProductService(db)
    unit = await service.create_unit(current.company_id, payload)
    return ok(UnitRead.model_validate(unit).model_dump())


@router.patch("/units/{unit_id}")
async def update_unit(
    unit_id: uuid.UUID,
    payload: UnitUpdate,
    current: TokenData = Depends(require_permission("inventory.product.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ProductService(db)
    unit = await service.update_unit(unit_id, current.company_id, payload)
    return ok(UnitRead.model_validate(unit).model_dump())


@router.delete("/units/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_unit(
    unit_id: uuid.UUID,
    current: TokenData = Depends(require_permission("inventory.product.delete")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = ProductService(db)
    await service.delete_unit(unit_id, current.company_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/categories")
async def list_categories(
    tree: bool = Query(default=False),
    current: TokenData = Depends(require_permission("inventory.product.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ProductService(db)
    categories = await service.list_categories(current.company_id, tree=tree)
    return ok([serialize_category(category, include_children=tree) for category in categories])


@router.post("/categories", status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    current: TokenData = Depends(require_permission("inventory.product.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ProductService(db)
    category = await service.create_category(current.company_id, payload)
    return ok(serialize_category(category))


@router.post("/categories/{cat_id}/image")
async def upload_category_image(
    cat_id: uuid.UUID,
    file: UploadFile = File(...),
    current: TokenData = Depends(require_permission("inventory.product.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ProductService(db)
    category = await service._get_category(cat_id, current.company_id)
    uploader = UploadService()
    if category.image_url:
        await uploader.delete_image(category.image_url)
    category.image_url = await uploader.save_image(file, "categories", str(current.company_id))
    await db.commit()
    await db.refresh(category)
    return ok(serialize_category(category))


@router.patch("/categories/{cat_id}")
async def update_category(
    cat_id: uuid.UUID,
    payload: CategoryUpdate,
    current: TokenData = Depends(require_permission("inventory.product.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ProductService(db)
    category = await service.update_category(cat_id, current.company_id, payload)
    return ok(serialize_category(category))


@router.delete("/categories/{cat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    cat_id: uuid.UUID,
    current: TokenData = Depends(require_permission("inventory.product.delete")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = ProductService(db)
    await service.delete_category(cat_id, current.company_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/products")
async def list_products(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    category_id: uuid.UUID | None = Query(default=None),
    product_type: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    current: TokenData = Depends(require_permission("inventory.product.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ProductService(db)
    products, total = await service.list_products(
        current.company_id,
        page=page,
        limit=limit,
        search=search,
        category_id=category_id,
        product_type=product_type,
        is_active=is_active,
    )
    data = [ProductListItem.model_validate(product).model_dump() for product in products]
    return ok(data, meta={"total": total, "page": page, "limit": limit})


@router.get("/products/{product_id}")
async def get_product(
    product_id: uuid.UUID,
    current: TokenData = Depends(require_permission("inventory.product.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ProductService(db)
    product = await service.get_product(product_id, current.company_id)
    return ok(ProductRead.model_validate(product).model_dump())


@router.post("/products", status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    current: TokenData = Depends(require_permission("inventory.product.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ProductService(db)
    product = await service.create_product(current.company_id, payload)
    return ok(ProductRead.model_validate(product).model_dump())


@router.post("/products/{product_id}/image")
async def upload_product_image(
    product_id: uuid.UUID,
    file: UploadFile = File(...),
    is_primary: bool = Form(default=True),
    current: TokenData = Depends(require_permission("inventory.product.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ProductService(db)
    uploader = UploadService()
    url = await uploader.save_image(file, "products", str(current.company_id))
    await service.add_product_image(
        product_id=product_id,
        company_id=current.company_id,
        url=url,
        filename=Path(file.filename or url).name,
        is_primary=is_primary,
    )
    product = await service.get_product(product_id, current.company_id)
    return ok(ProductRead.model_validate(product).model_dump())


@router.delete("/products/{product_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_image(
    product_id: uuid.UUID,
    image_id: uuid.UUID,
    current: TokenData = Depends(require_permission("inventory.product.edit")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = ProductService(db)
    uploader = UploadService()
    image = await service.delete_product_image(product_id, image_id, current.company_id)
    await uploader.delete_image(image.url)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/products/{product_id}/images/{image_id}/primary")
async def set_primary_product_image(
    product_id: uuid.UUID,
    image_id: uuid.UUID,
    current: TokenData = Depends(require_permission("inventory.product.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ProductService(db)
    await service.set_primary_image(product_id, image_id, current.company_id)
    product = await service.get_product(product_id, current.company_id)
    return ok(ProductRead.model_validate(product).model_dump())


@router.patch("/products/{product_id}")
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    current: TokenData = Depends(require_permission("inventory.product.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ProductService(db)
    product = await service.update_product(product_id, current.company_id, payload)
    return ok(ProductRead.model_validate(product).model_dump())


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    current: TokenData = Depends(require_permission("inventory.product.delete")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = ProductService(db)
    await service.delete_product(product_id, current.company_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/products/{product_id}/variants", status_code=status.HTTP_201_CREATED)
async def add_variant(
    product_id: uuid.UUID,
    payload: ProductVariantCreate,
    current: TokenData = Depends(require_permission("inventory.product.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ProductService(db)
    variant = await service.add_variant(
        product_id,
        current.company_id,
        payload.model_copy(update={"product_id": product_id}),
    )
    return ok(ProductVariantRead.model_validate(variant).model_dump())


@router.patch("/products/{product_id}/variants/{variant_id}")
async def update_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    payload: ProductVariantUpdate,
    current: TokenData = Depends(require_permission("inventory.product.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    del product_id
    service = ProductService(db)
    variant = await service.update_variant(variant_id, current.company_id, payload)
    return ok(ProductVariantRead.model_validate(variant).model_dump())


@router.delete("/products/{product_id}/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    current: TokenData = Depends(require_permission("inventory.product.delete")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    del product_id
    service = ProductService(db)
    await service.delete_variant(variant_id, current.company_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/price-lists")
async def list_price_lists(
    current: TokenData = Depends(require_permission("inventory.product.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ProductService(db)
    price_lists = await service.list_price_lists(current.company_id)
    return ok([PriceListRead.model_validate(item).model_dump() for item in price_lists])


@router.post("/price-lists", status_code=status.HTTP_201_CREATED)
async def create_price_list(
    payload: PriceListCreate,
    current: TokenData = Depends(require_permission("inventory.product.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ProductService(db)
    price_list = await service.create_price_list(current.company_id, payload)
    return ok(PriceListRead.model_validate(price_list).model_dump())


@router.post("/price-lists/{price_list_id}/items")
async def set_price_list_item(
    price_list_id: uuid.UUID,
    payload: PriceListItemCreate,
    current: TokenData = Depends(require_permission("inventory.product.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ProductService(db)
    item = await service.set_price(current.company_id, payload.model_copy(update={"price_list_id": price_list_id}))
    return ok(PriceListItemRead.model_validate(item).model_dump())


@router.get("/products/{product_id}/price")
async def get_product_price(
    product_id: uuid.UUID,
    price_list_id: uuid.UUID | None = Query(default=None),
    variant_id: uuid.UUID | None = Query(default=None),
    qty: Decimal = Query(default=Decimal("1")),
    x_company_id: str | None = Header(default=None, alias="X-Company-ID"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ProductService(db)
    product = await db.scalar(select(Product).where(Product.id == product_id, Product.deleted_at.is_(None)))
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    company_id = uuid.UUID(x_company_id) if x_company_id else product.company_id
    price = await service.get_product_price(product_id, company_id, price_list_id, variant_id, qty)
    vat_rate = Decimal(product.vat_rate)
    if product.vat_type == "included":
        vat_amount = (price * vat_rate / (Decimal("100") + vat_rate)).quantize(Decimal("0.01"))
        total = price
    elif product.vat_type == "excluded":
        vat_amount = (price * vat_rate / Decimal("100")).quantize(Decimal("0.01"))
        total = (price + vat_amount).quantize(Decimal("0.01"))
    else:
        vat_amount = Decimal("0.00")
        total = price
    return ok(
        {
            "price": price,
            "vat_amount": vat_amount,
            "total": total,
        }
    )
