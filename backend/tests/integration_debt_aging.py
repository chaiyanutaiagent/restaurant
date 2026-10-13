"""Single boundary matrix on disposable restored PostgreSQL only."""
import asyncio
from datetime import timedelta
from decimal import Decimal as D
from uuid import uuid4
from dataclasses import replace
from sqlalchemy import select, text, func
from app.config import settings
from app.database import AsyncSessionLocal
from app.dependencies import TokenData
from app.models.branch import Branch
from app.models.crm import Customer
from app.models.payable import SupplierInvoice
from app.models.credit_sales import CreditSale, CreditSaleDocument
from app.models.document_snapshot import DocumentEvent
from app.services.debt_aging_service import report
from app.services.credit_sales_service import today

assert settings.database_url=="postgresql+asyncpg://unused:unused@127.0.0.1/unused"

async def main():
    marker="AGING-"+uuid4().hex[:10]
    offsets=[-91,-90,-61,-60,-31,-30,-1,0,1,7,8,30,31]
    async with AsyncSessionLocal() as db:
        assert await db.scalar(text("select current_database()"))=="unused"
        row=(await db.execute(text('''SELECT b.company_id,b.id branch_id,u.id user_id,s.id supplier_id
          FROM branches b JOIN users u ON u.company_id=b.company_id JOIN suppliers s ON s.company_id=b.company_id
          JOIN companies c ON c.id=b.company_id WHERE c.currency='THB' AND b.deleted_at IS NULL LIMIT 1'''))).mappings().one()
        c,b,u,s=[row[k] for k in ("company_id","branch_id","user_id","supplier_id")]
        branch=Branch(company_id=c,code=marker,name="isolated other branch")
        customer=Customer(company_id=c,customer_code=marker,display_name=marker)
        db.add_all([branch,customer]); await db.flush()
        ids=[]
        for index,delta in enumerate(offsets+[0,0,0,0]):
            # Last four are paid, cancelled, draft/deleted and other branch, all excluded.
            status_ap="partial" if index<13 else ["paid","cancelled","unpaid","unpaid"][index-13]
            status_ar="partial" if index<13 else ["paid","cancelled","draft","invoiced"][index-13]
            target=branch.id if index==16 else b
            invoice=SupplierInvoice(company_id=c,branch_id=target,supplier_id=s,invoice_number=f"{marker}-{index}",
                status=status_ap,invoice_date=today()-timedelta(days=100),due_date=today()+timedelta(days=delta),
                subtotal=150,vat_amount=0,wht_amount=0,total_amount=150,paid_amount=50,remaining_amount=100,created_by=u)
            if index==15:
                from datetime import datetime, timezone
                invoice.deleted_at=datetime.now(timezone.utc)
            sale=CreditSale(company_id=c,branch_id=target,customer_id=customer.id,request_key=uuid4(),request_hash="a"*64,
                status=status_ar,description=marker,due_date=today()+timedelta(days=delta),transaction_type="external_sale",
                seller={},buyer={"name":marker},items=[],subtotal=150,vat_amount=0,total_amount=150,paid_amount=50,created_by=u)
            db.add_all([invoice,sale]); await db.flush(); ids.append(invoice.id)
            db.add(CreditSaleDocument(company_id=c,branch_id=target,sale_id=sale.id,kind="customer_invoice",number=f"{marker}-AR-{index}",
                document_date=today(),total_amount=150,request_key=uuid4(),request_hash="b"*64,details={},created_by=u))
        await db.commit()
        events_before=await db.scalar(select(func.count(DocumentEvent.id)))
    current=TokenData(user_id=u,company_id=c,branch_id=b,permissions=["*"])
    for side in ("payable","receivable"):
        data=await report(current,side,search=marker,limit=5)
        summary=data["summary"]
        assert summary["count"]==13 and summary["outstanding"]==D(1300),summary
        assert summary["overdue"]==700 and summary["due_today"]==100 and summary["next7"]==300 and summary["next30"]==500,summary
        expected={"not_due":500,"due_today":100,"days_1_30":200,"days_31_60":200,"days_61_90":200,"days_91_plus":100}
        assert all(summary["bucket_"+k]==v for k,v in expected.items()),summary
        assert data["has_more"] and len(data["items"])==5 and data["items"][0]["days_overdue"]==91
        nextpage=await report(current,side,search=marker,limit=5,page=2)
        assert not set(r["id"] for r in data["items"]) & set(r["id"] for r in nextpage["items"])
        due=await report(current,side,search=marker,window="next7")
        assert due["summary"]["count"]==3 and due["summary"]["outstanding"]==300
        bucket=await report(current,side,search=marker,bucket="days_31_60")
        assert bucket["summary"]["count"]==2
        other=await report(replace(current,branch_id=uuid4()),side,search=marker)
        assert other["summary"]["count"]==0
        assert sum(p["outstanding"] for p in data["partners"])==1300
    # A source balance changing between refreshes is reflected without a report write.
    async with AsyncSessionLocal() as db:
        invoice=await db.get(SupplierInvoice,ids[0]); invoice.paid_amount=100; invoice.remaining_amount=50
        await db.commit()
    assert (await report(current,"payable",search=marker))["summary"]["outstanding"]==1250
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count(DocumentEvent.id)))==events_before
    print("PASS AP/AR aging boundaries, partial-payment balances, excluded sources, due windows, scope, search, paging, totals and read-only refresh")

asyncio.run(main())
