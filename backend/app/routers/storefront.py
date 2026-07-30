from __future__ import annotations

from decimal import Decimal
from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.branch import Branch
from app.models.company import Company
from app.models.product import Product
from app.models.settings import BranchSettings
from app.models.stock import StockBalance
from app.schemas.api_integration import (
    PublicStorefrontBranchRead,
    PublicStorefrontCompanyRead,
    PublicStorefrontProductRead,
    PublicStorefrontSummaryRead,
)
from app.services.crm_service import resolve_public_company_id

router = APIRouter(prefix="/api/public/storefront", tags=["storefront"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


def _serialize_company(company: Company) -> dict[str, Any]:
    return PublicStorefrontCompanyRead.model_validate(company).model_dump(mode="json")


def _serialize_branch(branch: Branch, settings_row: BranchSettings | None) -> dict[str, Any]:
    storefront_enabled = settings_row.public_storefront_enabled if settings_row else True
    return PublicStorefrontBranchRead(
        id=branch.id,
        code=branch.code,
        name=branch.name,
        name_en=branch.name_en,
        address=branch.address,
        landmark=branch.landmark,
        phone=branch.phone,
        email=branch.email,
        latitude=branch.latitude,
        longitude=branch.longitude,
        google_maps_url=branch.google_maps_url,
        working_hours=settings_row.working_hours if settings_row else None,
        is_active=branch.is_active,
        is_pickup_available=branch.is_active and not branch.is_warehouse and storefront_enabled,
    ).model_dump(mode="json")


def _serialize_product(product: Product, total_qty_available: Decimal) -> dict[str, Any]:
    qty = Decimal(total_qty_available or 0)
    return PublicStorefrontProductRead(
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
        total_qty_available=qty,
        in_stock=qty > 0,
    ).model_dump(mode="json")


def _product_statement(company_id: uuid.UUID) -> Select[tuple[Product, Decimal]]:
    stock_subquery = (
        select(
            StockBalance.product_id.label("product_id"),
            func.coalesce(func.sum(StockBalance.qty_on_hand - StockBalance.qty_reserved), 0).label("total_qty_available"),
        )
        .where(StockBalance.company_id == company_id)
        .group_by(StockBalance.product_id)
        .subquery()
    )
    return (
        select(Product, func.coalesce(stock_subquery.c.total_qty_available, 0))
        .outerjoin(stock_subquery, stock_subquery.c.product_id == Product.id)
        .where(
            Product.company_id == company_id,
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
            Product.is_for_sale.is_(True),
        )
        .options(selectinload(Product.category), selectinload(Product.unit))
    )


@router.get("")
async def get_storefront_summary(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company_id = await resolve_public_company_id(db)
    company = await db.scalar(select(Company).where(Company.id == company_id, Company.is_active.is_(True)))
    assert company is not None

    product_rows = (
        await db.execute(
            _product_statement(company_id)
            .order_by(Product.created_at.desc())
            .limit(8)
        )
    ).all()

    branches = (
        await db.scalars(
            select(Branch)
            .where(
                Branch.company_id == company_id,
                Branch.deleted_at.is_(None),
                Branch.is_active.is_(True),
            )
            .order_by(Branch.sort_order.asc(), Branch.name.asc())
        )
    ).all()
    branch_ids = [branch.id for branch in branches]
    settings_rows = (
        await db.scalars(select(BranchSettings).where(BranchSettings.company_id == company_id, BranchSettings.branch_id.in_(branch_ids)))
    ).all() if branch_ids else []
    settings_by_branch = {row.branch_id: row for row in settings_rows}
    visible_branches = [
        branch for branch in branches if (settings_by_branch.get(branch.id).public_storefront_enabled if settings_by_branch.get(branch.id) else True)
    ]

    payload = PublicStorefrontSummaryRead(
        company=PublicStorefrontCompanyRead.model_validate(company),
        featured_products=[
            PublicStorefrontProductRead.model_validate(_serialize_product(product, total_qty))
            for product, total_qty in product_rows
        ],
        branches=[
            PublicStorefrontBranchRead.model_validate(_serialize_branch(branch, settings_by_branch.get(branch.id)))
            for branch in visible_branches
        ],
    )
    return ok(payload.model_dump(mode="json"))


@router.get("/products")
async def list_storefront_products(
    search: str | None = Query(default=None),
    category_id: uuid.UUID | None = Query(default=None),
    in_stock_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=24, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company_id = await resolve_public_company_id(db)
    statement = _product_statement(company_id)

    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                Product.sku.ilike(pattern),
                Product.barcode.ilike(pattern),
                Product.name.ilike(pattern),
                Product.name_en.ilike(pattern),
            )
        )
    if category_id is not None:
        statement = statement.where(Product.category_id == category_id)
    if in_stock_only:
        statement = statement.where(func.coalesce(statement.selected_columns[1], 0) > 0)

    total = int((await db.scalar(select(func.count()).select_from(statement.subquery()))) or 0)
    rows = (
        await db.execute(
            statement
            .order_by(Product.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).all()
    data = [_serialize_product(product, total_qty) for product, total_qty in rows]
    return ok(data, meta={"total": total, "page": page, "limit": limit})


@router.get("/branches")
async def list_storefront_branches(
    active_only: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company_id = await resolve_public_company_id(db)
    filters = [Branch.company_id == company_id, Branch.deleted_at.is_(None)]
    if active_only:
        filters.append(Branch.is_active.is_(True))

    branches = (
        await db.scalars(select(Branch).where(*filters).order_by(Branch.sort_order.asc(), Branch.name.asc()))
    ).all()
    branch_ids = [branch.id for branch in branches]
    settings_rows = (
        await db.scalars(select(BranchSettings).where(BranchSettings.company_id == company_id, BranchSettings.branch_id.in_(branch_ids)))
    ).all() if branch_ids else []
    settings_by_branch = {row.branch_id: row for row in settings_rows}
    visible_branches = [
        branch for branch in branches if (settings_by_branch.get(branch.id).public_storefront_enabled if settings_by_branch.get(branch.id) else True)
    ]
    data = [_serialize_branch(branch, settings_by_branch.get(branch.id)) for branch in visible_branches]
    return ok(data, meta={"total": len(data)})
