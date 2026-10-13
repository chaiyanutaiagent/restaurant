"""Read-only posted-ledger analysis plus explicitly user-supplied CVP scenario.

Do not filter is_reversed: both original and reversal postings must net to zero.
No operational/recipe estimates, wallets or source sales are added to GL totals.
"""
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select, func, text
from app.database import AsyncSessionLocal
from app.models.accounting import Account, JournalEntry, JournalLine
from app.models.company import Company

D = Decimal

def q(value):
    return D(value).quantize(D("0.01"), rounding=ROUND_HALF_UP)

def scenario(fixed_cost, variable_pct, target_sales):
    values = [D(str(v)) for v in (fixed_cost, variable_pct, target_sales)]
    fixed, pct, sales = values
    if (not all(v.is_finite() for v in values) or not 0 <= fixed <= D("999999999999")
            or not 0 <= sales <= D("999999999999") or not 0 <= pct <= 100):
        raise HTTPException(422, "สมมติฐานต้องเป็นจำนวนที่ไม่ติดลบ อัตราผันแปรไม่เกิน 100%")
    ratio = 1 - pct / 100
    return {"fixed_cost": q(fixed), "variable_pct": pct, "target_sales": q(sales),
        "contribution_pct": 100 - pct,
        "break_even_sales": q(fixed / ratio) if ratio > 0 else None,
        "projected_result": q(sales * ratio - fixed),
        "margin_of_safety": q(sales - fixed / ratio) if ratio > 0 else None,
        "basis": "user_assumptions_not_posted_or_saved"}

def statement(current, start, end):
    if "*" not in current.permissions and "accounting.report.view" not in current.permissions:
        raise HTTPException(403, "ต้องมีสิทธิ์ดูรายงานบัญชี")
    if not current.branch_id or current.station_key:
        raise HTTPException(403, "เลือกสาขาก่อนดูรายงาน ไม่รองรับบริบทจุดขายหรือรวมทุกสาขา")
    if end < start or (end - start).days > 365:
        raise HTTPException(422, "เลือกช่วงวันที่ไม่เกิน 366 วันและวันสิ้นสุดต้องไม่ก่อนวันเริ่มต้น")
    a, j, line = Account, JournalEntry, JournalLine
    return select(a.id, a.code, a.name, a.account_type, a.account_subtype,
        func.sum(line.debit_amount).label("debit"), func.sum(line.credit_amount).label("credit"),
        func.count().label("line_count")).join(line, line.account_id == a.id).join(j, j.id == line.entry_id).where(
        a.company_id == current.company_id, line.company_id == current.company_id,
        j.company_id == current.company_id, j.branch_id == current.branch_id,
        j.is_posted.is_(True), j.entry_date.between(start, end), a.is_header.is_(False),
        a.account_type.in_(["revenue", "expense"])
    ).group_by(a.id, a.code, a.name, a.account_type, a.account_subtype).order_by(a.code)

def summarize(rows):
    totals = {"revenue": D(0), "cogs": D(0), "other_expense": D(0)}
    accounts = []
    for row in rows:
        r = dict(row)
        group = "revenue" if r["account_type"] == "revenue" else "cogs" if r["account_subtype"] == "cost_of_goods" else "other_expense"
        amount = q(r["credit"] - r["debit"] if group == "revenue" else r["debit"] - r["credit"])
        totals[group] += amount
        accounts.append({**r, "group": group, "amount": amount})
    totals["gross_profit"] = totals["revenue"] - totals["cogs"]
    totals["posted_result"] = totals["gross_profit"] - totals["other_expense"]
    totals["gross_margin_pct"] = q(totals["gross_profit"] / totals["revenue"] * 100) if totals["revenue"] > 0 else None
    return totals, accounts

async def report(current, start: date, end: date, *, fixed_cost=D(0), variable_pct=D(0), target_sales=D(0)):
    query = statement(current, start, end)
    simulation = scenario(fixed_cost, variable_pct, target_sales)
    async with AsyncSessionLocal() as db:
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        if await db.scalar(select(Company.currency).where(Company.id == current.company_id)) != "THB":
            raise HTTPException(409, "รายงานรุ่นนี้รองรับบริษัทที่ใช้เงินบาทเท่านั้น")
        rows = (await db.execute(query)).mappings().all()
    summary, accounts = summarize(rows)
    return {"company_id": current.company_id, "branch_id": current.branch_id,
        "generated_at": datetime.now(ZoneInfo("Asia/Bangkok")), "start": start, "end": end,
        "currency": "THB", "basis": "posted_shared_accounting_ledger_selected_branch",
        "summary": summary, "accounts": accounts, "scenario": simulation,
        "posting_lines": sum(r["line_count"] for r in accounts)}
