"""Additional negative paths, on disposable clone only; main happy path not repeated."""
import asyncio
from datetime import timedelta
from decimal import Decimal as D
from uuid import uuid4
from dataclasses import replace
from fastapi import HTTPException
from sqlalchemy import select, text, func
from app.config import settings
from app.database import AsyncSessionLocal
from app.dependencies import TokenData
from app.models.company import Company
from app.models.crm import Customer
from app.models.product import Product
from app.models.stock import StockBalance
from app.models.credit_sales import CreditSale
from app.models.accounting import JournalEntry
from app.models.tax_operations import TaxPeriod
from app.schemas.credit_sales import CreditSaleCreate, SaleAction, DeliveryRequest
from app.services import credit_sales_service as svc
from app.services.document_archive_service import history

assert settings.database_url == "postgresql+asyncpg://unused:unused@127.0.0.1/unused"

async def main():
    async with AsyncSessionLocal() as db:
        r=(await db.execute(text('''SELECT b.company_id,b.id branch_id,u.id actor_id,u2.id approver_id,l.id location_id
          FROM branches b JOIN users u ON u.company_id=b.company_id
          JOIN users u2 ON u2.company_id=b.company_id AND u2.id<>u.id
          JOIN stock_locations l ON l.branch_id=b.id AND l.company_id=b.company_id
          WHERE b.deleted_at IS NULL AND b.is_active AND l.is_active AND l.deleted_at IS NULL LIMIT 1'''))).mappings().one()
        c,b,u,a,l=[r[k] for k in ("company_id","branch_id","actor_id","approver_id","location_id")]
        company=await db.get(Company,c); company.tax_id="1111111111111"
        customer=Customer(company_id=c,customer_code="GUARD-"+uuid4().hex[:8],display_name="clone",tax_id=company.tax_id)
        product=Product(company_id=c,sku="GUARD-"+uuid4().hex[:8],name="clone guard stock",product_type="simple",selling_price=D(100),vat_type="exempt",inventory_role="central_ready")
        db.add_all([customer,product]); await db.flush()
        cust,p=customer.id,product.id
        db.add(StockBalance(company_id=c,branch_id=b,location_id=l,product_id=p,qty_on_hand=0,qty_reserved=0,cost_per_unit=10))
        await db.commit()
    actor=TokenData(user_id=u,company_id=c,branch_id=b,permissions=["*"])
    payload=CreditSaleCreate(request_key=uuid4(),customer_id=cust,description="guard",due_date=svc.today()+timedelta(days=7),items=[{"product_id":p,"quantity":1}])
    async with AsyncSessionLocal() as db:
        try: await svc.create(db,actor,payload)
        except HTTPException as e: assert e.status_code==409
        else: raise AssertionError("same-company sale allowed")
        await db.rollback()
        customer=await db.get(Customer,cust); customer.tax_id="2222222222222"; await db.commit()
        sale=await svc.create(db,actor,payload); sid=sale["id"]
        await svc.action(db,replace(actor,user_id=a),sid,"approve",SaleAction(request_key=uuid4(),reason="approve"))
    deliver=DeliveryRequest(request_key=uuid4(),reason="guard",location_id=l,received_by="clone")
    async with AsyncSessionLocal() as db:
        try: await svc.action(db,actor,sid,"deliver",deliver)
        except HTTPException as e: assert e.status_code==409
        else: raise AssertionError("insufficient stock allowed")
        await db.rollback()
        assert await db.scalar(select(func.count(JournalEntry.id)).where(JournalEntry.reference_id==str(sid)))==0
        assert (await db.get(CreditSale,sid)).status=="approved"
        try: await svc.action(db,replace(actor,target_database="retail"),sid,"deliver",deliver)
        except HTTPException as e: assert e.status_code==409
        else: raise AssertionError("retail routing bypass")
        await db.rollback()
        balance=await db.scalar(select(StockBalance).where(StockBalance.product_id==p)); balance.qty_on_hand=10
        period=await db.scalar(select(TaxPeriod).where(TaxPeriod.company_id==c,TaxPeriod.scope_key==str(b),TaxPeriod.period_year==svc.today().year,TaxPeriod.period_month==svc.today().month))
        if not period:
            period=TaxPeriod(company_id=c,branch_id=b,filing_scope="branch",scope_key=str(b),period_year=svc.today().year,period_month=svc.today().month,status="locked")
            db.add(period)
        else: period.status="locked"
        await db.commit()
        try: await svc.action(db,actor,sid,"deliver",deliver)
        except HTTPException as e: assert e.status_code==409
        else: raise AssertionError("closed period allowed")
        await db.rollback()
        cancelled=await svc.action(db,actor,sid,"cancel",SaleAction(request_key=uuid4(),reason="cancel before stock"))
        assert cancelled["status"]=="cancelled"
        doc=cancelled["documents"][0]
        h=await history(db,actor,doc["kind"],doc["id"])
        assert not h["original_available"] and h["status"]=="cancelled"
        assert await db.scalar(select(StockBalance.qty_on_hand).where(StockBalance.product_id==p))==10
    print("PASS same-company transfer block, insufficient stock, retail source protection, closed period and pre-delivery cancellation")

asyncio.run(main())
