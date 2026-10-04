"""No network, credentials or operational data writes; test the actual boundary functions."""
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch
import unittest
import uuid

from fastapi import HTTPException, Response
from starlette.requests import Request
from app.dependencies import TokenData
from app.services.takeaway_service import TakeawayService


class ProductionLoginGuards(unittest.IsolatedAsyncioTestCase):
    async def test_all_test_login_paths_reject_production_even_if_flag_is_on(self):
        from app.routers.auth import uat_auto_login, _qa_access_guard
        from app.routers.platform import uat_platform_auto_login, _platform_qa_access_guard
        request = Request({"type": "http", "method": "POST", "path": "/",
                           "headers": [(b"host", b"uat-pos.foodchainservice.com")]})
        configured = NS(environment="production", uat_auth_bypass_enabled=True,
                        qa_access_mode_enabled=True, qa_access_key="fixture-key",
                        saas_public_base_url="https://uat-pos.foodchainservice.com")
        db = AsyncMock()
        for target, endpoint in (("app.routers.auth.settings", uat_auto_login),
                                 ("app.routers.platform.settings", uat_platform_auto_login)):
            with self.subTest(endpoint=endpoint.__name__), patch(target, configured):
                with self.assertRaises(HTTPException) as exc:
                    if endpoint is uat_auto_login: await endpoint(request, db)
                    else: await endpoint(request, Response(), db)
                self.assertEqual(exc.exception.status_code, 404)
        for target, guard in (("app.routers.auth.settings", _qa_access_guard),
                              ("app.routers.platform.settings", _platform_qa_access_guard)):
            with patch(target, configured), self.assertRaises(HTTPException) as exc:
                guard(request, "irrelevant-test-key")
            self.assertEqual(exc.exception.status_code, 404)
        db.scalar.assert_not_awaited()
        db.execute.assert_not_awaited()

    async def test_business_code_authentication_uses_resolved_company_not_client_company(self):
        from app.routers.mobile_store_auth import authenticate, StoreCredentials
        for code in ("company-one", "company-two"):
            company = NS(id=uuid.uuid4())
            service = NS(authenticate_user=AsyncMock(return_value=NS(is_superuser=False)))
            request = Mock()
            payload = StoreCredentials(business_code=code, username=" Store ", password="fixture-only",
                                       station_key="counter-1", device_id=uuid.uuid4())
            with patch("app.routers.mobile_store_auth.resolve_active_business", AsyncMock(return_value=company)) as resolve, \
                 patch("app.routers.mobile_store_auth.require_public_rate_limit", AsyncMock()), \
                 patch("app.routers.mobile_store_auth.AuthService", return_value=service):
                db = AsyncMock()
                await authenticate(payload, request, db)
                resolve.assert_awaited_once_with(db, code)
                service.authenticate_user.assert_awaited_once_with(company.id, "store", "fixture-only")


class StoreCatalogStockGuards(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.current = TokenData(user_id=uuid.uuid4(), company_id=uuid.uuid4(), branch_id=uuid.uuid4(),
                                 brand_id=uuid.uuid4(), permissions=[], business_type="takeaway", target_database="takeaway")
        self.db = AsyncMock()
        self.db.add = Mock()
        self.service = TakeawayService(self.db, self.current)

    async def test_catalog_availability_and_override_do_not_ignore_stock_or_branch_switch(self):
        self.service._validate_context = AsyncMock()
        self.service._sale_location_id = AsyncMock(return_value=uuid.uuid4())
        item = NS(track_stock=True, price=Decimal("50"))
        self.db.execute.return_value = NS(all=lambda: [
            (item, Decimal("0"), True, Decimal("3")),
            (item, None, True, Decimal("0")),
            (item, None, True, Decimal("-1")),
            (item, None, True, None),
            (item, None, False, Decimal("20")),
            (NS(track_stock=False, price=Decimal("9")), None, True, None),
        ])
        rows = await self.service.list_catalog(self.current.brand_id, self.current.branch_id)
        self.assertEqual([r["is_available"] for r in rows], [True, False, False, False, False, True])
        self.assertEqual(rows[0]["effective_price"], Decimal("0"))
        statement = self.db.execute.call_args.args[0]
        sql, params = str(statement), statement.compile().params
        for value in (self.current.company_id, self.current.branch_id, self.current.brand_id,
                      self.service._sale_location_id.return_value, ""):
            self.assertIn(value, params.values())
        self.assertIn("on_hand_qty - takeaway_stock_balances.reserved_qty", sql)
        self.assertIn("takeaway_catalog_items.is_active IS true", sql)

    async def test_catalog_rejects_context_before_querying(self):
        self.service._validate_context = AsyncMock(side_effect=HTTPException(404))
        with self.assertRaises(HTTPException):
            await self.service.list_catalog(uuid.uuid4(), uuid.uuid4())
        self.db.execute.assert_not_awaited()

    async def test_sale_cannot_consume_reserved_stock_and_equal_boundary_is_allowed(self):
        for delta, accepted in (("-4", False), ("-3", True)):
            with self.subTest(delta=delta):
                balance = NS(on_hand_qty=Decimal("10"), reserved_qty=Decimal("7"), average_cost=Decimal("2"))
                self.db.scalar.side_effect = [None, balance]
                self.db.add.reset_mock()
                args = dict(location_id=uuid.uuid4(), item_id=uuid.uuid4(), lot_code="",
                            quantity_delta=Decimal(delta), unit_cost=Decimal("0"),
                            movement_type="sale", idempotency_key="fixture-only")
                if accepted:
                    result = await self.service._apply_stock(**args)
                    self.assertEqual(result.on_hand_qty, Decimal("7"))
                    self.db.add.assert_called_once()
                else:
                    with self.assertRaises(HTTPException) as exc: await self.service._apply_stock(**args)
                    self.assertEqual(exc.exception.status_code, 409)
                    self.assertEqual(balance.on_hand_qty, Decimal("10"))
                    self.db.add.assert_not_called()
                query = self.db.scalar.call_args.args[0]
                self.assertIn("FOR UPDATE", str(query))
                self.assertIn(self.current.company_id, query.compile().params.values())
