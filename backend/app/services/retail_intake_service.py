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
from app.models.stock import StockLocation
from app.schemas.retail_intake import RetailIntakeRequest
from app.schemas.stock import ReceiveStockRequest
from app.services.stock_access_service import StockAccessService, STOCK_MANAGE_PERMISSIONS
from app.services.stock_service import StockService
from app.services.upload_service import UploadService
from app.config import settings

ACTION = "retail.product.intake"


def require_retail(current: TokenData) -> None:
    if not (current.company_id and current.brand_id and current.branch_id
            and current.business_type == "retail_pos" and current.target_database == "retail_pos"):
        raise HTTPException(403, "ต้องเลือกบริษัท แบรนด์ และสาขา Retail ก่อน")


async def lock(db: AsyncSession, key: str) -> None:
    value = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big", signed=True)
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": value})


async def find_code(db: AsyncSession, current: TokenData, code: str) -> Product | None:
    # Include inactive products and variants: they must not become silent duplicates.
    products = list((await db.scalars(select(Product).where(
        Product.company_id == current.company_id, Product.deleted_at.is_(None),
        or_(Product.barcode == code, func.lower(Product.sku) == code.lower()),
    ))).all())
    variant = await db.scalar(select(ProductVariant.id).where(
        ProductVariant.company_id == current.company_id, ProductVariant.deleted_at.is_(None),
        or_(ProductVariant.barcode == code, func.lower(ProductVariant.sku) == code.lower()),
    ))
    if variant or len(products) > 1:
        raise HTTPException(409, "บาร์โค้ดผูกกับตัวเลือกสินค้าหรือหลายรายการ กรุณาตรวจทะเบียนสินค้า")
    product = products[0] if products else None
    if product and (product.brand_id != current.brand_id or not product.is_active
                    or product.product_type != "simple"):
        raise HTTPException(409, "บาร์โค้ดมีอยู่แล้ว แต่ไม่ใช่สินค้าปลีกแบบปกติที่ใช้งานในแบรนด์นี้ กรุณาตรวจทะเบียนสินค้า")
    return product


async def lookup(db: AsyncSession, current: TokenData, barcode: str) -> dict:
    require_retail(current)
    product = await find_code(db, current, barcode.strip())
    return {"product": None if product is None else {
        "id": str(product.id), "barcode": product.barcode, "name": product.name,
        "sku": product.sku, "selling_price": str(product.selling_price),
        "cost_price": str(product.cost_price),
    }}


async def intake(db: AsyncSession, current: TokenData, payload: RetailIntakeRequest,
                 image: UploadFile | None = None) -> dict:
    require_retail(current)
    if "*" not in current.permissions and "inventory.product.create" not in current.permissions:
        raise HTTPException(403, "ไม่มีสิทธิ์เพิ่มสินค้า")
    if payload.qty > 0 and "*" not in current.permissions and not set(STOCK_MANAGE_PERMISSIONS).intersection(current.permissions):
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
    await lock(db, f"retail-barcode:{current.company_id}:{payload.barcode}")
    product = await find_code(db, current, payload.barcode)
    if payload.existing_product_id:
        if not product or product.id != payload.existing_product_id:
            raise HTTPException(409, "สินค้าเปลี่ยนแปลง กรุณาตรวจบาร์โค้ดอีกครั้ง")
    elif product:
        raise HTTPException(409, "บาร์โค้ดนี้มีสินค้าแล้ว กรุณาตรวจบาร์โค้ดและเลือกรับเพิ่ม")

    if payload.qty > 0:
        location = await db.scalar(select(StockLocation).where(
            StockLocation.id == payload.location_id, StockLocation.company_id == current.company_id,
            StockLocation.branch_id == current.branch_id, StockLocation.is_active.is_(True),
            StockLocation.deleted_at.is_(None),
        ))
        if not location:
            raise HTTPException(404, "ไม่พบคลังในสาขาที่เลือก")
        await StockAccessService(db).resolve_scope(current, requested_location_id=location.id, manage=True)
    created = product is None
    image_url = None
    if created:
        for model, identity in ((Unit, payload.unit_id), (Category, payload.category_id)):
            if identity and not await db.scalar(select(model.id).where(
                model.id == identity, model.company_id == current.company_id,
                model.is_active.is_(True), model.deleted_at.is_(None),
            )):
                raise HTTPException(404, "ไม่พบหน่วยหรือหมวดหมู่ที่ใช้งานได้ในบริษัทนี้")
        product = Product(id=uuid.uuid4(), company_id=current.company_id, brand_id=current.brand_id,
            sku=f"R-{uuid.uuid4().hex}", barcode=payload.barcode, name=payload.name,
            description=payload.description, category_id=payload.category_id, unit_id=payload.unit_id,
            selling_price=payload.selling_price, cost_price=payload.cost_price,
            vat_type=payload.vat_type, vat_rate=payload.vat_rate, product_type="simple",
            inventory_role="store_local", is_active=True, is_for_sale=True, is_for_purchase=True)
        db.add(product)
        await db.flush()
        if image:
            image_url = await UploadService().save_image(image, "products", str(current.company_id))
            db.add(ProductImage(company_id=current.company_id, product_id=product.id,
                url=image_url, filename=Path(image.filename or "image").name, is_primary=True, sort_order=0))
    movements = []
    if payload.qty > 0:
        movements = await StockService(db).receive(current.company_id, current.user_id,
            ReceiveStockRequest(location_id=payload.location_id, items=[{
                "product_id": product.id, "qty": payload.qty, "cost_per_unit": payload.cost_price,
            }], reference_type="opening" if created else "retail_intake",
                reference_id=str(payload.request_id), note="สแกนสร้างสินค้า / รับสินค้า Retail"), commit=False)
    result = {"product_id": str(product.id), "name": product.name, "barcode": product.barcode,
              "created": created, "qty_received": str(payload.qty), "location_id": str(payload.location_id) if payload.location_id else None,
              "movement_ids": [str(m.id) for m in movements], "image_url": image_url, "replayed": False}
    db.add(AuditLog(company_id=current.company_id, branch_id=current.branch_id, user_id=current.user_id,
        action=ACTION, resource="RetailIntake", resource_id=str(payload.request_id),
        new_value={"fingerprint": fingerprint, "result": result}))
    # Do not delete uploaded files on an uncertain commit: a retry resolves using the receipt.
    await db.commit()
    return result
