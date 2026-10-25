import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.product import Product, ProductImage, ProductVariant
from app.models.retail_catalog import RetailProductBrand, RetailProductBrandLink
from app.services.retail_intake_service import require_retail


async def list_brands(db, current):
    require_retail(current)
    rows = await db.scalars(select(RetailProductBrand).where(
        RetailProductBrand.company_id == current.company_id, RetailProductBrand.deleted_at.is_(None),
    ).order_by(RetailProductBrand.name))
    return [{"id": row.id, "name": row.name} for row in rows]


async def create_brand(db, current, name):
    require_retail(current)
    identity = uuid.uuid4()
    name_key = name.casefold()
    result = await db.scalar(insert(RetailProductBrand).values(
        id=identity, company_id=current.company_id, name=name, name_key=name_key,
    ).on_conflict_do_nothing(constraint="uq_retail_product_brand_name").returning(RetailProductBrand.id))
    row = await db.scalar(select(RetailProductBrand).where(
        RetailProductBrand.company_id == current.company_id, RetailProductBrand.name_key == name_key))
    if row.deleted_at:
        raise HTTPException(409, "แบรนด์สินค้านี้ถูกปิดใช้งาน ให้ผู้ดูแลตรวจสอบ")
    if result:
        db.add(AuditLog(company_id=current.company_id, branch_id=current.branch_id, user_id=current.user_id,
            action="retail.product_brand.create", resource="RetailProductBrand", resource_id=str(row.id),
            new_value={"name": row.name}))
    await db.commit()
    return {"id": row.id, "name": row.name, "reused": not bool(result)}


async def brand_names(db, company_id, product_ids):
    if not product_ids:
        return {}
    rows = await db.execute(select(RetailProductBrandLink.product_id, RetailProductBrand.name).join(
        RetailProductBrand, RetailProductBrand.id == RetailProductBrandLink.product_brand_id,
    ).where(RetailProductBrandLink.company_id == company_id, RetailProductBrand.company_id == company_id,
        RetailProductBrandLink.product_id.in_(product_ids), RetailProductBrand.deleted_at.is_(None)))
    return dict(rows.all())


async def catalog_images(db, company_id, product_ids):
    """Read old intake attachments without rewriting customer data."""
    if not product_ids:
        return {}
    images = await db.scalars(select(ProductImage).where(
        ProductImage.company_id == company_id, ProductImage.product_id.in_(product_ids),
    ).order_by(ProductImage.is_primary.desc(), ProductImage.sort_order, ProductImage.created_at, ProductImage.id))
    result = {}
    for image in images:
        result.setdefault(image.product_id, image.url)
    missing = [identity for identity in product_ids if identity not in result]
    if missing:
        variants = await db.scalars(select(ProductVariant).where(
            ProductVariant.company_id == company_id, ProductVariant.product_id.in_(missing),
            ProductVariant.deleted_at.is_(None), ProductVariant.is_active.is_(True),
            ProductVariant.image_url.is_not(None),
        ).order_by(ProductVariant.sort_order, ProductVariant.created_at, ProductVariant.id))
        for variant in variants:
            result.setdefault(variant.product_id, variant.image_url)
    return result


async def parents(db, current, search):
    require_retail(current)
    statement = select(Product).where(Product.company_id == current.company_id,
        Product.brand_id == current.brand_id, Product.product_type == "variant",
        Product.is_active.is_(True), Product.deleted_at.is_(None))
    if search:
        statement = statement.where(Product.name.ilike(f"%{search}%"))
    rows = list((await db.scalars(statement.options(selectinload(Product.variants)).order_by(Product.name, Product.id).limit(50))).all())
    names = await brand_names(db, current.company_id, [row.id for row in rows])
    return [{"id": row.id, "name": row.name, "product_brand_name": names.get(row.id),
        "option_names": list(next((v.attributes for v in row.variants if v.deleted_at is None and v.attributes), {}).keys()),
        "variants": [{"name": v.name, "barcode": v.barcode} for v in row.variants if v.deleted_at is None],
    } for row in rows]
