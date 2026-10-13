"""Live AP/credit-sales aging, not a historical balance reconstruction.

Reads accounting's existing database, never operational wallets or POS totals.
Summary and page use one read-only repeatable-read snapshot.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import and_, case, func, literal, or_, select, text
from app.database import AsyncSessionLocal
from app.models.credit_sales import CreditSale, CreditSaleDocument
from app.models.payable import SupplierInvoice
from app.models.purchase import Supplier
from app.models.company import Company

PERMISSIONS = {"payable": "accounting.payment.view", "receivable": "accounting.invoice.view"}
BUCKETS = ("not_due", "due_today", "days_1_30", "days_31_60", "days_61_90", "days_91_plus")
WINDOWS = ("all", "overdue", "today", "next7", "next30")


def authorize(current, side):
    if side not in PERMISSIONS:
        raise HTTPException(422, "ประเภทหนี้ไม่ถูกต้อง")
    for permission in ("accounting.report.view", PERMISSIONS[side]):
        if "*" not in current.permissions and permission not in current.permissions:
            raise HTTPException(403, "ต้องมีสิทธิ์ดูรายงานบัญชีและเอกสารหนี้ประเภทนี้")
    if not current.branch_id or current.station_key:
        raise HTTPException(403, "เลือกสาขาก่อนดูรายงาน ไม่รองรับบริบทจุดขายหรือรวมทุกสาขา")


def base_statement(current, side):
    authorize(current, side)
    if side == "payable":
        m = SupplierInvoice
        return select(m.id, m.id.label("document_id"), m.invoice_number.label("number"),
            m.supplier_id.label("partner_id"), func.coalesce(Supplier.name, literal("ไม่พบชื่อผู้จำหน่าย")).label("partner_name"),
            m.invoice_date.label("document_date"), m.due_date, m.total_amount, m.paid_amount,
            m.remaining_amount.label("outstanding"), m.status,
            (m.remaining_amount != m.total_amount - m.paid_amount).label("balance_warning")
        ).outerjoin(Supplier, and_(Supplier.id == m.supplier_id, Supplier.company_id == m.company_id)).where(
            m.company_id == current.company_id, m.branch_id == current.branch_id,
            m.deleted_at.is_(None), m.status.in_(["unpaid", "partial"]), m.remaining_amount > 0)
    m, doc = CreditSale, CreditSaleDocument
    return select(m.id, doc.id.label("document_id"), func.coalesce(doc.number, m.description).label("number"),
        m.customer_id.label("partner_id"), m.buyer["name"].as_string().label("partner_name"),
        doc.document_date, m.due_date, m.total_amount, m.paid_amount,
        (m.total_amount - m.paid_amount).label("outstanding"), m.status,
        doc.id.is_(None).label("balance_warning")
    ).outerjoin(doc, and_(doc.sale_id == m.id, doc.company_id == m.company_id,
        doc.branch_id == m.branch_id, doc.kind == "customer_invoice")).where(
        m.company_id == current.company_id, m.branch_id == current.branch_id,
        m.status.in_(["invoiced", "partial"]), m.total_amount > m.paid_amount)


def aging_bucket(due, day):
    return case((due > day, "not_due"), (due == day, "due_today"),
        (due >= day - timedelta(days=30), "days_1_30"),
        (due >= day - timedelta(days=60), "days_31_60"),
        (due >= day - timedelta(days=90), "days_61_90"), else_="days_91_plus")


def filtered_source(current, side, day, *, search="", window="all", bucket="all"):
    if len(search) > 100 or window not in WINDOWS or bucket not in ("all", *BUCKETS):
        raise HTTPException(422, "ตัวกรองไม่ถูกต้อง")
    base = base_statement(current, side).subquery()
    query = select(base, aging_bucket(base.c.due_date, day).label("bucket"),
                   func.greatest(literal(day) - base.c.due_date, 0).label("days_overdue"))
    if search.strip():
        query = query.where(or_(base.c.number.icontains(search.strip(), autoescape=True),
                               base.c.partner_name.icontains(search.strip(), autoescape=True)))
    if window == "overdue":
        query = query.where(base.c.due_date < day)
    elif window == "today":
        query = query.where(base.c.due_date == day)
    elif window in {"next7", "next30"}:
        days = 7 if window == "next7" else 30
        query = query.where(base.c.due_date.between(day, day + timedelta(days=days)))
    if bucket != "all":
        query = query.where(aging_bucket(base.c.due_date, day) == bucket)
    return query.subquery()


async def report(current, side, *, search="", window="all", bucket="all", page=1, limit=25):
    if page < 1 or page > 10000 or not 1 <= limit <= 100:
        raise HTTPException(422, "หน้ารายงานไม่ถูกต้อง")
    generated = datetime.now(ZoneInfo("Asia/Bangkok"))
    day = generated.date()
    source = filtered_source(current, side, day, search=search, window=window, bucket=bucket)
    col = source.c
    def total(condition):
        return func.coalesce(func.sum(case((condition, col.outstanding), else_=0)), 0)
    totals = select(func.count().label("count"), func.coalesce(func.sum(col.outstanding), 0).label("outstanding"),
        total(col.due_date < day).label("overdue"), total(col.due_date == day).label("due_today"),
        total(col.due_date.between(day, day + timedelta(days=7))).label("next7"),
        total(col.due_date.between(day, day + timedelta(days=30))).label("next30"),
        func.coalesce(func.sum(case((col.balance_warning, 1), else_=0)), 0).label("warnings"),
        *[total(col.bucket == name).label("bucket_" + name) for name in BUCKETS])
    async with AsyncSessionLocal() as db:
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        if await db.scalar(select(Company.currency).where(Company.id == current.company_id)) != "THB":
            raise HTTPException(409, "รายงานรุ่นนี้รองรับบริษัทที่ใช้เงินบาทเท่านั้น")
        summary = dict((await db.execute(totals)).mappings().one())
        rows = (await db.execute(select(source).order_by(col.due_date, col.id)
            .offset((page - 1) * limit).limit(limit))).mappings().all()
        partners = (await db.execute(select(col.partner_id, col.partner_name,
            func.sum(col.outstanding).label("outstanding"), func.count().label("count"))
            .group_by(col.partner_id, col.partner_name).order_by(func.sum(col.outstanding).desc(), col.partner_id)
            .limit(20))).mappings().all()
    return {"company_id": current.company_id, "branch_id": current.branch_id, "side": side,
        "generated_at": generated, "aging_date": day, "timezone": "Asia/Bangkok", "currency": "THB",
        "basis": "current_open_balances_not_historical", "summary": summary,
        "items": [dict(row) for row in rows], "partners": [dict(row) for row in partners], "partner_limit": 20,
        "page": page, "limit": limit, "has_more": page * limit < summary["count"],
        "filters": {"search": search, "window": window, "bucket": bucket},
        "document_kind": "supplier_invoice" if side == "payable" else "customer_invoice"}
