"""Evidence only. All captures/events share the caller's transaction and database."""
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import func, inspect, select, text

from app.models.company import Company
from app.models.document_snapshot import DocumentEvent, DocumentSnapshot
from app.services.document_snapshot_service import fields, json_value, snapshot_digest, evidence_notice
from app.utils.business_documents import render_po_html, render_gr_html, document, money


def serial(value):
    return json.loads(json.dumps(value, default=json_value))


def columns(row):
    return fields(row, " ".join(column.key for column in inspect(type(row)).columns))


async def document_lock(db, company_id, kind, source_id):
    key = int.from_bytes(hashlib.sha256(f"document:{company_id}:{kind}:{source_id}".encode()).digest()[:8], "big", signed=True)
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


async def append_event(db, source, kind, action, actor_id, reason=None, payload=None):
    await document_lock(db, source.company_id, kind, source.id)
    sequence = (await db.scalar(select(func.max(DocumentEvent.sequence)).where(
        DocumentEvent.company_id == source.company_id, DocumentEvent.document_kind == kind,
        DocumentEvent.source_id == source.id))) or 0
    event = DocumentEvent(company_id=source.company_id, branch_id=source.branch_id,
        document_kind=kind, source_id=source.id, sequence=sequence + 1, action=action,
        actor_id=actor_id, occurred_at=datetime.now(timezone.utc), reason=reason,
        payload=serial(payload or {}))
    db.add(event)
    await db.flush()
    return event


def require_reason(reason):
    if not reason or not reason.strip() or len(reason) > 1000:
        raise HTTPException(422, "กรุณาระบุเหตุผล 1–1,000 ตัวอักษร")
    return reason.strip()


async def capture(db, source, kind, number, actor_id, payload, html):
    await document_lock(db, source.company_id, kind, source.id)
    row = DocumentSnapshot(company_id=source.company_id, branch_id=source.branch_id,
        document_kind=kind, source_id=source.id, document_number=number,
        template_version="document-lifecycle-1", captured_by=actor_id,
        captured_at=datetime.now(timezone.utc), payload=serial(payload), rendered_html=html)
    row.content_sha256 = snapshot_digest(row)
    db.add(row)
    await db.flush()
    await append_event(db, source, kind, "issued", actor_id,
        payload={"snapshot_id": row.id, "sha256": row.content_sha256, "number": number})
    return row


async def company_for(db, source):
    company = await db.get(Company, source.company_id)
    if company is None:
        raise HTTPException(409, "ไม่พบบริษัทสำหรับเก็บหลักฐานเอกสาร")
    return company


async def po_revision(db, po, actor_id, action, reason=None):
    await db.flush()
    await db.refresh(po, attribute_names=[c.key for c in inspect(type(po)).columns] + ["items", "supplier"])
    return await append_event(db, po, "purchase_order", action, actor_id, reason,
        {"source": columns(po), "items": [columns(item) for item in po.items]})


async def capture_po(db, po, actor_id):
    await db.flush()
    await db.refresh(po, attribute_names=[c.key for c in inspect(type(po)).columns])
    company = await company_for(db, po)
    return await capture(db, po, "purchase_order", po.po_number, actor_id,
        {"company": fields(company, "id name tax_id address"), "source": columns(po),
         "supplier": fields(po.supplier, "id name tax_id address branch_code payment_term_days"),
         "items": [columns(item) for item in po.items]},
        render_po_html(po, company.name, company.address or "-", company.tax_id or "-"))


async def capture_gr(db, gr, actor_id):
    company = await company_for(db, gr)
    po = gr.purchase_order
    return await capture(db, gr, "goods_receipt", gr.gr_number, actor_id,
        {"company": fields(company, "id name tax_id address"), "source": columns(gr),
         "po_number": po.po_number, "supplier": fields(po.supplier, "id name tax_id address"),
         "location": fields(gr.location, "id name"), "receiver": fields(gr.receiver, "id display_name username"),
         "items": [dict(columns(item), product=fields(item.po_item, "product_name sku unit_code")) for item in gr.items]},
        render_gr_html(gr, po, company.name, company.address or "-", company.tax_id or "-"))


async def capture_invoice(db, invoice, supplier, actor_id):
    company = await company_for(db, invoice)
    html = document("ทะเบียนรับใบแจ้งหนี้ผู้จำหน่าย (ไม่ใช่เอกสารที่ผู้จำหน่ายออก)",
        invoice.invoice_number, company.name, company.address or "-", company.tax_id or "-",
        [("วันที่ใบแจ้งหนี้", invoice.invoice_date), ("กำหนดจ่าย", invoice.due_date)],
        [("ผู้จำหน่าย", supplier.name), ("เลขภาษี", supplier.tax_id), ("อ้างอิง", invoice.supplier_ref)], "",
        [("มูลค่าก่อน VAT", invoice.subtotal), ("VAT", invoice.vat_amount), ("ยอดตามเอกสาร", invoice.total_amount)],
        ("ผู้บันทึก", "ผู้ตรวจสอบ", "ผู้อนุมัติ"), invoice.note)
    return await capture(db, invoice, "supplier_invoice", invoice.invoice_number, actor_id,
        {"company": fields(company, "id name tax_id address"), "source": columns(invoice),
         "supplier": fields(supplier, "id name tax_id address")}, html)


async def capture_tax(db, doc, actor_id):
    await db.flush()
    await db.refresh(doc, attribute_names=[c.key for c in inspect(type(doc)).columns] + ["items"])
    # Preserve stored seller/buyer, tax values and XML; never fetch current profiles.
    # Reference rendering is intentionally not certification of an official tax form.
    from app.utils.pdf_generator import render_tax_invoice_html
    html = render_tax_invoice_html(doc, doc.items, doc.seller_name, doc.seller_address or "-")
    if doc.is_synthetic or doc.watermark:
        html = evidence_notice(html, doc.watermark or "ข้อมูลจำลอง UAT")
    row = await capture(db, doc, "sales_tax_document", doc.document_number, actor_id,
        {"source": columns(doc), "items": [columns(item) for item in doc.items]}, html)
    if doc.original_document_id:
        from app.models.etax import TaxDocument
        original = await db.get(TaxDocument, doc.original_document_id)
        if original is None or original.company_id != doc.company_id or original.branch_id != doc.branch_id:
            raise HTTPException(409, "เอกสารปรับปรุงต้องอ้างอิงบริษัทและสาขาเดียวกัน")
        await append_event(db, original, "sales_tax_document", "credit_note_linked", actor_id,
            doc.reason, {"document_id": doc.id, "number": doc.document_number})
    return row


async def next_number(db, prefix, model, field, target_date):
    """Global unique source constraints require a global, stable daily lock."""
    day_prefix = f"{prefix}{target_date:%Y%m%d}-"
    await document_lock(db, "global", "number", day_prefix)
    values = (await db.scalars(select(field).where(field.like(f"{day_prefix}%")))).all()
    highest = max((int(value[len(day_prefix):]) for value in values if value[len(day_prefix):].isdigit()), default=0)
    return f"{day_prefix}{highest + 1:04d}"
