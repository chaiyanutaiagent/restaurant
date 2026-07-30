from __future__ import annotations

from datetime import date
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, require_permission
from app.schemas.etax import CancelDocumentRequest, IssueCreditNoteRequest, IssueTaxInvoiceRequest
from app.services.etax_service import ETaxService
from app.utils.pdf_generator import generate_tax_invoice_pdf

router = APIRouter(prefix="/api/v1/etax", tags=["etax"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


@router.get("/documents")
async def list_documents(
    document_type: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current: TokenData = Depends(require_permission("accounting.invoice.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ETaxService(db)
    documents, total = await service.list_documents(
        current.company_id,
        document_type=document_type,
        status_value=status_value,
        date_from=date_from,
        date_to=date_to,
        page=page,
        limit=limit,
    )
    return ok([service.serialize_list_item(document) for document in documents], meta={"total": total, "page": page, "limit": limit})


@router.post("/documents/tax-invoice", status_code=status.HTTP_201_CREATED)
async def issue_tax_invoice(
    payload: IssueTaxInvoiceRequest,
    current: TokenData = Depends(require_permission("accounting.etax.generate")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    service = ETaxService(db)
    document = await service.issue_tax_invoice(current.company_id, current.branch_id, current.user_id, payload)
    return ok(service.serialize_document(document))


@router.post("/documents/credit-note", status_code=status.HTTP_201_CREATED)
async def issue_credit_note(
    payload: IssueCreditNoteRequest,
    current: TokenData = Depends(require_permission("accounting.etax.generate")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    service = ETaxService(db)
    document = await service.issue_credit_note(current.company_id, current.branch_id, current.user_id, payload)
    return ok(service.serialize_document(document))


@router.get("/documents/{document_id}")
async def get_document(
    document_id: uuid.UUID,
    current: TokenData = Depends(require_permission("accounting.invoice.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ETaxService(db)
    document = await service.get_document(document_id, current.company_id)
    return ok(service.serialize_document(document))


@router.get("/documents/{document_id}/xml")
async def get_xml(
    document_id: uuid.UUID,
    current: TokenData = Depends(require_permission("accounting.invoice.view")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = ETaxService(db)
    document = await service.get_document(document_id, current.company_id)
    xml_content = await service.get_xml(document_id, current.company_id)
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename=\"{document.document_number}.xml\""},
    )


@router.get("/documents/{document_id}/pdf")
async def get_pdf(
    document_id: uuid.UUID,
    current: TokenData = Depends(require_permission("accounting.invoice.view")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = ETaxService(db)
    document = await service.get_document(document_id, current.company_id)
    content, media_type = await generate_tax_invoice_pdf(
        doc=document,
        items=document.items,
        company_name=document.seller_name,
        company_address=document.seller_address or "-",
    )
    extension = "pdf" if media_type == "application/pdf" else "html"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=\"{document.document_number}.{extension}\""},
    )


@router.post("/documents/{document_id}/cancel")
async def cancel_document(
    document_id: uuid.UUID,
    payload: CancelDocumentRequest,
    current: TokenData = Depends(require_permission("accounting.etax.generate")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ETaxService(db)
    document = await service.cancel_document(document_id, current.company_id, current.user_id, payload)
    return ok(service.serialize_document(document))


@router.get("/vat-summary")
async def get_vat_summary(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    current: TokenData = Depends(require_permission("accounting.report.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ETaxService(db)
    return ok(await service.get_monthly_vat_summary(current.company_id, year, month))
