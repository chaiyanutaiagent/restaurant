from __future__ import annotations

from datetime import date
from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, require_permission
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
    po = await PurchaseService(db).update_po(po_id, current.company_id, payload)
    return ok(PurchaseOrderRead.model_validate(po).model_dump())


@router.post("/orders/{po_id}/submit")
async def submit_purchase_order(
    po_id: uuid.UUID,
    current: TokenData = Depends(require_permission("inventory.purchase.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    po = await PurchaseService(db).submit_for_approval(po_id, current.company_id, current.user_id)
    return ok(PurchaseOrderRead.model_validate(po).model_dump())


@router.post("/orders/{po_id}/approve")
async def approve_purchase_order(
    po_id: uuid.UUID,
    payload: ApprovePORequest,
    current: TokenData = Depends(require_permission("inventory.purchase.approve")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    po = await PurchaseService(db).approve_po(po_id, current.company_id, current.user_id, payload)
    return ok(PurchaseOrderRead.model_validate(po).model_dump())


@router.post("/orders/{po_id}/cancel")
async def cancel_purchase_order(
    po_id: uuid.UUID,
    payload: CancelPORequest,
    current: TokenData = Depends(require_permission("inventory.purchase.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    po = await PurchaseService(db).cancel_po(po_id, current.company_id, current.user_id, payload.reason)
    return ok(PurchaseOrderRead.model_validate(po).model_dump())


@router.get("/orders/{po_id}/pdf")
async def purchase_order_pdf(
    po_id: uuid.UUID,
    current: TokenData = Depends(require_permission("inventory.purchase.view")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = PurchaseService(db)
    po = await service.get_po(po_id, current.company_id)
    company = await _get_company(db, current.company_id)
    html = render_po_html(po, company.name, company.address or "", company.tax_id or "")
    content, media_type = html_to_pdf_or_html(html)
    ext = "pdf" if media_type == "application/pdf" else "html"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={po.po_number}.{ext}"},
    )


@router.post("/receipts", status_code=status.HTTP_201_CREATED)
async def create_goods_receipt(
    payload: CreateGRRequest,
    current: TokenData = Depends(require_permission("inventory.purchase.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    receipt = await PurchaseService(db).receive_goods(current.company_id, current.branch_id, current.user_id, payload)
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
    company = await _get_company(db, current.company_id)
    html = render_gr_html(
        receipt,
        receipt.purchase_order,
        company.name,
        company.address or "",
        company.tax_id or "",
    )
    content, media_type = html_to_pdf_or_html(html)
    ext = "pdf" if media_type == "application/pdf" else "html"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={receipt.gr_number}.{ext}"},
    )
