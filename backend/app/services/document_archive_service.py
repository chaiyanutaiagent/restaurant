"""Scoped history and issuance/copy exports; no financial mutation endpoints."""
from fastapi import HTTPException
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.document_snapshot import DocumentEvent, DocumentSnapshot
from app.models.credit_sales import KINDS
from app.services.document_register_service import SOURCES, check_register_access
from app.services.document_snapshot_service import load_snapshot, snapshot_digest, evidence_notice, require_document_scope
from app.services.document_lifecycle_service import append_event
from app.utils.pdf_generator import html_to_pdf_or_html

RESOURCE = {"purchase_order": "PurchaseOrder", "goods_receipt": "GoodsReceipt", "supplier_invoice": "SupplierInvoice",
            "payment_voucher": "APPayment", "wht_certificate": "WHTCertificate", "sales_tax_document": "TaxDocument"}
RESOURCE.update({kind: "CreditSaleDocument" for kind in KINDS})


async def archive_source(db, current, kind, source_id, *, lock=False):
    check_register_access(current, kind)
    model = SOURCES[kind][0]
    query = select(model).where(model.id == source_id, model.company_id == current.company_id,
                                model.branch_id == current.branch_id)
    if kind in KINDS:
        query = query.where(model.kind == kind)
    if hasattr(model, "deleted_at"):
        query = query.where(model.deleted_at.is_(None))
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    source = await db.scalar(query)
    if source is None:
        raise HTTPException(404, "ไม่พบเอกสารในบริษัทและสาขาที่เลือก")
    return source


async def evidence_for(db, current, kind, source):
    require_document_scope(current, source)
    if kind in {"payment_voucher", "wht_certificate"}:
        return await load_snapshot(db, current, kind, source, source.id if kind == "payment_voucher" else source.payment_id)
    row = await db.scalar(select(DocumentSnapshot).where(
        DocumentSnapshot.company_id == current.company_id, DocumentSnapshot.branch_id == source.branch_id,
        DocumentSnapshot.document_kind == kind, DocumentSnapshot.source_id == source.id))
    if row is not None:
        if snapshot_digest(row) != row.content_sha256:
            raise HTTPException(409, "หลักฐานเอกสารไม่ผ่านการตรวจความครบถ้วน")
        return row
    expected = await db.scalar(select(DocumentEvent.id).where(
        DocumentEvent.company_id == current.company_id, DocumentEvent.branch_id == source.branch_id,
        DocumentEvent.document_kind == kind, DocumentEvent.source_id == source.id, DocumentEvent.action == "issued").limit(1))
    if expected:
        raise HTTPException(409, "หลักฐานที่ต้องมีสูญหาย ห้ามแทนด้วยข้อมูลปัจจุบัน")
    return None


async def history(db, current, kind, source_id, page=1):
    source = await archive_source(db, current, kind, source_id)
    snapshot = await evidence_for(db, current, kind, source)
    where = (DocumentEvent.company_id == current.company_id, DocumentEvent.branch_id == current.branch_id,
             DocumentEvent.document_kind == kind, DocumentEvent.source_id == source_id)
    rows = (await db.scalars(select(DocumentEvent).where(*where).order_by(DocumentEvent.sequence.desc()).offset((page - 1) * 25).limit(26))).all()
    original = await db.scalar(select(DocumentEvent.id).where(*where, DocumentEvent.action == "print_original").limit(1))
    # Old audit rows are labelled separately, not re-created as historical snapshots.
    legacy = (await db.scalars(select(AuditLog).where(AuditLog.company_id == current.company_id,
        AuditLog.branch_id == current.branch_id, AuditLog.resource == RESOURCE[kind],
        AuditLog.resource_id == str(source_id)).order_by(AuditLog.created_at.desc()).limit(25))).all() if page == 1 else []
    return {"company_id": current.company_id, "branch_id": current.branch_id,
        "number": getattr(source, SOURCES[kind][1]), "status": getattr(source, "status", "recorded"),
        "snapshot": None if snapshot is None else {"id": snapshot.id, "captured_at": snapshot.captured_at,
            "captured_by": snapshot.captured_by, "sha256": snapshot.content_sha256, "template_version": snapshot.template_version},
        "original_available": snapshot is not None and not original and getattr(source, "status", None) != "cancelled",
        "events": [{"sequence": e.sequence, "action": e.action, "actor_id": e.actor_id,
            "occurred_at": e.occurred_at, "reason": e.reason, "payload": e.payload} for e in rows[:25]],
        "has_more": len(rows) > 25,
        "legacy_audit": [{"action": e.action, "actor_id": e.user_id, "occurred_at": e.created_at} for e in legacy],
        "correction_policy": "แก้ร่างได้พร้อมเหตุผล; ออกแล้วห้ามแก้ทับ ให้ยกเลิก/ออกใหม่ หรือใบลดหนี้ผ่านระบบต้นทาง ไม่แก้ยอดจากทะเบียน",
    }


def copy_html(snapshot, source, variant="copy"):
    marker = "ต้นฉบับจากหลักฐานในระบบ" if variant == "original" else "สำเนา / COPY"
    if getattr(source, "status", None) == "cancelled":
        marker += " — ยกเลิกแล้ว / CANCELLED"
    marker += f" · SHA-256 {snapshot.content_sha256} · ไม่ใช่การรับรองเอกสารภาษี"
    return evidence_notice(snapshot.rendered_html, marker)


async def export_document(db, current, kind, source_id, variant):
    if variant not in {"original", "copy"}:
        raise HTTPException(422, "Invalid copy variant")
    source = await archive_source(db, current, kind, source_id, lock=True)
    snapshot = await evidence_for(db, current, kind, source)
    if snapshot is None:
        raise HTTPException(409, "เอกสารเก่าหรือฉบับร่างไม่มีหลักฐาน ณ วันออก ให้ใช้หน้าต้นทาง ไม่มีการสร้างหลักฐานย้อนหลัง")
    if variant == "original":
        if getattr(source, "status", None) == "cancelled":
            raise HTTPException(409, "เอกสารยกเลิกแล้วดาวน์โหลดได้เฉพาะสำเนา")
        existing = await db.scalar(select(DocumentEvent.id).where(
            DocumentEvent.company_id == current.company_id, DocumentEvent.document_kind == kind,
            DocumentEvent.source_id == source_id, DocumentEvent.action == "print_original").limit(1))
        if existing:
            raise HTTPException(409, "บันทึกการออกต้นฉบับแล้ว ให้เลือกสำเนา (หากดาวน์โหลดไม่สำเร็จก็ใช้สำเนา)")
    content, media_type = html_to_pdf_or_html(copy_html(snapshot, source, variant))
    event = await append_event(db, source, kind, f"print_{variant}", current.user_id,
        payload={"sha256": snapshot.content_sha256, "media_type": media_type})
    await db.commit()  # Export records only; never post stock, tax, payment or journal.
    return content, media_type, snapshot.document_number, snapshot.content_sha256, event.sequence
