"""Single posted-ledger matrix; disposable restored DB only."""
import asyncio
from datetime import date, timedelta
from dataclasses import replace
from uuid import uuid4
from sqlalchemy import text, select, func
from app.config import settings
from app.database import AsyncSessionLocal
from app.dependencies import TokenData
from app.models.branch import Branch
from app.models.accounting import Account, JournalEntry, JournalLine
from app.services.cost_analysis_service import report

assert settings.database_url == "postgresql+asyncpg://unused:unused@127.0.0.1/unused"

async def main():
    marker="COST-"+uuid4().hex[:8]
    day=date(2026,10,1)
    async with AsyncSessionLocal() as db:
        assert await db.scalar(text("select current_database()")) == "unused"
        r=(await db.execute(text("SELECT c.id company_id,u.id user_id FROM companies c JOIN users u ON u.company_id=c.id WHERE c.currency='THB' LIMIT 1"))).mappings().one()
        c,u=r["company_id"],r["user_id"]
        b=Branch(company_id=c,code=marker,name="Isolated cost matrix")
        db.add(b); await db.flush()
        accounts=[]
        for i,(kind,subtype) in enumerate([("revenue",None),("expense","cost_of_goods"),("expense",None),("asset",None)]):
            a=Account(company_id=c,code=f"{marker}-{i}",name=marker,account_type=kind,account_subtype=subtype,normal_balance="credit" if i==0 else "debit")
            db.add(a); accounts.append(a)
        await db.flush()
        async def entry(idx,legs,**kwargs):
            j=JournalEntry(company_id=c,branch_id=b.id,entry_number=f"{marker}-{idx}",entry_date=day,period_year=day.year,period_month=day.month,
                entry_type="manual",description=marker,created_by=u,is_posted=True)
            for key,value in kwargs.items(): setattr(j,key,value)
            db.add(j); await db.flush()
            for n,(account,debit,credit) in enumerate(legs):
                db.add(JournalLine(company_id=c,entry_id=j.id,account_id=accounts[account].id,line_number=n+1,debit_amount=debit,credit_amount=credit))
        await entry(1,[(0,0,1000),(3,1000,0)])
        await entry(2,[(1,400,0),(3,0,400)])
        await entry(3,[(2,100,0),(3,0,100)])
        await entry(4,[(0,0,200),(3,200,0)],is_reversed=True)
        await entry(5,[(0,200,0),(3,0,200)])
        await entry(6,[(0,100,0),(3,0,100)]) # return / contra revenue
        await entry(7,[(0,0,999),(3,999,0)],is_posted=False)
        await entry(8,[(0,0,999),(3,999,0)],branch_id=None)
        await entry(9,[(0,0,999),(3,999,0)],entry_date=day-timedelta(days=1))
        await db.commit()
        count=await db.scalar(select(func.count(JournalEntry.id)))
        actor=TokenData(user_id=u,company_id=c,branch_id=b.id,permissions=["accounting.report.view"])
    result=await report(actor,day,day,fixed_cost=30000,variable_pct=60,target_sales=100000)
    assert result["summary"]["revenue"]==900,result
    assert result["summary"]["cogs"]==400
    assert result["summary"]["other_expense"]==100
    assert result["summary"]["posted_result"]==400
    assert result["posting_lines"]==6
    assert result["scenario"]["break_even_sales"]==75000
    assert sum(r["amount"] for r in result["accounts"] if r["group"]=="revenue")==900
    for other in (replace(actor,branch_id=uuid4()), replace(actor,company_id=uuid4())):
        if other.company_id != c:
            from fastapi import HTTPException
            try: await report(other,day,day)
            except HTTPException as e: assert e.status_code==409
            else: raise AssertionError("unknown company must fail closed")
        else: assert (await report(other,day,day))["posting_lines"]==0
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count(JournalEntry.id)))==count
    print("PASS scoped posted-ledger aggregation, debit/credit reversal netting, contra sales, date/draft exclusions, scenario and read-only checks")

asyncio.run(main())
