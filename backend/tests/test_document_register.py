"""Bounded read-only register tests; no financial writes or source migrations."""
from datetime import date
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from fastapi import HTTPException, Response
from sqlalchemy.dialects import postgresql

from app.dependencies import TokenData
from app.services import document_register_service as service
from app.routers.company_documents import register, router


def context(**kwargs):
    values = dict(user_id=uuid.uuid4(), company_id=uuid.uuid4(), branch_id=uuid.uuid4(),
                  permissions=["*"], target_database="restaurant")
    values.update(kwargs)
    return TokenData(**values)


class RegisterPolicyTests(TestCase):
    def test_every_type_constrains_company_branch_and_stable_pagination(self):
        current = context()
        for kind, spec in service.SOURCES.items():
            with self.subTest(kind=kind):
                stmt = service.register_statement(current, kind, page=2, limit=25)
                sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
                self.assertIn(f"{spec[0].__tablename__}.company_id = '{current.company_id}'", sql)
                self.assertIn(f"{spec[0].__tablename__}.branch_id = '{current.branch_id}'", sql)
                self.assertIn("LIMIT 26 OFFSET 25", sql)
                self.assertIn(".id DESC", sql)
                if kind in {"purchase_order", "supplier_invoice"}:
                    self.assertIn("deleted_at IS NULL", sql)

    def test_each_type_requires_its_own_permission(self):
        for kind, spec in service.SOURCES.items():
            service.check_register_access(context(permissions=[spec[5]]), kind)
            with self.assertRaises(HTTPException) as raised:
                service.check_register_access(context(permissions=["system.company.edit"]), kind)
            self.assertEqual(raised.exception.status_code, 403)
        with self.assertRaises(HTTPException):
            service.check_register_access(context(permissions=["inventory.purchase.view"]), "wht_certificate")

    def test_branch_and_station_scope_fail_closed(self):
        for changes, status in [({"branch_id": None}, 409), ({"station_key": "cashier-1"}, 403)]:
            with self.assertRaises(HTTPException) as raised:
                service.check_register_access(context(**changes), "payment_voucher")
            self.assertEqual(raised.exception.status_code, status)

    def test_takeaway_purchase_does_not_query_nonexistent_legacy_tables(self):
        for kind in ["purchase_order", "goods_receipt"]:
            with self.assertRaises(HTTPException) as raised:
                service.register_session_factory(context(target_database="takeaway"), kind)
            self.assertEqual(raised.exception.status_code, 409)

    def test_routing_matches_existing_source_not_client_database_parameter(self):
        current = context(target_database="retail_pos")
        with patch.object(service, "legacy_model_session_factory_for", return_value="purchase") as factory:
            self.assertEqual(service.register_session_factory(current, "goods_receipt"), "purchase")
            factory.assert_called_once_with(current)
        for kind in ["supplier_invoice", "payment_voucher", "wht_certificate", "sales_tax_document"]:
            self.assertIs(service.register_session_factory(current, kind), service.AsyncSessionLocal)

    def test_invalid_type_dates_and_limits(self):
        for kind, options in [("unknown", {}), ("payment_voucher", {"limit": 101}),
                              ("payment_voucher", {"page": 0}),
                              ("payment_voucher", {"search": "x" * 101}),
                              ("payment_voucher", {"date_from": date(2026, 2, 1), "date_to": date(2026, 1, 1)})]:
            with self.assertRaises(HTTPException) as raised:
                service.register_statement(context(), kind, **options)
            self.assertEqual(raised.exception.status_code, 422)

    def test_search_is_bound_and_wildcards_are_escaped(self):
        stmt = service.register_statement(context(), "payment_voucher", search="%_PAY'", date_from=date(2026, 1, 1))
        compiled = stmt.compile(dialect=postgresql.dialect())
        self.assertNotIn("%_PAY'", str(compiled))
        self.assertIn("/%/_PAY'", compiled.params.values())
        self.assertIn(date(2026, 1, 1), compiled.params.values())

    def test_register_remains_read_only_and_export_is_explicit_post(self):
        routes = {route.path.rsplit("/", 1)[-1]: route.methods for route in router.routes}
        self.assertEqual(routes, {"register": {"GET"}, "history": {"GET"}, "print": {"POST"}})


class RegisterReadTests(IsolatedAsyncioTestCase):
    async def test_one_bounded_select_no_write_and_explicit_non_snapshot(self):
        current = context()
        rows = [{"id": uuid.uuid4(), "number": f"PAY-{i}", "amount": "100.00"} for i in range(3)]
        db = SimpleNamespace(execute=AsyncMock(return_value=MagicMock()))
        db.execute.return_value.mappings.return_value.all.return_value = rows
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=db)
        manager.__aexit__ = AsyncMock(return_value=False)
        with patch.object(service, "register_session_factory", return_value=lambda: manager):
            result = await service.list_register(current, "payment_voucher", limit=2)
        self.assertEqual(result["items"], rows[:2])
        self.assertTrue(result["has_more"])
        self.assertFalse(result["historical_snapshot"])
        self.assertEqual(result["source"], "accounting_legacy")
        self.assertEqual(result["branch_id"], current.branch_id)
        db.execute.assert_awaited_once()

    async def test_http_response_never_shared_cached(self):
        response = Response()
        with patch("app.routers.company_documents.list_register", new=AsyncMock(return_value={"items": []})):
            result = await register(response=response, kind="payment_voucher", current=context(),
                                    search="", date_from=None, date_to=None, page=1, limit=25)
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(result["data"], {"items": []})
