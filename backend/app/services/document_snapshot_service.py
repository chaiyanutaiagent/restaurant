"""Capture AP evidence inside the payment transaction; never backfill old profiles."""
from datetime import date, datetime, timezone
from decimal import Decimal
from html import escape
from types import SimpleNamespace
import hashlib
import json
import re
import uuid

from fastapi import HTTPException
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.company import Company
from app.models.document_snapshot import DocumentSnapshot
from app.utils.business_documents import render_payment_voucher_html
from app.utils.pdf_generator import render_wht_certificate_html

TEMPLATE_VERSION = "ap-issuance-evidence-1"


def json_value(value):
    if isinstance(value, (Decimal, uuid.UUID)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Unsupported snapshot value: {type(value).__name__}")


def fields(obj, names):
    return {name: getattr(obj, name) for name in names.split()}


def snapshot_digest(row):
    envelope = dict(company_id=row.company_id, branch_id=row.branch_id,
                    kind=row.document_kind, source_id=row.source_id,
                    document_number=row.document_number, template_version=row.template_version,
                    captured_at=row.captured_at, captured_by=row.captured_by,
                    payload=row.payload, rendered_html=row.rendered_html)
    return hashlib.sha256(json.dumps(envelope, default=json_value, sort_keys=True,
                                     ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def evidence_notice(html: str, message: str) -> str:
    # No scripts or remote resources are introduced; message is always escaped.
    return html.replace("</body>", f'<p style="margin-top:16px;font-size:10px;color:#666">{escape(message)}</p></body>')


def make_payment_snapshots(company, payment, allocations, invoices, certificates, actor_id):
    captured_at = datetime.now(timezone.utc)
    party = fields(company, "id name tax_id address")
    lines = []
    for allocation in allocations:
        invoice = invoices[allocation.invoice_id]
        line = fields(allocation, "invoice_id allocated_amount wht_amount wht_rate wht_type")
        line.update(invoice_number=invoice.invoice_number, supplier_name=invoice.supplier.name,
                    supplier=fields(invoice.supplier, "id name tax_id address"))
        lines.append(line)
    common = dict(company_id=payment.company_id, branch_id=payment.branch_id,
                  captured_at=captured_at, captured_by=actor_id, template_version=TEMPLATE_VERSION)
    payment_data = fields(payment, "id payment_number payment_date payment_method bank_account reference_no total_amount note")
    voucher_html = render_payment_voucher_html(payment, [SimpleNamespace(**line) for line in lines],
                                              company.name, company.address or "-", company.tax_id or "-")
    entries = [("payment_voucher", payment.id, payment.payment_number,
                dict(company=party, payment=payment_data, allocations=lines), voucher_html)]
    suppliers = {invoice.supplier_id: invoice.supplier for invoice in invoices.values()}
    for cert in certificates:
        supplier = suppliers[cert.supplier_id]
        payload = dict(company=party, supplier=fields(supplier, "id name tax_id address"),
                       certificate=fields(cert, "id payment_id supplier_id certificate_number issue_date wht_type wht_rate base_amount wht_amount income_type"))
        html = render_wht_certificate_html(cert, supplier.name, supplier.tax_id, company.name,
                                           company.tax_id or "-", company.address or "-")
        # Freeze self-contained template; installed Thai fonts render without Google fetches.
        html = re.sub(r"@import url\('[^']*'\);", "", html)
        html = html.replace("font-family: 'Sarabun', sans-serif", "font-family: 'Noto Sans Thai', 'Sarabun', sans-serif")
        entries.append(("wht_certificate", cert.id, cert.certificate_number, payload, html))
    rows = []
    for kind, source_id, number, payload, html in entries:
        row = DocumentSnapshot(**common, document_kind=kind, source_id=source_id, document_number=number,
            payload=json.loads(json.dumps(payload, default=json_value)),
            rendered_html=evidence_notice(html, "สำเนาข้อมูล ณ เวลาบันทึกการจ่าย ไม่ใช่การรับรองรูปแบบเอกสารภาษี"))
        row.content_sha256 = snapshot_digest(row)
        rows.append(row)
    return rows


async def capture_payment_snapshots(db, payment, allocations, invoices, certificates, actor_id):
    company = await db.get(Company, payment.company_id)
    if company is None:
        raise HTTPException(409, "ไม่พบข้อมูลบริษัทสำหรับเก็บหลักฐานเอกสาร")
    rows = make_payment_snapshots(company, payment, allocations, invoices, certificates, actor_id)
    db.add_all(rows)
    await db.flush()  # Failure rolls back the entire payment; no independent commit.
    from app.services.document_lifecycle_service import append_event
    for row in rows:
        await append_event(db, payment if row.document_kind == "payment_voucher" else next(c for c in certificates if c.id == row.source_id),
            row.document_kind, "issued", actor_id, payload={"snapshot_id": row.id, "sha256": row.content_sha256})
    return rows


def require_document_scope(current, source):
    if source.company_id != current.company_id or current.station_key:
        raise HTTPException(403, "ไม่มีสิทธิ์ดาวน์โหลดเอกสารในบริบทนี้")
    if current.branch_id is not None:
        if source.branch_id != current.branch_id:
            raise HTTPException(403, "กรุณาสลับไปสาขาของเอกสารก่อนดาวน์โหลด")
    elif "*" not in current.permissions and "company" not in current.scope_types:
        raise HTTPException(403, "ต้องเลือกสาขาหรือมีสิทธิ์ขอบเขตบริษัท")


async def load_snapshot(db, current, kind, source, payment_id):
    require_document_scope(current, source)
    row = await db.scalar(select(DocumentSnapshot).where(
        DocumentSnapshot.company_id == current.company_id,
        DocumentSnapshot.branch_id == source.branch_id,
        DocumentSnapshot.document_kind == kind,
        DocumentSnapshot.source_id == source.id,
    ))
    if row is not None:
        if snapshot_digest(row) != row.content_sha256:
            raise HTTPException(409, "หลักฐานเอกสารไม่ผ่านการตรวจความครบถ้วน กรุณาติดต่อผู้ดูแล")
        return row
    # New payments must not silently fall back to mutable profiles if evidence is missing.
    receipts = (await db.scalars(select(AuditLog).where(
        AuditLog.company_id == current.company_id,
        AuditLog.branch_id == source.branch_id,
        AuditLog.action == "accounting.payment.request",
        AuditLog.new_value["payment_id"].as_string() == str(payment_id),
    ))).all()
    if any((receipt.new_value or {}).get("document_snapshot_version") == 1 for receipt in receipts):
        raise HTTPException(409, "ไม่พบหลักฐานที่ต้องมีสำหรับเอกสารนี้ ห้ามพิมพ์จากข้อมูลปัจจุบันแทน")
    return None
