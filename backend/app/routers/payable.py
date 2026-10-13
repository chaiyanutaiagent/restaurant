from __future__ import annotations

from datetime import date
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, require_permission
from app.models.company import Company
from app.schemas.payable import (
    APPaymentAllocationRead,
    APPaymentRead,
    CreateAPPaymentRequest,
    SupplierInvoiceCreate,
    SupplierInvoiceListItem,
    SupplierInvoiceRead,
    WHTCertificateRead,
)
from app.services.payable_service import PayableService
from app.services.document_snapshot_service import evidence_notice, load_snapshot
from app.utils.business_documents import render_payment_voucher_html
from app.utils.pdf_generator import html_to_pdf_or_html, render_wht_certificate_html
from app.utils.pdf_generator import generate_payment_voucher_pdf, generate_wht_certificate_pdf

router = APIRouter(prefix="/api/v1/payable", tags=["payable"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


def check_write_branch(current: TokenData, branch_id: uuid.UUID) -> None:
    if current.branch_id is not None and current.branch_id != branch_id:
        raise HTTPException(status_code=403, detail="กรุณาสลับไปสาขาของเอกสารก่อนทำรายการ")


async def _get_company(db: AsyncSession, company_id: uuid.UUID) -> Company:
    company = await db.get(Company, company_id)
    if company is None:
        raise RuntimeError("Company not found")
    return company


@router.get("/invoices")
async def list_invoices(
    supplier_id: uuid.UUID | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    overdue_only: bool = Query(default=False),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    current: TokenData = Depends(require_permission("accounting.payment.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await PayableService(db).list_invoices(
        company_id=current.company_id,
        supplier_id=supplier_id,
        status=status_value,
        overdue_only=overdue_only,
        date_from=date_from,
        date_to=date_to,
        page=page,
        limit=limit,
    )
    data = [SupplierInvoiceListItem.model_validate(item).model_dump() for item in rows]
    return ok(data, meta={"total": total, "page": page, "limit": limit})


@router.post("/invoices", status_code=status.HTTP_201_CREATED)
async def create_invoice(
    payload: SupplierInvoiceCreate,
    current: TokenData = Depends(require_permission("accounting.payment.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    check_write_branch(current, payload.branch_id)
    invoice = await PayableService(db).create_invoice(current.company_id, current.user_id, payload)
    return ok(SupplierInvoiceRead.model_validate(invoice).model_dump())


@router.get("/invoices/{invoice_id}")
async def get_invoice(
    invoice_id: uuid.UUID,
    current: TokenData = Depends(require_permission("accounting.payment.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    invoice = await PayableService(db).get_invoice(invoice_id, current.company_id)
    return ok(SupplierInvoiceRead.model_validate(invoice).model_dump())


class CancelInvoiceRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


@router.post("/invoices/{invoice_id}/cancel")
async def cancel_invoice(
    invoice_id: uuid.UUID,
    payload: CancelInvoiceRequest,
    current: TokenData = Depends(require_permission("accounting.payment.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    source = await PayableService(db).get_invoice(invoice_id, current.company_id)
    check_write_branch(current, source.branch_id)
    invoice = await PayableService(db).cancel_invoice(invoice_id, current.company_id, current.user_id, payload.reason)
    return ok(SupplierInvoiceRead.model_validate(invoice).model_dump())


@router.get("/payments")
async def list_payments(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    current: TokenData = Depends(require_permission("accounting.payment.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await PayableService(db).list_payments(current.company_id, page, limit)
    data = [APPaymentRead.model_validate(item).model_dump() for item in rows]
    return ok(data, meta={"total": total, "page": page, "limit": limit})


@router.post("/payments", status_code=status.HTTP_201_CREATED)
async def create_payment(
    payload: CreateAPPaymentRequest,
    current: TokenData = Depends(require_permission("accounting.payment.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    check_write_branch(current, payload.branch_id)
    payment = await PayableService(db).create_payment(current.company_id, current.user_id, payload)
    return ok(APPaymentRead.model_validate(payment).model_dump())


@router.post("/payments/preview")
async def preview_payment(
    payload: CreateAPPaymentRequest,
    current: TokenData = Depends(require_permission("accounting.payment.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    check_write_branch(current, payload.branch_id)
    return ok(await PayableService(db).preview_payment(current.company_id, payload))


@router.get("/payments/{payment_id}")
async def get_payment(
    payment_id: uuid.UUID,
    current: TokenData = Depends(require_permission("accounting.payment.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    payment = await PayableService(db).get_payment(payment_id, current.company_id)
    return ok(APPaymentRead.model_validate(payment).model_dump())


@router.get("/payments/{payment_id}/voucher")
async def get_payment_voucher(
    payment_id: uuid.UUID,
    current: TokenData = Depends(require_permission("accounting.payment.view")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = PayableService(db)
    payment = await service.get_payment(payment_id, current.company_id)
    snapshot = await load_snapshot(db, current, "payment_voucher", payment, payment.id)
    if snapshot is not None:
        html = snapshot.rendered_html
    else:
        company = await _get_company(db, current.company_id)
        allocations = [APPaymentAllocationRead.model_validate(item) for item in payment.allocations]
        html = evidence_notice(render_payment_voucher_html(payment, allocations, company.name,
            company.address or "-", company.tax_id or "-"),
            "เอกสารเดิมไม่มีสำเนาข้อมูล ณ วันบันทึก — ข้อมูลผู้เกี่ยวข้องอาจเป็นข้อมูลปัจจุบัน")
    content, media_type = html_to_pdf_or_html(html)
    ext = "pdf" if media_type == "application/pdf" else "html"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=voucher_{payment.payment_number}.{ext}",
                 "Cache-Control": "private, no-store", "X-Document-Evidence": "issuance_snapshot" if snapshot else "legacy_live_profile",
                 "X-Document-SHA256": snapshot.content_sha256 if snapshot else "unavailable"},
    )


@router.get("/wht-certificates")
async def list_wht_certificates(
    supplier_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    current: TokenData = Depends(require_permission("accounting.payment.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await PayableService(db).list_wht_certificates(current.company_id, supplier_id, page, limit)
    data = [WHTCertificateRead.model_validate(item).model_dump() for item in rows]
    return ok(data, meta={"total": total, "page": page, "limit": limit})


@router.get("/wht-certificates/{cert_id}")
async def get_wht_certificate(
    cert_id: uuid.UUID,
    current: TokenData = Depends(require_permission("accounting.payment.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cert = await PayableService(db).get_wht_certificate(cert_id, current.company_id)
    return ok(WHTCertificateRead.model_validate(cert).model_dump())


@router.get("/wht-certificates/{cert_id}/pdf")
async def get_wht_certificate_pdf(
    cert_id: uuid.UUID,
    current: TokenData = Depends(require_permission("accounting.payment.view")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = PayableService(db)
    cert = await service.get_wht_certificate(cert_id, current.company_id)
    snapshot = await load_snapshot(db, current, "wht_certificate", cert, cert.payment_id)
    if snapshot is not None:
        html = snapshot.rendered_html
    else:
        company = await _get_company(db, current.company_id)
        html = evidence_notice(render_wht_certificate_html(cert, cert.supplier_name, cert.supplier_tax_id,
            company.name, company.tax_id or "-", company.address or "-"),
            "เอกสารเดิมไม่มีสำเนาข้อมูล ณ วันบันทึก — ข้อมูลผู้เกี่ยวข้องอาจเป็นข้อมูลปัจจุบัน")
    content, media_type = html_to_pdf_or_html(html)
    ext = "pdf" if media_type == "application/pdf" else "html"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={cert.certificate_number}.{ext}",
                 "Cache-Control": "private, no-store", "X-Document-Evidence": "issuance_snapshot" if snapshot else "legacy_live_profile",
                 "X-Document-SHA256": snapshot.content_sha256 if snapshot else "unavailable"},
    )


@router.get("/vat-return")
async def get_vat_return(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    current: TokenData = Depends(require_permission("accounting.report.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    report = await PayableService(db).get_vat_return_report(current.company_id, year, month)
    return ok(report.model_dump())
