import unittest
from datetime import date, timedelta
from decimal import Decimal as D
from dataclasses import replace
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from app.dependencies import TokenData
from app.services.cost_analysis_service import scenario, statement, summarize

class CostAnalysisTests(unittest.TestCase):
    def test_scenario_boundaries(self):
        r = scenario(30000, 60, 100000)
        self.assertEqual(r["break_even_sales"], D("75000.00"))
        self.assertEqual(r["projected_result"], D("10000.00"))
        self.assertEqual(r["margin_of_safety"], D("25000.00"))
        self.assertIsNone(scenario(100, 100, 500)["break_even_sales"])
        self.assertEqual(scenario(0, 60, 0)["break_even_sales"], 0)
        self.assertEqual(scenario(100, 0, 50)["projected_result"], -50)
        for values in [(-1,0,0), (0,101,0), (0,-1,0), (0,0,-1), ("NaN",0,0), (0,"Infinity",0)]:
            with self.assertRaises(HTTPException): scenario(*values)

    def test_summarize_contra_and_empty(self):
        rows = [dict(id=uuid4(), code="1", name="a", account_type=t, account_subtype=s,
                     debit=D(d), credit=D(c), line_count=1) for t,s,d,c in [
            ("revenue",None,"0","1000"), ("revenue",None,"100","0"),
            ("expense","cost_of_goods","400","50"), ("expense",None,"100","0")]]
        summary, _ = summarize(rows)
        self.assertEqual(summary["revenue"], 900)
        self.assertEqual(summary["cogs"], 350)
        self.assertEqual(summary["posted_result"], 450)
        self.assertIsNone(summarize([])[0]["gross_margin_pct"])

    def test_scope_and_sql_reversal_policy(self):
        actor=TokenData(user_id=uuid4(),company_id=uuid4(),branch_id=uuid4(),permissions=["accounting.report.view"])
        start=date(2026,1,1)
        sql=str(statement(actor,start,start).compile(dialect=postgresql.dialect()))
        for part in ("accounts.company_id", "journal_lines.company_id", "journal_entries.company_id", "journal_entries.branch_id", "is_posted IS true", "entry_date BETWEEN"):
            self.assertIn(part,sql)
        self.assertNotIn("is_reversed",sql)
        for a in (replace(actor,permissions=[]), replace(actor,branch_id=None), replace(actor,station_key="x")):
            with self.assertRaises(HTTPException): statement(a,start,start)
        for end in (start-timedelta(days=1), start+timedelta(days=366)):
            with self.assertRaises(HTTPException): statement(actor,start,end)

    def test_get_only(self):
        from app.routers.cost_analysis import router
        self.assertEqual(len(router.routes),1)
        self.assertEqual(router.routes[0].methods,{"GET"})

if __name__ == "__main__": unittest.main()
