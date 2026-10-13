from datetime import date
from uuid import uuid4
from unittest import TestCase
from sqlalchemy.dialects import postgresql
from fastapi import HTTPException
from app.dependencies import TokenData
from app.services.debt_aging_service import authorize, base_statement, filtered_source
from app.routers.debt_aging import router


def actor(**changes):
    data = dict(user_id=uuid4(),company_id=uuid4(),branch_id=uuid4(),permissions=["*"])
    data.update(changes)
    return TokenData(**data)


class AgingTests(TestCase):
    def test_scope_and_permissions(self):
        for side, permission in (("payable","accounting.payment.view"),("receivable","accounting.invoice.view")):
            authorize(actor(permissions=["accounting.report.view",permission]),side)
            for changes in ({"permissions":[permission]}, {"permissions":["accounting.report.view"]}, {"branch_id":None}, {"station_key":"counter"}):
                with self.assertRaises(HTTPException): authorize(actor(**changes),side)

    def test_sql_source_and_tenant_filters(self):
        current=actor()
        for side, table in (("payable","supplier_invoices"),("receivable","credit_sales")):
            sql=str(base_statement(current,side).compile(dialect=postgresql.dialect(),compile_kwargs={"literal_binds":True}))
            self.assertIn(f"{table}.company_id = '{current.company_id}'",sql)
            self.assertIn(f"{table}.branch_id = '{current.branch_id}'",sql)
            self.assertNotIn("credit_ledgers",sql)
            self.assertNotIn("sale_orders",sql)
        self.assertIn("remaining_amount >",str(base_statement(current,"payable")))

    def test_bad_filters_rejected_and_search_escaped(self):
        for options in ({"window":"yesterday"},{"bucket":"bad"},{"search":"x"*101}):
            with self.assertRaises(HTTPException): filtered_source(actor(),"payable",date(2026,10,13),**options)
        query=filtered_source(actor(),"payable",date(2026,10,13),search="%_'",window="next7")
        compiled=query.compile(dialect=postgresql.dialect())
        self.assertNotIn("%_'",str(compiled))
        self.assertIn("/%/_'",compiled.params.values())

    def test_router_has_no_mutations_or_backdated_parameter(self):
        self.assertTrue(all(r.methods=={"GET"} for r in router.routes))
        import inspect
        from app.routers.debt_aging import aging
        self.assertNotIn("as_of",inspect.signature(aging).parameters)
