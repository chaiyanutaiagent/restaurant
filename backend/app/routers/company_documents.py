from datetime import date
from typing import Literal
import uuid
from pydantic import BaseModel

from fastapi import APIRouter, Depends, Query, Response

from app.config import settings
from app.dependencies import TokenData, require_any_permission
from app.services.document_register_service import list_register
from app.services.document_register_service import register_session_factory
from app.services.document_archive_service import history, export_document

router = APIRouter(prefix="/api/v1/company/documents", tags=["company-documents"])
DocumentKind = Literal["purchase_order", "goods_receipt", "supplier_invoice", "payment_voucher", "wht_certificate", "sales_tax_document", "sales_quotation", "sales_delivery", "customer_invoice", "billing_notice", "customer_receipt"]


@router.get("/register")
async def register(
    response: Response,
    kind: DocumentKind,
    search: str = Query(default="", max_length=100),
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1, le=10000),
    limit: int = Query(default=25, ge=1, le=100),
    current: TokenData = Depends(require_any_permission(
        "inventory.purchase.view", "accounting.payment.view", "accounting.invoice.view",
    )),
):
    response.headers["Cache-Control"] = "private, no-store"
    data = await list_register(current, kind, search=search, date_from=date_from,
                               date_to=date_to, page=page, limit=limit)
    return {"data": data, "meta": {"version": settings.app_version}, "error": None}


@router.get("/{kind}/{source_id}/history")
async def document_history(kind: DocumentKind, source_id: uuid.UUID, response: Response,
    page: int = Query(default=1, ge=1, le=10000),
    current: TokenData = Depends(require_any_permission("inventory.purchase.view", "accounting.payment.view", "accounting.invoice.view")),
):
    response.headers["Cache-Control"] = "private, no-store"
    async with register_session_factory(current, kind)() as db:
        data = await history(db, current, kind, source_id, page)
    return {"data": data, "error": None}


class PrintRequest(BaseModel):
    variant: Literal["original", "copy"] = "copy"


@router.post("/{kind}/{source_id}/print")
async def print_document(kind: DocumentKind, source_id: uuid.UUID, payload: PrintRequest,
    current: TokenData = Depends(require_any_permission("inventory.purchase.view", "accounting.payment.view", "accounting.invoice.view")),
):
    async with register_session_factory(current, kind)() as db:
        content, media_type, number, digest, sequence = await export_document(db, current, kind, source_id, payload.variant)
    ext = "pdf" if media_type == "application/pdf" else "html"
    return Response(content=content, media_type=media_type, headers={
        "Cache-Control": "private, no-store", "X-Document-SHA256": digest,
        "Content-Disposition": f'attachment; filename="{source_id}-{payload.variant}-{sequence}.{ext}"',
    })
