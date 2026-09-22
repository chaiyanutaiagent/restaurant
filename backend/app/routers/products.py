from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
import uuid

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.dependencies import TokenData, get_legacy_model_operational_db as get_db, require_permission
from app.models.product import Product, ProductVariant
from app.models.stock import StockBalance, StockLocation
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
    RetailLookupProduct,
    RetailLookupRead,
    RetailLookupVariant,
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
    is_for_sale: bool | None = Query(default=None),
    catalog_scope: Literal["all", "restaurant_menu", "retail_sale"] = Query(default="all"),
    current: TokenData = Depends(require_permission("inventory.product.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    effective_product_type = product_type
    effective_is_for_sale = is_for_sale
    effective_brand_id: uuid.UUID | None = None
    include_company_wide = False
    excluded_product_types: set[str] | None = None
    if catalog_scope == "restaurant_menu":
        if current.branch_id is None or current.brand_id is None or current.business_type != "restaurant":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Restaurant menu requires a signed Restaurant Brand and Branch context",
            )
        effective_product_type = "menu_item"
        effective_is_for_sale = True
        effective_brand_id = current.brand_id
        include_company_wide = True
    elif catalog_scope == "retail_sale":
        if (
            current.branch_id is None
            or current.brand_id is None
            or current.business_type != "retail_pos"
            or current.target_database != "retail_pos"
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Retail catalog requires a signed Retail Brand and Branch context",
            )
        effective_product_type = None
        effective_is_for_sale = True
        effective_brand_id = current.brand_id
        include_company_wide = False
        excluded_product_types = {"menu_item", "raw_material"}
    service = ProductService(db)
    products, total = await service.list_products(
        current.company_id,
        page=page,
        limit=limit,
        search=search,
        category_id=category_id,
        product_type=effective_product_type,
        is_active=is_active,
        is_for_sale=effective_is_for_sale,
        brand_id=effective_brand_id,
        include_company_wide=include_company_wide,
        excluded_product_types=excluded_product_types,
    )
    data = [ProductListItem.model_validate(product).model_dump() for product in products]
    return ok(data, meta={"total": total, "page": page, "limit": limit})


@router.get("/products/retail/lookup")
async def lookup_retail_product(
    code: str = Query(min_length=1, max_length=100),
    location_id: uuid.UUID = Query(),
    qty: Decimal = Query(default=Decimal("1"), gt=0),
    current: TokenData = Depends(require_permission("inventory.product.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if (
        current.branch_id is None
        or current.brand_id is None
        or current.business_type != "retail_pos"
        or current.target_database != "retail_pos"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Retail lookup requires a signed Retail Brand and Branch context",
        )

    location = await db.scalar(
        select(StockLocation).where(
            StockLocation.id == location_id,
            StockLocation.company_id == current.company_id,
            StockLocation.branch_id == current.branch_id,
            StockLocation.is_active.is_(True),
            StockLocation.deleted_at.is_(None),
        )
    )
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retail stock location not found")

    normalized_code = code.strip()
    product_filters = (
        Product.company_id == current.company_id,
        Product.brand_id == current.brand_id,
        Product.deleted_at.is_(None),
        Product.is_active.is_(True),
        Product.is_for_sale.is_(True),
        Product.product_type.not_in(("menu_item", "raw_material")),
    )
    base_products = (
        await db.scalars(
            select(Product)
            .where(
                *product_filters,
                or_(Product.barcode == normalized_code, func.lower(Product.sku) == normalized_code.lower()),
            )
            .options(selectinload(Product.variants), selectinload(Product.unit))
        )
    ).all()
    variant_matches = (
        await db.scalars(
            select(ProductVariant)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(
                *product_filters,
                ProductVariant.company_id == current.company_id,
                ProductVariant.deleted_at.is_(None),
                ProductVariant.is_active.is_(True),
                or_(
                    ProductVariant.barcode == normalized_code,
                    func.lower(ProductVariant.sku) == normalized_code.lower(),
                ),
            )
            .options(
                selectinload(ProductVariant.product).selectinload(Product.unit),
                selectinload(ProductVariant.product).selectinload(Product.variants),
            )
        )
    ).all()
    matched_product_ids = {row.id for row in base_products} | {row.product_id for row in variant_matches}
    if len(matched_product_ids) > 1 or len(variant_matches) > 1:
        return ok(
            RetailLookupRead(
                result="not_found",
                code=normalized_code,
                validation_time=datetime.now(timezone.utc),
                error_code="ambiguous_code",
            ).model_dump(mode="json")
        )

    base_product = base_products[0] if base_products else None
    variant_match = variant_matches[0] if variant_matches else None
    product = variant_match.product if variant_match is not None else base_product
    if product is None:
        return ok(
            RetailLookupRead(
                result="not_found",
                code=normalized_code,
                validation_time=datetime.now(timezone.utc),
                error_code="retail_product_not_found",
            ).model_dump(mode="json")
        )

    service = ProductService(db)

    async def stock_available(variant_id: uuid.UUID | None) -> Decimal:
        statement = select(StockBalance).where(
            StockBalance.company_id == current.company_id,
            StockBalance.branch_id == current.branch_id,
            StockBalance.location_id == location.id,
            StockBalance.product_id == product.id,
        )
        statement = statement.where(
            StockBalance.variant_id.is_(None)
            if variant_id is None
            else StockBalance.variant_id == variant_id
        )
        balance = await db.scalar(statement)
        return Decimal(balance.qty_available if balance is not None else 0)

    active_variants = sorted(
        [row for row in product.variants if row.deleted_at is None and row.is_active],
        key=lambda row: (row.sort_order, row.name, str(row.id)),
    )
    variant_rows: list[RetailLookupVariant] = []
    for row in active_variants:
        variant_rows.append(
            RetailLookupVariant(
                id=row.id,
                name=row.name,
                sku=row.sku,
                barcode=row.barcode,
                server_price=await service.get_product_price(product.id, current.company_id, None, row.id, qty),
                available_qty=await stock_available(row.id),
                is_active=row.is_active,
            )
        )

    selected_variant = variant_match
    if selected_variant is None and product.product_type == "variant":
        available_variants = [row for row in variant_rows if row.available_qty >= qty]
        if len(active_variants) != 1:
            return ok(
                RetailLookupRead(
                    result="variant_required",
                    code=normalized_code,
                    product=RetailLookupProduct(
                        id=product.id,
                        name=product.name,
                        sku=product.sku,
                        barcode=product.barcode,
                        product_type=product.product_type,
                        vat_type=product.vat_type,
                        vat_rate=product.vat_rate,
                        unit_code=product.unit.code if product.unit else None,
                        server_price=product.selling_price,
                        available_qty=sum((row.available_qty for row in available_variants), Decimal("0")),
                        variants=variant_rows,
                    ),
                    validation_time=datetime.now(timezone.utc),
                    error_code="variant_selection_required",
                ).model_dump(mode="json")
            )
        selected_variant = active_variants[0]

    selected_variant_id = selected_variant.id if selected_variant else None
    available_qty = await stock_available(selected_variant_id)
    server_price = await service.get_product_price(
        product.id,
        current.company_id,
        None,
        selected_variant_id,
        qty,
    )
    result: Literal["matched", "unavailable"] = "matched" if available_qty >= qty else "unavailable"
    return ok(
        RetailLookupRead(
            result=result,
            code=normalized_code,
            product=RetailLookupProduct(
                id=product.id,
                name=product.name,
                sku=selected_variant.sku if selected_variant else product.sku,
                barcode=selected_variant.barcode if selected_variant else product.barcode,
                product_type=product.product_type,
                vat_type=product.vat_type,
                vat_rate=product.vat_rate,
                unit_code=product.unit.code if product.unit else None,
                server_price=server_price,
                available_qty=available_qty,
                selected_variant_id=selected_variant_id,
                selected_variant_name=selected_variant.name if selected_variant else None,
                variants=variant_rows,
            ),
            validation_time=datetime.now(timezone.utc),
            error_code=None if result == "matched" else "retail_stock_unavailable",
        ).model_dump(mode="json")
    )


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
