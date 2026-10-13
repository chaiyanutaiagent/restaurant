"""UAT credit sales. One transaction per action; no POS replay or fiscal issuance.

Full delivery only; partial collections. Goods use the existing restaurant stock
source only. Production is deliberately blocked pending accounting acceptance.
"""
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from uuid import UUID
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import inspect, or_, select
from app.config import settings
from app.database import AsyncSessionLocal, active_restaurant_service_session_factory
from app.models.branch import Branch
from app.models.company import Company
from app.models.crm import Customer
from app.models.credit_sales import CreditSale, CreditSaleDocument
from app.models.product import Product, ProductVariant
from app.models.stock import StockBalance, StockLocation
from app.models.tax_operations import TaxPeriod
from app.services.accounting_service import AccountingService, q2
from app.services.document_lifecycle_service import append_event, capture, columns, document_lock, next_number, serial
from app.services.document_snapshot_service import evidence_notice
from app.services.stock_service import StockService
from app.utils.business_documents import document, money, text
from app.utils.posting_rules import PostingLine

TITLES = {"sales_quotation": "ใบเสนอราคา", "sales_delivery": "ใบส่งสินค้า / ส่งมอบบริการ",
          "customer_invoice": "ใบแจ้งหนี้ลูกค้า", "billing_notice": "ใบวางบิล", "customer_receipt": "ใบรับเงิน"}
PREFIXES = dict(zip(TITLES, ("QT", "DN", "CI", "BN", "CR")))


def today():
    return datetime.now(ZoneInfo("Asia/Bangkok")).date()


def fingerprint(payload):
    return hashlib.sha256(json.dumps(serial(payload), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def check_access(current, permission="accounting.invoice.view"):
    host = urlparse(settings.saas_public_base_url).hostname or ""
    if settings.environment == "production" or not (host.startswith("uat-") or host in {"localhost", "127.0.0.1"}):
        raise HTTPException(403, "ระบบขายเชื่อชุดนี้เปิดเฉพาะ UAT ยังไม่อนุมัติ Production")
    if "*" not in current.permissions and permission not in current.permissions:
        raise HTTPException(403, "ไม่มีสิทธิ์ทำรายการขายเชื่อนี้")
    if not current.branch_id or current.station_key:
        raise HTTPException(403, "กรุณาเลือกบริบทสาขา ไม่ใช่จุดขาย")


def line_amounts(product, quantity, vat_registered):
    price = Decimal(product.selling_price)
    rate = Decimal(product.vat_rate) if vat_registered and product.vat_type != "exempt" else Decimal(0)
    if price <= 0 or rate < 0 or rate > 100 or product.vat_type not in {"included", "excluded", "exempt"}:
        raise HTTPException(409, "กรุณาตรวจราคาและการตั้งค่า VAT ของสินค้า")
    gross = q2(price * quantity)
    base = q2(gross / (1 + rate / 100)) if product.vat_type == "included" else gross
    tax = gross - base if product.vat_type == "included" else q2(base * rate / 100)
    return base, tax, base + tax


async def scoped_sale(db, current, sale_id, lock=False):
    check_access(current)
    query = select(CreditSale).where(CreditSale.id == sale_id, CreditSale.company_id == current.company_id,
                                    CreditSale.branch_id == current.branch_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = await db.scalar(query)
    if row is None:
        raise HTTPException(404, "ไม่พบรายการในบริษัทและสาขานี้")
    return row


async def detail(db, current, sale_id):
    sale = await scoped_sale(db, current, sale_id)
    docs = (await db.scalars(select(CreditSaleDocument).where(CreditSaleDocument.sale_id == sale.id,
        CreditSaleDocument.company_id == current.company_id, CreditSaleDocument.branch_id == current.branch_id)
        .order_by(CreditSaleDocument.created_at, CreditSaleDocument.id))).all()
    return dict(columns(sale), outstanding=q2(sale.total_amount - sale.paid_amount),
                documents=[columns(d) for d in docs])


async def create(db, current, payload):
    check_access(current, "accounting.invoice.create")
    digest = fingerprint(payload.model_dump())
    await document_lock(db, current.company_id, "credit_create", payload.request_key)
    existing = await db.scalar(select(CreditSale).where(CreditSale.company_id == current.company_id,
                                                      CreditSale.request_key == payload.request_key))
    if existing:
        if existing.branch_id != current.branch_id or existing.request_hash != digest:
            raise HTTPException(409, "รหัสคำขอนี้ถูกใช้กับข้อมูลอื่นแล้ว")
        return await detail(db, current, existing.id)
    if payload.due_date < today():
        raise HTTPException(422, "กำหนดชำระต้องไม่ย้อนหลัง")
    company = await db.get(Company, current.company_id)
    branch = await db.scalar(select(Branch).where(Branch.id == current.branch_id, Branch.company_id == current.company_id,
                                                Branch.deleted_at.is_(None), Branch.is_active.is_(True)))
    customer = await db.scalar(select(Customer).where(Customer.id == payload.customer_id,
        Customer.company_id == current.company_id, Customer.deleted_at.is_(None), Customer.is_active.is_(True),
        Customer.is_blacklisted.is_(False)))
    if not company or company.currency != "THB" or not branch or not customer:
        raise HTTPException(409, "ตรวจบริษัท สาขา ลูกค้า และสกุลเงินบาทก่อนสร้างเอกสาร")
    if company.tax_id and customer.tax_id and company.tax_id.strip() == customer.tax_id.strip():
        raise HTTPException(409, "บริษัทเดียวกันให้ใช้โอนสินค้าภายใน ไม่สร้างยอดขายเชื่อ")
    buyer_company = await db.scalar(select(Company.id).where(Company.tax_id == customer.tax_id,
        Company.id != company.id).limit(1)) if customer.tax_id else None
    ids = [i.product_id for i in payload.items]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "รวมจำนวนสินค้ารหัสเดียวกันเป็นหนึ่งรายการ")
    products = (await db.scalars(select(Product).where(Product.id.in_(ids), Product.company_id == current.company_id,
        Product.deleted_at.is_(None), Product.is_active.is_(True), Product.is_for_sale.is_(True)))).all()
    if len(products) != len(ids):
        raise HTTPException(422, "มีสินค้าที่ไม่พร้อมขายหรือไม่ได้อยู่ในบริษัทนี้")
    variants = await db.scalar(select(ProductVariant.id).where(ProductVariant.product_id.in_(ids),
        ProductVariant.deleted_at.is_(None)).limit(1))
    if variants:
        raise HTTPException(409, "ขายเชื่อรุ่นนี้ยังไม่รองรับสินค้ามีตัวเลือกย่อย")
    mapping = {p.id: p for p in products}
    items = []
    for line in payload.items:
        p = mapping[line.product_id]
        if p.product_type not in {"simple", "service"}:
            raise HTTPException(409, "รุ่นนี้รองรับสินค้าปกติและบริการ ไม่รองรับชุดสินค้า/สูตรผลิต")
        base, vat, total = line_amounts(p, line.quantity, company.vat_registered)
        stocked = p.product_type != "service" and p.inventory_role != "not_stocked"
        if stocked and (current.target_database not in {None, "legacy", "restaurant"} or
                        active_restaurant_service_session_factory() is not AsyncSessionLocal):
            raise HTTPException(409, "ยังไม่เปิดขายเชื่อสินค้าจากฐานข้อมูลแยก ใช้ระบบต้นทาง ห้ามเปลี่ยนแหล่งสต๊อก")
        items.append(serial(dict(product_id=p.id, sku=p.sku, name=p.name, quantity=line.quantity,
            unit_price=p.selling_price, unit_id=p.unit_id, vat_type=p.vat_type,
            vat_rate=p.vat_rate if company.vat_registered else 0, stocked=stocked,
            revenue_account="4002" if p.product_type == "service" else "4001",
            subtotal=base, vat_amount=vat, total_amount=total)))
    total = sum((Decimal(i["total_amount"]) for i in items), Decimal(0))
    if total <= 0 or total > Decimal("999999999.99"):
        raise HTTPException(422, "ยอดเอกสารต้องมากกว่าศูนย์และไม่เกินขีดจำกัด")
    sale = CreditSale(company_id=company.id, branch_id=current.branch_id, customer_id=customer.id,
        request_key=payload.request_key, request_hash=digest, description=payload.description,
        due_date=payload.due_date, transaction_type="intercompany_sale" if buyer_company else "external_sale",
        seller=serial({"name": company.name, "tax_id": company.tax_id, "address": company.address}),
        buyer=serial({"name": customer.full_name, "tax_id": customer.tax_id, "address": customer.address,
                      "customer_id": customer.id, "company_id": buyer_company}),
        items=items, subtotal=sum(Decimal(i["subtotal"]) for i in items),
        vat_amount=sum(Decimal(i["vat_amount"]) for i in items), total_amount=total, created_by=current.user_id)
    db.add(sale)
    await db.flush()
    await append_event(db, sale, "credit_sale", "draft_created", current.user_id, payload.description,
                       {"source": columns(sale)})
    await db.commit()
    return await detail(db, current, sale.id)


async def issue(db, current, sale, kind, key, digest, details, amount=None):
    row = CreditSaleDocument(company_id=sale.company_id, branch_id=sale.branch_id, sale_id=sale.id,
        kind=kind, number=await next_number(db, PREFIXES[kind], CreditSaleDocument, CreditSaleDocument.number, today()),
        document_date=today(), total_amount=sale.total_amount if amount is None else amount,
        request_key=key, request_hash=digest, details=serial(details), created_by=current.user_id)
    db.add(row)
    await db.flush()
    table = '<table><thead><tr><th>รายการ</th><th>จำนวน</th><th>ราคา</th><th>รวม</th></tr></thead><tbody>'
    table += ''.join(f'<tr><td>{text(i["name"])}</td><td>{text(i["quantity"])}</td><td>{money(i["unit_price"])}</td><td>{money(i["total_amount"])}</td></tr>' for i in sale.items)
    table += '</tbody></table>'
    html = document(TITLES[kind], row.number, sale.seller["name"], sale.seller.get("address") or "-",
        sale.seller.get("tax_id") or "-", [("วันที่", today()), ("กำหนดชำระ", sale.due_date), ("อ้างอิง", sale.id)],
        [("ลูกค้า", sale.buyer["name"]), ("เลขภาษี", sale.buyer.get("tax_id")), ("ที่อยู่", sale.buyer.get("address")),
         *[(k, v) for k, v in details.items()]], table,
        [("ก่อน VAT", sale.subtotal), ("VAT ตามข้อมูลทดสอบ", sale.vat_amount), ("ยอดเอกสารนี้", row.total_amount)],
        ("ผู้จัดทำ", "ผู้อนุมัติ", "ผู้รับเอกสาร"), sale.description)
    await capture(db, row, kind, row.number, current.user_id,
        {"sale": columns(sale), "document": columns(row)},
        evidence_notice(html, "UAT — เอกสารทดสอบ ไม่ใช่ใบกำกับภาษี ห้ามใช้ยื่นภาษี"))
    await append_event(db, sale, "credit_sale", kind, current.user_id, details.get("reason"),
                       {"document_id": row.id, "number": row.number})
    return row


async def period_open(db, current):
    day = today()
    periods = (await db.scalars(select(TaxPeriod).where(TaxPeriod.company_id == current.company_id,
        TaxPeriod.period_year.in_([day.year, day.year + 543]), TaxPeriod.period_month == day.month,
        or_(TaxPeriod.branch_id.is_(None), TaxPeriod.branch_id == current.branch_id)).with_for_update())).all()
    if any(p.status in {"review", "closed", "locked"} for p in periods):
        raise HTTPException(409, "งวดอยู่ระหว่างตรวจหรือปิดแล้ว ไม่อนุญาตลงบัญชี")


async def deliver_stock(db, current, sale, location_id):
    lines = sorted((i for i in sale.items if i["stocked"]), key=lambda i: i["product_id"])
    if not lines:
        return Decimal(0), []
    if current.target_database not in {None, "legacy", "restaurant"} or active_restaurant_service_session_factory() is not AsyncSessionLocal:
        raise HTTPException(409, "แหล่งข้อมูลสต๊อกไม่ตรงกับเอกสาร ไม่อนุญาตตัดสต๊อก")
    loc = await db.scalar(select(StockLocation).where(StockLocation.id == location_id,
        StockLocation.company_id == current.company_id, StockLocation.branch_id == current.branch_id,
        StockLocation.deleted_at.is_(None), StockLocation.is_active.is_(True)))
    if not loc:
        raise HTTPException(422, "เลือกคลังที่เปิดใช้งานในสาขานี้")
    cost, movements = Decimal(0), []
    for item in lines:
        balances = (await db.scalars(select(StockBalance).where(StockBalance.company_id == current.company_id,
            StockBalance.branch_id == current.branch_id, StockBalance.location_id == loc.id,
            StockBalance.product_id == UUID(item["product_id"]), StockBalance.variant_id.is_(None))
            .with_for_update().execution_options(populate_existing=True))).all()
        qty = Decimal(item["quantity"])
        if len(balances) != 1 or balances[0].qty_available < qty:
            raise HTTPException(409, f'สต๊อกพร้อมใช้ไม่เพียงพอหรือซ้ำ: {item["name"]}')
        balance = balances[0]
        cost += q2(qty * balance.cost_per_unit)
        movement = await StockService(db)._record_movement(balance, "issue", -qty, current.user_id,
            reference_type="credit_sale", reference_id=str(sale.id), note="UAT credit delivery",
            suppress_low_stock_events=True)
        movements.append(str(movement.id))
    return cost, movements


async def action(db, current, sale_id, action_name, payload):
    permission = {"approve": "accounting.invoice.approve", "deliver": "accounting.invoice.create",
                  "bill": "accounting.invoice.create", "receive": "accounting.payment.create",
                  "cancel": "accounting.invoice.create"}[action_name]
    check_access(current, permission)
    sale = await scoped_sale(db, current, sale_id, lock=True)
    digest = fingerprint({"sale_id": sale_id, "action": action_name, **payload.model_dump()})
    await document_lock(db, current.company_id, "credit_action", payload.request_key)
    existing = await db.scalar(select(CreditSaleDocument).where(CreditSaleDocument.company_id == current.company_id,
                                                              CreditSaleDocument.request_key == payload.request_key))
    if existing:
        if existing.sale_id != sale.id or existing.request_hash != digest:
            raise HTTPException(409, "คำขอเดิมมีข้อมูลไม่ตรงกัน")
        return await detail(db, current, sale.id)
    data = {"reason": payload.reason}
    if action_name == "approve":
        if sale.status != "draft":
            raise HTTPException(409, "อนุมัติได้เฉพาะร่าง")
        if sale.created_by == current.user_id:
            raise HTTPException(403, "ผู้อนุมัติต้องไม่ใช่ผู้สร้างรายการ")
        sale.status, sale.approved_by = "approved", current.user_id
        await db.flush()
        await db.refresh(sale)
        await issue(db, current, sale, "sales_quotation", payload.request_key, digest, data)
    elif action_name == "cancel":
        if sale.status not in {"draft", "approved"}:
            raise HTTPException(409, "ส่งมอบแล้วห้ามยกเลิกทับ ต้องใช้กระบวนการคืนสินค้า/ลดหนี้ซึ่งยังไม่เปิดในรุ่นนี้")
        sale.status = "cancelled"
        quotes = (await db.scalars(select(CreditSaleDocument).where(CreditSaleDocument.sale_id == sale.id))).all()
        for quote in quotes:
            quote.status = "cancelled"
            await append_event(db, quote, quote.kind, "cancelled", current.user_id, payload.reason)
        await append_event(db, sale, "credit_sale", "cancelled", current.user_id, payload.reason)
    elif action_name == "deliver":
        if sale.status != "approved" or sale.due_date < today():
            raise HTTPException(409, "ต้องอนุมัติและกำหนดชำระยังไม่หมดอายุก่อนส่งมอบ")
        if any(i["stocked"] for i in sale.items):
            check_access(current, "inventory.stock.adjust")
        await period_open(db, current)
        cost, movements = await deliver_stock(db, current, sale, payload.location_id)
        lines = [PostingLine("1103", sale.total_amount, Decimal(0), "ลูกหนี้ขายเชื่อ UAT")]
        for code in ("4001", "4002"):
            revenue = sum((Decimal(i["subtotal"]) for i in sale.items if i["revenue_account"] == code), Decimal(0))
            if revenue:
                lines.append(PostingLine(code, Decimal(0), revenue, "รายได้ขายเชื่อ UAT"))
        if sale.vat_amount:
            lines.append(PostingLine("2102", Decimal(0), sale.vat_amount, "VAT จำลอง UAT รอบัญชีตรวจ"))
        if cost:
            lines += [PostingLine("5001", cost, Decimal(0), "ต้นทุนส่งมอบ"), PostingLine("1105", Decimal(0), cost, "ตัดสินค้าคงคลัง")]
        entry = await AccountingService(db)._post_entry(current.company_id, current.branch_id, current.user_id,
            today(), "credit_sale", "UAT credit sale delivery", lines, "credit_sale", str(sale.id))
        sale.status = "invoiced"
        await db.flush()
        await db.refresh(sale)
        delivery = await issue(db, current, sale, "sales_delivery", payload.request_key, digest,
            dict(data, received_by=payload.received_by, stock_movements=movements, journal_id=str(entry.id)))
        # Deterministic child idempotency key; both documents and accounting commit together.
        from uuid import uuid5, NAMESPACE_URL
        await issue(db, current, sale, "customer_invoice", uuid5(NAMESPACE_URL, f"credit-invoice:{sale.id}"), digest,
            dict(data, delivery_number=delivery.number, journal_id=str(entry.id)))
    elif action_name == "bill":
        if sale.status not in {"invoiced", "partial"}:
            raise HTTPException(409, "วางบิลได้หลังแจ้งหนี้และมียอดค้าง")
        prior = await db.scalar(select(CreditSaleDocument.id).where(CreditSaleDocument.sale_id == sale.id,
                                                                  CreditSaleDocument.kind == "billing_notice"))
        if prior:
            raise HTTPException(409, "มีใบวางบิลแล้ว ให้ดาวน์โหลดสำเนา ไม่สร้างใบซ้ำ")
        await issue(db, current, sale, "billing_notice", payload.request_key, digest, data,
                    amount=q2(sale.total_amount - sale.paid_amount))
    elif action_name == "receive":
        if sale.status not in {"invoiced", "partial"} or payload.amount > q2(sale.total_amount - sale.paid_amount):
            raise HTTPException(409, "ยอดรับเกินหนี้ค้างหรือสถานะไม่พร้อมรับเงิน")
        receipts = (await db.scalars(select(CreditSaleDocument).where(CreditSaleDocument.sale_id == sale.id,
            CreditSaleDocument.kind == "customer_receipt"))).all()
        if any(r.details.get("method") == payload.method and r.details.get("reference") == payload.reference for r in receipts):
            raise HTTPException(409, "หลักฐานรับเงินนี้ถูกใช้กับใบแจ้งหนี้นี้แล้ว กรุณาตรวจรายการเดิม")
        await period_open(db, current)
        entry = await AccountingService(db)._post_entry(current.company_id, current.branch_id, current.user_id,
            today(), "credit_receipt", "รับเงินขายเชื่อ UAT",
            [PostingLine("1101" if payload.method == "cash" else "1102", payload.amount, Decimal(0), "รับเงิน"),
             PostingLine("1103", Decimal(0), payload.amount, "ลดลูกหนี้")], "credit_receipt", str(payload.request_key))
        sale.paid_amount = q2(sale.paid_amount + payload.amount)
        sale.status = "paid" if sale.paid_amount == sale.total_amount else "partial"
        await db.flush()
        await db.refresh(sale)
        await issue(db, current, sale, "customer_receipt", payload.request_key, digest,
            dict(data, method=payload.method, reference=payload.reference, journal_id=str(entry.id),
                 outstanding=str(sale.total_amount - sale.paid_amount)), amount=payload.amount)
    await db.commit()
    return await detail(db, current, sale.id)
