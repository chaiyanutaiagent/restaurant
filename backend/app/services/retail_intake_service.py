"""Barcode intake in the signed Retail database; one transaction and retry receipt."""
from __future__ import annotations

import hashlib
from pathlib import Path
import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import TokenData
from app.models.audit import AuditLog
from app.models.product import Category, Product, ProductImage, ProductVariant, Unit
from app.models.retail_catalog import RetailProductBrand, RetailProductBrandLink
from app.models.stock import StockLocation
from app.schemas.retail_intake import RetailIntakeRequest
from app.schemas.stock import ReceiveStockRequest
from app.services.stock_access_service import StockAccessService
from app.services.stock_service import StockService
from app.services.upload_service import UploadService
from app.config import settings

ACTION = "retail.product.intake"
RETAIL_STOCK_PERMISSIONS = {"inventory.stock.adjust", "brand.store.stock.adjust"}


def attribute_key(attributes: dict) -> tuple:
    return tuple(sorted((" ".join(k.split()).casefold(), " ".join(v.split()).casefold()) for k, v in attributes.items()))


def require_retail(current: TokenData) -> None:
    if not (current.company_id and current.brand_id and current.branch_id
            and current.business_type == "retail_pos" and current.target_database == "retail_pos"):
        raise HTTPException(403, "ต้องเลือกบริษัท แบรนด์ และสาขา Retail ก่อน")


async def lock(db: AsyncSession, key: str) -> None:
    value = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big", signed=True)
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": value})


async def find_code(db: AsyncSession, current: TokenData, code: str) -> tuple[Product | None, ProductVariant | None]:
    # Include inactive products and variants: they must not become silent duplicates.
    products = list((await db.scalars(select(Product).where(
        Product.company_id == current.company_id, Product.deleted_at.is_(None),
        or_(Product.barcode == code, func.lower(Product.sku) == code.lower()),
    ))).all())
    variants = list((await db.scalars(select(ProductVariant).where(
        ProductVariant.company_id == current.company_id, ProductVariant.deleted_at.is_(None),
        or_(ProductVariant.barcode == code, func.lower(ProductVariant.sku) == code.lower()),
    ))).all())
    if len(variants) + len(products) > 1:
        raise HTTPException(409, "บาร์โค้ดผูกกับหลายรายการ กรุณาตรวจทะเบียนสินค้า")
    variant = variants[0] if variants else None
    product = await db.get(Product, variant.product_id) if variant else (products[0] if products else None)
    if product and (product.brand_id != current.brand_id or not product.is_active
                    or product.company_id != current.company_id or product.deleted_at is not None
                    or product.product_type not in ("simple", "variant")
                    or (product.product_type == "variant" and not variant)
                    or (variant and (not variant.is_active or product.product_type != "variant"))):
        raise HTTPException(409, "รหัสนี้ไม่ใช่รายการที่รับเข้าได้ในแบรนด์ร้านนี้ กรุณาใช้บาร์โค้ดของตัวเลือก")
    return product, variant


async def lookup(db: AsyncSession, current: TokenData, barcode: str) -> dict:
    require_retail(current)
    product, variant = await find_code(db, current, barcode.strip())
    item = variant or product
    return {"product": None if product is None else {
        "id": str(product.id), "barcode": item.barcode, "name": product.name,
        "variant_id": str(variant.id) if variant else None,
        "variant_name": variant.name if variant else None,
        "sku": item.sku, "selling_price": str(item.selling_price if item.selling_price is not None else product.selling_price),
        "cost_price": str(item.cost_price if item.cost_price is not None else product.cost_price),
    }}


async def intake(db: AsyncSession, current: TokenData, payload: RetailIntakeRequest,
                 image: UploadFile | None = None) -> dict:
    require_retail(current)
    if "*" not in current.permissions and "inventory.product.create" not in current.permissions:
        raise HTTPException(403, "ไม่มีสิทธิ์เพิ่มสินค้า")
    if payload.qty > 0 and "*" not in current.permissions and not RETAIL_STOCK_PERMISSIONS.intersection(current.permissions):
        raise HTTPException(403, "ไม่มีสิทธิ์รับสินค้าเข้าคลัง")
    if payload.existing_product_id and image:
        raise HTTPException(422, "รับสินค้าเดิมเพิ่มไม่แก้รูปหรือรายละเอียดสินค้า")
    image_hash = ""
    if image:
        contents = await image.read(settings.max_file_size_mb * 1024 * 1024 + 1)
        if len(contents) > settings.max_file_size_mb * 1024 * 1024:
            raise HTTPException(413, "รูปมีขนาดใหญ่เกินกำหนด")
        image_hash = hashlib.sha256(contents).hexdigest()
        await image.seek(0)
    fingerprint = hashlib.sha256((payload.model_dump_json() + image_hash + str(current.brand_id)
                                 + str(current.branch_id) + str(current.user_id)).encode()).hexdigest()
    await lock(db, f"{ACTION}:{current.company_id}:{payload.request_id}")
    receipt = await db.scalar(select(AuditLog).where(
        AuditLog.company_id == current.company_id, AuditLog.action == ACTION,
        AuditLog.resource_id == str(payload.request_id),
    ))
    if receipt:
        if receipt.new_value["fingerprint"] != fingerprint:
            raise HTTPException(409, "คำขอนี้เคยบันทึกด้วยข้อมูลอื่นแล้ว กรุณาตรวจรายการเดิม")
        return {**receipt.new_value["result"], "replayed": True}
    await lock(db, f"retail-barcode:{current.company_id}:{payload.barcode.casefold()}")
    product, variant = await find_code(db, current, payload.barcode)
    if payload.existing_product_id:
        if not product or product.id != payload.existing_product_id or (variant.id if variant else None) != payload.existing_variant_id:
            raise HTTPException(409, "สินค้าเปลี่ยนแปลง กรุณาตรวจบาร์โค้ดอีกครั้ง")
    elif product:
        raise HTTPException(409, "บาร์โค้ดนี้มีสินค้าแล้ว กรุณาตรวจบาร์โค้ดและเลือกรับเพิ่ม")

    if payload.parent_product_id:
        # Serializes additions to a family, including different barcodes with the same attributes.
        product = await db.scalar(select(Product).where(
            Product.id == payload.parent_product_id, Product.company_id == current.company_id,
            Product.brand_id == current.brand_id, Product.product_type == "variant",
            Product.is_active.is_(True), Product.deleted_at.is_(None),
        ).with_for_update())
        if not product:
            raise HTTPException(404, "ไม่พบสินค้าหลักแบบมีตัวเลือกในแบรนด์ร้านนี้")
        previous = list((await db.scalars(select(ProductVariant).where(
            ProductVariant.product_id == product.id, ProductVariant.company_id == current.company_id,
            ProductVariant.deleted_at.is_(None),
        ))).all())
        for row in previous:
            if attribute_key(row.attributes or {}) == attribute_key(payload.attributes):
                raise HTTPException(409, "มีชุดตัวเลือกนี้แล้ว ให้สแกนบาร์โค้ดเดิมเพื่อรับเพิ่ม")
        dimensions = {key.casefold() for key in payload.attributes}
        if previous and any({key.casefold() for key in (row.attributes or {})} != dimensions for row in previous):
            raise HTTPException(422, "ใช้ชื่อกลุ่มตัวเลือกเดียวกับสินค้าหลัก เช่น สี และ ไซซ์")

    if payload.qty > 0:
        location = await db.scalar(select(StockLocation).where(
            StockLocation.id == payload.location_id, StockLocation.company_id == current.company_id,
            StockLocation.branch_id == current.branch_id, StockLocation.is_active.is_(True),
            StockLocation.deleted_at.is_(None),
        ))
        if not location:
            raise HTTPException(404, "ไม่พบคลังในสาขาที่เลือก")
        await StockAccessService(db).resolve_scope(current, requested_location_id=location.id, manage=True, store_only=True)
    created = not payload.existing_product_id
    image_url = None
    if product is None:
        for model, identity in ((Unit, payload.unit_id), (Category, payload.category_id)):
            if identity and not await db.scalar(select(model.id).where(
                model.id == identity, model.company_id == current.company_id,
                model.is_active.is_(True), model.deleted_at.is_(None),
            )):
                raise HTTPException(404, "ไม่พบหน่วยหรือหมวดหมู่ที่ใช้งานได้ในบริษัทนี้")
        product = Product(id=uuid.uuid4(), company_id=current.company_id, brand_id=current.brand_id,
            sku=f"R-{uuid.uuid4().hex}", barcode=payload.barcode if payload.product_type == "simple" else None, name=payload.name,
            description=payload.description, category_id=payload.category_id, unit_id=payload.unit_id,
            selling_price=payload.selling_price, cost_price=payload.cost_price,
            vat_type=payload.vat_type, vat_rate=payload.vat_rate, product_type=payload.product_type,
            inventory_role="store_local", is_active=True, is_for_sale=True, is_for_purchase=True)
        db.add(product)
        await db.flush()
        if payload.product_brand_id:
            brand = await db.scalar(select(RetailProductBrand).where(
                RetailProductBrand.id == payload.product_brand_id, RetailProductBrand.company_id == current.company_id,
                RetailProductBrand.deleted_at.is_(None)))
            if not brand:
                raise HTTPException(404, "ไม่พบแบรนด์สินค้าในบริษัทนี้")
            db.add(RetailProductBrandLink(product_id=product.id, company_id=current.company_id, product_brand_id=brand.id))
    if created and product.product_type == "variant":
        variant = ProductVariant(id=uuid.uuid4(), company_id=current.company_id, product_id=product.id,
            sku=f"RV-{uuid.uuid4().hex}", barcode=payload.barcode,
            name=" / ".join(payload.attributes.values()), attributes=payload.attributes,
            selling_price=payload.selling_price, cost_price=payload.cost_price, is_active=True, sort_order=0)
        db.add(variant)
        await db.flush()
    if created and image:
        image_url = await UploadService().save_image(image, "products", str(current.company_id))
        if variant:
            variant.image_url = image_url
        else:
            db.add(ProductImage(company_id=current.company_id, product_id=product.id,
                url=image_url, filename=Path(image.filename or "image").name, is_primary=True, sort_order=0))
    movements = []
    if payload.qty > 0:
        movements = await StockService(db).receive(current.company_id, current.user_id,
            ReceiveStockRequest(location_id=payload.location_id, items=[{
                "product_id": product.id, "variant_id": variant.id if variant else None,
                "qty": payload.qty, "cost_per_unit": payload.cost_price,
            }], reference_type="opening" if created else "retail_intake",
                reference_id=str(payload.request_id), note="สแกนสร้างสินค้า / รับสินค้า Retail"), commit=False)
    result = {"product_id": str(product.id), "name": product.name, "barcode": payload.barcode,
              "variant_id": str(variant.id) if variant else None, "variant_name": variant.name if variant else None,
              "created": created, "qty_received": str(payload.qty), "location_id": str(payload.location_id) if payload.location_id else None,
              "movement_ids": [str(m.id) for m in movements], "image_url": image_url, "replayed": False}
    db.add(AuditLog(company_id=current.company_id, branch_id=current.branch_id, user_id=current.user_id,
        action=ACTION, resource="RetailIntake", resource_id=str(payload.request_id),
        new_value={"fingerprint": fingerprint, "result": result}))
    # Do not delete uploaded files on an uncertain commit: a retry resolves using the receipt.
    await db.commit()
    return result
