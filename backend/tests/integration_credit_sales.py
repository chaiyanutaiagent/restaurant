"""Disposable restored PostgreSQL only. No live test transactions."""
import asyncio
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from sqlalchemy import select, text, func
from app.config import settings
from app.database import AsyncSessionLocal
from app.dependencies import TokenData
from app.models.company import Company
from app.models.crm import Customer
from app.models.product import Product
from app.models.stock import StockBalance, StockMovement
from app.models.credit_sales import CreditSale, CreditSaleDocument
from app.models.accounting import JournalEntry, JournalLine
from app.models.document_snapshot import DocumentSnapshot
from app.schemas.credit_sales import CreditSaleCreate, SaleAction, DeliveryRequest, ReceiptRequest
from app.services import credit_sales_service as svc
from app.services.document_archive_service import history, export_document
from app.services.document_register_service import register_statement
from app.utils.seed_accounts import seed_default_accounts

assert settings.database_url == "postgresql+asyncpg://unused:unused@127.0.0.1/unused"


async def main():
    async with AsyncSessionLocal() as db:
        assert await db.scalar(text("select current_database()")) == "unused"
        row = (await db.execute(text('''SELECT b.company_id,b.id branch_id,u.id actor_id,u2.id approver_id,l.id location_id
            FROM branches b JOIN users u ON u.company_id=b.company_id
            JOIN users u2 ON u2.company_id=b.company_id AND u2.id<>u.id
            JOIN stock_locations l ON l.branch_id=b.id AND l.company_id=b.company_id
            WHERE b.deleted_at IS NULL AND b.is_active AND u.deleted_at IS NULL AND u2.deleted_at IS NULL
            AND l.deleted_at IS NULL AND l.is_active LIMIT 1'''))).mappings().one()
        c,b,u,a,l = [row[k] for k in ("company_id", "branch_id", "actor_id", "approver_id", "location_id")]
        company = await db.get(Company,c)
        company.vat_registered = True
        # Clone-only fixture, do not alter a live product/customer/stock.
        customer = Customer(company_id=c, customer_code="CREDIT-QA-"+uuid4().hex[:8], display_name="ลูกค้าทดสอบขายเชื่อ", tax_id="9999999999999", is_active=True)
        product = Product(company_id=c, sku="CREDIT-QA-"+uuid4().hex[:8], name="สินค้าเครดิต UAT clone only",
            product_type="simple", inventory_role="central_ready", selling_price=D(107), vat_type="included", vat_rate=D(7))
        db.add_all([customer,product]); await db.flush()
        customer_id,p = customer.id,product.id
        db.add(StockBalance(company_id=c,branch_id=b,location_id=l,product_id=p,qty_on_hand=D(20),qty_reserved=0,cost_per_unit=D(30)))
        await seed_default_accounts(db,c)
        await db.commit()
    actor = TokenData(user_id=u,company_id=c,branch_id=b,permissions=["*"])
    approver = replace(actor,user_id=a)
    payload = CreditSaleCreate(request_key=uuid4(),customer_id=customer_id,description="isolated credit QA",
        due_date=svc.today()+timedelta(days=30),items=[{"product_id":p,"quantity":4}])
    async def create():
        async with AsyncSessionLocal() as db: return await svc.create(db,actor,payload)
    created = await asyncio.gather(create(),create())
    sid=created[0]["id"]
    assert sid==created[1]["id"] and created[0]["total_amount"]==D(428)
    async def denied(who,name,data,code):
        async with AsyncSessionLocal() as db:
            try: await svc.action(db,who,sid,name,data)
            except HTTPException as e: assert e.status_code==code,(e.status_code,e.detail)
            else: raise AssertionError("unexpected authorization/state success")
    approve=SaleAction(request_key=uuid4(),reason="approve clone")
    await denied(actor,"approve",approve,403)
    await denied(replace(approver,permissions=["accounting.invoice.view"]),"approve",approve,403)
    async with AsyncSessionLocal() as db:
        await svc.action(db,approver,sid,"approve",approve)
        again=await svc.action(db,approver,sid,"approve",approve)
        assert len(again["documents"])==1
    print("PASS create/approval idempotency, immutable price, maker-checker")
    deliver=DeliveryRequest(request_key=uuid4(),reason="handover clone",location_id=l,received_by="QA receiver")
    async with AsyncSessionLocal() as db:
        with patch("app.services.credit_sales_service.capture",AsyncMock(side_effect=RuntimeError("injected evidence failure"))):
            try: await svc.action(db,actor,sid,"deliver",deliver)
            except RuntimeError: await db.rollback()
            else: raise AssertionError("failure injection did not run")
        assert (await db.get(CreditSale,sid)).status=="approved"
        assert await db.scalar(select(StockBalance.qty_on_hand).where(StockBalance.product_id==p))==20
        assert await db.scalar(select(func.count(JournalEntry.id)).where(JournalEntry.reference_type=="credit_sale",JournalEntry.reference_id==str(sid)))==0
    async def delivery():
        async with AsyncSessionLocal() as db: return await svc.action(db,actor,sid,"deliver",deliver)
    await asyncio.gather(delivery(),delivery())
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(StockBalance.qty_on_hand).where(StockBalance.product_id==p))==16
        assert await db.scalar(select(func.count(StockMovement.id)).where(StockMovement.reference_type=="credit_sale",StockMovement.reference_id==str(sid)))==1
        entry=await db.scalar(select(JournalEntry).where(JournalEntry.reference_type=="credit_sale",JournalEntry.reference_id==str(sid)))
        amounts=(await db.execute(select(func.sum(JournalLine.debit_amount),func.sum(JournalLine.credit_amount)).where(JournalLine.entry_id==entry.id))).one()
        assert amounts==(D(548),D(548)),amounts
        billing=SaleAction(request_key=uuid4(),reason="bill clone")
        await svc.action(db,actor,sid,"bill",billing)
        assert len((await svc.detail(db,actor,sid))["documents"])==4
    await denied(actor,"cancel",SaleAction(request_key=uuid4(),reason="deny post-delivery cancel"),409)
    await denied(actor,"receive",ReceiptRequest(request_key=uuid4(),reason="overpay",amount=429,method="cash",reference="overpay"),409)
    print("PASS atomic delivery/stock/COGS/AR and rollback; billing has no financial posting")
    async def collect(ref):
        data=ReceiptRequest(request_key=uuid4(),reason="partial",amount=300,method="bank_transfer",reference=ref)
        async with AsyncSessionLocal() as db:
            try:
                await svc.action(db,actor,sid,"receive",data)
                return 200,data
            except HTTPException as e:
                await db.rollback(); return e.status_code,data
    results=await asyncio.gather(collect("bank-a"),collect("bank-b"))
    assert sorted(r[0] for r in results)==[200,409]
    receipt=next(data for code,data in results if code==200)
    async with AsyncSessionLocal() as db:
        await svc.action(db,actor,sid,"receive",receipt)
        assert (await db.get(CreditSale,sid)).paid_amount==300
    await denied(actor,"receive",receipt.model_copy(update={"request_key":uuid4(),"amount":D(1)}),409)
    async with AsyncSessionLocal() as db:
        paid=await svc.action(db,actor,sid,"receive",ReceiptRequest(request_key=uuid4(),reason="final",amount=128,method="cash",reference="cash-final"))
        assert paid["status"]=="paid" and len(paid["documents"])==6
        journals=(await db.scalars(select(JournalEntry).where(JournalEntry.company_id==c,JournalEntry.reference_type.in_(["credit_sale","credit_receipt"])))).all()
        assert len(journals)==3
        for doc in paid["documents"]:
            data=await history(db,actor,doc["kind"],doc["id"])
            assert data["snapshot"] and data["original_available"]
            rows=(await db.execute(register_statement(actor,doc["kind"]))).mappings().all()
            assert doc["id"] in [r["id"] for r in rows]
        invoice=next(d for d in paid["documents"] if d["kind"]=="customer_invoice")
        customer=await db.get(Customer,customer_id); customer.display_name="CHANGED AFTER ISSUE"
        await db.commit()
        content,media,*_=await export_document(db,actor,"customer_invoice",invoice["id"],"copy")
        assert content and media in {"application/pdf","text/html"}
        snap=await db.scalar(select(DocumentSnapshot).where(DocumentSnapshot.source_id==invoice["id"]))
        assert "CHANGED AFTER ISSUE" not in snap.rendered_html
        for wrong in [replace(actor,company_id=uuid4()),replace(actor,branch_id=uuid4()),replace(actor,permissions=[])]:
            try: await svc.detail(db,wrong,sid)
            except HTTPException as e: assert e.status_code in {403,404}
            else: raise AssertionError("scope leak")
    print("PASS partial/final receipt, concurrent overpay/idempotency, 5 document kinds, PDF, immutable buyer and scope")


asyncio.run(main())
