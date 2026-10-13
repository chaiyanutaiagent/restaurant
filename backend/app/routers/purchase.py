from __future__ import annotations

from datetime import date
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from app.models.document_snapshot import DocumentEvent
from app.services.document_lifecycle_service import append_event, require_reason

from app.config import settings
from app.dependencies import TokenData, get_scoped_operational_db as get_db, require_permission
from app.models.company import Company
from app.schemas.purchase import (
    ApprovePORequest,
    CancelPORequest,
    CreateGRRequest,
    CreatePORequest,
    GoodsReceiptRead,
    POListItem,
    PurchaseOrderRead,
    SupplierCreate,
    SupplierRead,
    SupplierUpdate,
    UpdatePORequest,
)
from app.services.purchase_service import PurchaseService
from app.services.document_snapshot_service import require_document_scope, evidence_notice
from app.services.document_archive_service import evidence_for, copy_html
from app.utils.pdf_generator import html_to_pdf_or_html, render_gr_html, render_po_html

router = APIRouter(prefix="/api/v1/purchase", tags=["purchase"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


async def _get_company(db: AsyncSession, company_id: uuid.UUID) -> Company:
    company = await db.get(Company, company_id)
    if company is None:
        raise RuntimeError("Company not found")
    return company


@router.get("/suppliers")
async def list_suppliers(
    search: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    current: TokenData = Depends(require_permission("inventory.purchase.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    suppliers, total = await PurchaseService(db).list_suppliers(current.company_id, search, is_active, page, limit)
    return ok(
        [SupplierRead.model_validate(item).model_dump() for item in suppliers],
        meta={"total": total, "page": page, "limit": limit},
    )


@router.post("/suppliers", status_code=status.HTTP_201_CREATED)
async def create_supplier(
    payload: SupplierCreate,
    current: TokenData = Depends(require_permission("inventory.purchase.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    supplier = await PurchaseService(db).create_supplier(current.company_id, payload)
    return ok(SupplierRead.model_validate(supplier).model_dump())


@router.get("/suppliers/{supplier_id}")
async def get_supplier(
    supplier_id: uuid.UUID,
    current: TokenData = Depends(require_permission("inventory.purchase.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    supplier = await PurchaseService(db).get_supplier(supplier_id, current.company_id)
    return ok(SupplierRead.model_validate(supplier).model_dump())


@router.patch("/suppliers/{supplier_id}")
async def update_supplier(
    supplier_id: uuid.UUID,
    payload: SupplierUpdate,
    current: TokenData = Depends(require_permission("inventory.purchase.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    supplier = await PurchaseService(db).update_supplier(supplier_id, current.company_id, payload)
    return ok(SupplierRead.model_validate(supplier).model_dump())


@router.delete("/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplier(
    supplier_id: uuid.UUID,
    current: TokenData = Depends(require_permission("inventory.purchase.create")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await PurchaseService(db).delete_supplier(supplier_id, current.company_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/orders")
async def list_purchase_orders(
    branch_id: uuid.UUID | None = Query(default=None),
    supplier_id: uuid.UUID | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    current: TokenData = Depends(require_permission("inventory.purchase.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    orders, total = await PurchaseService(db).list_pos(
        company_id=current.company_id,
        branch_id=branch_id,
        supplier_id=supplier_id,
        status_value=status_value,
        date_from=date_from,
        date_to=date_to,
        page=page,
        limit=limit,
    )
    data = [
        POListItem(
            id=order.id,
            po_number=order.po_number,
            status=order.status,
            order_date=order.order_date,
            expected_date=order.expected_date,
            supplier_id=order.supplier_id,
            supplier_name=order.supplier.name,
            total_amount=order.total_amount,
            paid_amount=order.paid_amount,
            remaining_amount=order.remaining_amount,
            item_count=len(order.items),
        ).model_dump()
        for order in orders
    ]
    return ok(data, meta={"total": total, "page": page, "limit": limit})


@router.post("/orders", status_code=status.HTTP_201_CREATED)
async def create_purchase_order(
    payload: CreatePORequest,
    current: TokenData = Depends(require_permission("inventory.purchase.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from types import SimpleNamespace
    require_document_scope(current, SimpleNamespace(company_id=current.company_id, branch_id=payload.branch_id))
    po = await PurchaseService(db).create_po(current.company_id, current.user_id, payload)
    return ok(PurchaseOrderRead.model_validate(po).model_dump())


@router.get("/orders/{po_id}")
async def get_purchase_order(
    po_id: uuid.UUID,
    current: TokenData = Depends(require_permission("inventory.purchase.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    po = await PurchaseService(db).get_po(po_id, current.company_id)
    return ok(PurchaseOrderRead.model_validate(po).model_dump())


@router.patch("/orders/{po_id}")
async def update_purchase_order(
    po_id: uuid.UUID,
    payload: UpdatePORequest,
    current: TokenData = Depends(require_permission("inventory.purchase.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = PurchaseService(db)
    require_document_scope(current, await service.get_po(po_id, current.company_id))
    po = await service.update_po(po_id, current.company_id, payload, current.user_id)
    return ok(PurchaseOrderRead.model_validate(po).model_dump())


@router.post("/orders/{po_id}/submit")
async def submit_purchase_order(
    po_id: uuid.UUID,
    current: TokenData = Depends(require_permission("inventory.purchase.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = PurchaseService(db)
    require_document_scope(current, await service.get_po(po_id, current.company_id))
    po = await service.submit_for_approval(po_id, current.company_id, current.user_id)
    return ok(PurchaseOrderRead.model_validate(po).model_dump())


@router.post("/orders/{po_id}/approve")
async def approve_purchase_order(
    po_id: uuid.UUID,
    payload: ApprovePORequest,
    current: TokenData = Depends(require_permission("inventory.purchase.approve")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = PurchaseService(db)
    require_document_scope(current, await service.get_po(po_id, current.company_id))
    po = await service.approve_po(po_id, current.company_id, current.user_id, payload)
    return ok(PurchaseOrderRead.model_validate(po).model_dump())


@router.post("/orders/{po_id}/cancel")
async def cancel_purchase_order(
    po_id: uuid.UUID,
    payload: CancelPORequest,
    current: TokenData = Depends(require_permission("inventory.purchase.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = PurchaseService(db)
    require_document_scope(current, await service.get_po(po_id, current.company_id))
    po = await service.cancel_po(po_id, current.company_id, current.user_id, payload.reason)
    return ok(PurchaseOrderRead.model_validate(po).model_dump())


@router.get("/orders/{po_id}/pdf")
async def purchase_order_pdf(
    po_id: uuid.UUID,
    current: TokenData = Depends(require_permission("inventory.purchase.view")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = PurchaseService(db)
    po = await service.get_po(po_id, current.company_id)
    snapshot = await evidence_for(db, current, "purchase_order", po)
    if snapshot:
        html = copy_html(snapshot, po)
    else:
        company = await _get_company(db, current.company_id)
        html = evidence_notice(render_po_html(po, company.name, company.address or "", company.tax_id or ""),
            "ฉบับร่าง / เอกสารเก่า ไม่มีหลักฐาน ณ วันออก ชื่อและที่อยู่อาจเป็นข้อมูลปัจจุบัน")
    content, media_type = html_to_pdf_or_html(html)
    ext = "pdf" if media_type == "application/pdf" else "html"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={po.po_number}.{ext}", "Cache-Control": "private, no-store"},
    )


class ReplacementRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


@router.post("/orders/{po_id}/replacement", status_code=201)
async def replace_purchase_order(po_id: uuid.UUID, payload: ReplacementRequest,
    current: TokenData = Depends(require_permission("inventory.purchase.create")),
    db: AsyncSession = Depends(get_db),
):
    service = PurchaseService(db)
    source = await service._get_po_entity(po_id, current.company_id)
    require_document_scope(current, source)
    reason = require_reason(payload.reason)
    if source.status != "cancelled":
        raise HTTPException(409, "ต้องยกเลิกใบสั่งซื้อเดิมผ่านขั้นตอนเดิมก่อนสร้างร่างทดแทน")
    prior = await db.scalar(select(DocumentEvent.id).where(DocumentEvent.company_id == current.company_id,
        DocumentEvent.document_kind == "purchase_order", DocumentEvent.source_id == po_id,
        DocumentEvent.action == "replacement_created").limit(1))
    if prior:
        raise HTTPException(409, "มีร่างทดแทนแล้ว กรุณาดูประวัติ ห้ามสร้างซ้ำ")
    from app.schemas.purchase import POItemCreate
    data = CreatePORequest(supplier_id=source.supplier_id, branch_id=source.branch_id,
        expected_date=source.expected_date, vat_type=source.vat_type, note=source.note,
        items=[POItemCreate(product_id=i.product_id, variant_id=i.variant_id, qty_ordered=i.qty_ordered,
            unit_cost=i.unit_cost, discount_amount=i.discount_amount, vat_type=i.vat_type, vat_rate=i.vat_rate) for i in source.items])
    replacement = await service.create_po(current.company_id, current.user_id, data, commit=False)
    await append_event(db, source, "purchase_order", "replacement_created", current.user_id, reason,
        {"replacement_id": replacement.id, "number": replacement.po_number})
    await append_event(db, replacement, "purchase_order", "replaces", current.user_id, reason,
        {"original_id": source.id, "number": source.po_number})
    await db.commit()
    return ok({"id": replacement.id, "po_number": replacement.po_number, "status": "draft"})


@router.post("/receipts", status_code=status.HTTP_201_CREATED)
async def create_goods_receipt(
    payload: CreateGRRequest,
    current: TokenData = Depends(require_permission("inventory.purchase.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = PurchaseService(db)
    require_document_scope(current, await service.get_po(payload.po_id, current.company_id))
    receipt = await service.receive_goods(current.company_id, current.branch_id, current.user_id, payload)
    return ok(GoodsReceiptRead.model_validate(receipt).model_dump())


@router.get("/receipts")
async def list_goods_receipts(
    po_id: uuid.UUID | None = Query(default=None),
    branch_id: uuid.UUID | None = Query(default=None),
    current: TokenData = Depends(require_permission("inventory.purchase.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    receipts = await PurchaseService(db).list_receipts(current.company_id, po_id, branch_id)
    return ok([GoodsReceiptRead.model_validate(item).model_dump() for item in receipts])


@router.get("/receipts/{gr_id}")
async def get_goods_receipt(
    gr_id: uuid.UUID,
    current: TokenData = Depends(require_permission("inventory.purchase.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    receipt = await PurchaseService(db).get_gr(gr_id, current.company_id)
    return ok(GoodsReceiptRead.model_validate(receipt).model_dump())


@router.get("/receipts/{gr_id}/pdf")
async def goods_receipt_pdf(
    gr_id: uuid.UUID,
    current: TokenData = Depends(require_permission("inventory.purchase.view")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = PurchaseService(db)
    receipt = await service.get_gr(gr_id, current.company_id)
    snapshot = await evidence_for(db, current, "goods_receipt", receipt)
    if snapshot:
        html = copy_html(snapshot, receipt)
    else:
        company = await _get_company(db, current.company_id)
        html = evidence_notice(render_gr_html(receipt, receipt.purchase_order, company.name, company.address or "", company.tax_id or ""),
            "เอกสารเก่า ไม่มีหลักฐาน ณ วันออก ชื่อและที่อยู่อาจเป็นข้อมูลปัจจุบัน")
    content, media_type = html_to_pdf_or_html(html)
    ext = "pdf" if media_type == "application/pdf" else "html"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={receipt.gr_number}.{ext}", "Cache-Control": "private, no-store"},
    )
