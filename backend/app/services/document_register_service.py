"""Read-only index of source records; not an issuance-time archive.

Never allocate numbers, recalculate tax, or fabricate historical snapshots here.
Purchase follows its operational source; AP/tax follow their existing legacy source.
"""
from datetime import date

from fastapi import HTTPException
from sqlalchemy import String, cast, literal, select

from app.database import AsyncSessionLocal
from app.dependencies import TokenData, legacy_model_session_factory_for
from app.models.etax import TaxDocument
from app.models.payable import APPayment, SupplierInvoice, WHTCertificate
from app.models.purchase import GoodsReceipt, PurchaseOrder
from app.models.credit_sales import CreditSaleDocument, KINDS


SOURCES = {
    "purchase_order": (PurchaseOrder, "po_number", "order_date", "total_amount", "status", "inventory.purchase.view"),
    "goods_receipt": (GoodsReceipt, "gr_number", "received_date", None, None, "inventory.purchase.view"),
    "supplier_invoice": (SupplierInvoice, "invoice_number", "invoice_date", "total_amount", "status", "accounting.payment.view"),
    "payment_voucher": (APPayment, "payment_number", "payment_date", "total_amount", None, "accounting.payment.view"),
    "wht_certificate": (WHTCertificate, "certificate_number", "issue_date", "wht_amount", None, "accounting.payment.view"),
    "sales_tax_document": (TaxDocument, "document_number", "issue_date", "total_amount", "status", "accounting.invoice.view"),
}
SOURCES.update({kind: (CreditSaleDocument, "number", "document_date", "total_amount", "status", "accounting.invoice.view") for kind in KINDS})


def check_register_access(current: TokenData, kind: str) -> None:
    if kind not in SOURCES:
        raise HTTPException(422, "Unknown document type")
    if "*" not in current.permissions and SOURCES[kind][5] not in current.permissions:
        raise HTTPException(403, "ไม่มีสิทธิ์ดูเอกสารประเภทนี้")
    # No company-wide aggregation or station-to-branch privilege expansion in v1.
    if current.branch_id is None:
        raise HTTPException(409, "กรุณาเลือกสาขาก่อนดูทะเบียนเอกสาร")
    if current.station_key:
        raise HTTPException(403, "ทะเบียนนี้ต้องใช้บริบทระดับสาขา ไม่ใช่จุดขาย")
    if kind in {"purchase_order", "goods_receipt"} and current.target_database == "takeaway":
        raise HTTPException(409, "ทะเบียนจัดซื้อ Takeaway ยังไม่เชื่อมกับทะเบียนนี้")


def register_statement(current: TokenData, kind: str, *, search: str = "",
                       date_from: date | None = None, date_to: date | None = None,
                       page: int = 1, limit: int = 25):
    check_register_access(current, kind)
    if page < 1 or not 1 <= limit <= 100 or len(search) > 100:
        raise HTTPException(422, "Invalid register pagination or search")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "วันที่เริ่มต้องไม่อยู่หลังวันที่สิ้นสุด")
    model, number, day, amount, status, _ = SOURCES[kind]
    statement = select(
        model.id, getattr(model, number).label("number"),
        getattr(model, day).label("document_date"),
        (cast(getattr(model, amount), String) if amount else literal(None)).label("amount"),
        (getattr(model, status) if status else literal("recorded")).label("status"),
        model.created_at,
    ).where(model.company_id == current.company_id, model.branch_id == current.branch_id)
    if kind in KINDS:
        statement = statement.where(model.kind == kind)
    if hasattr(model, "deleted_at"):
        statement = statement.where(model.deleted_at.is_(None))
    if search.strip():
        statement = statement.where(getattr(model, number).icontains(search.strip(), autoescape=True))
    if date_from:
        statement = statement.where(getattr(model, day) >= date_from)
    if date_to:
        statement = statement.where(getattr(model, day) <= date_to)
    return statement.order_by(getattr(model, day).desc(), model.id.desc()).offset((page - 1) * limit).limit(limit + 1)


def register_session_factory(current: TokenData, kind: str):
    check_register_access(current, kind)
    if kind in {"purchase_order", "goods_receipt"}:
        return legacy_model_session_factory_for(current)
    # Keep exactly the routing of payable.py and etax.py; don't silently migrate data.
    return AsyncSessionLocal


async def list_register(current: TokenData, kind: str, **filters):
    statement = register_statement(current, kind, **filters)
    factory = register_session_factory(current, kind)
    async with factory() as db:
        rows = (await db.execute(statement)).mappings().all()
    limit = filters.get("limit", 25)
    return {
        "items": [dict(row) for row in rows[:limit]],
        "has_more": len(rows) > limit,
        "page": filters.get("page", 1),
        "kind": kind,
        "company_id": current.company_id,
        "branch_id": current.branch_id,
        "source": "purchase_operational" if kind in {"purchase_order", "goods_receipt"} else "accounting_legacy",
        "evidence_mode": "live_source_reference",
        "historical_snapshot": False,
    }
