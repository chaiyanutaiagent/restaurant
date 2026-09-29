from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
import unittest
import uuid
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from starlette.requests import Request
from app.dependencies import TokenData, get_current_user
from app.services.auth_service import AuthService
from app.services.business_directory_service import resolve_active_business
from app.services.mobile_store_policy import (
    STORE_PERMISSIONS,
    enforce_store_request,
    store_permissions,
    uat_superadmin_store_access,
)
from app.services.role_preset_service import ROLE_PRESET_POLICIES
from app.services.takeaway_service import TakeawayService
from app.utils.security import create_access_token, decode_token

POLICIES = {role.key: list(role.permission_codes) for role in ROLE_PRESET_POLICIES}


class StorePolicyTests(unittest.TestCase):
    def setUp(self):
        self.context = NS(branch_id=uuid.uuid4(), business_type="takeaway", target_database="takeaway")
        self.user = NS(is_superuser=False)

    def test_all_five_personas_have_intended_access(self):
        for role in ("takeaway-cashier", "takeaway-branch-manager", "takeaway-stock-receiving", "company-owner"):
            result = store_permissions(user=self.user, context=self.context, permissions=POLICIES[role], device_id="device")
            self.assertNotIn("*", result)
            self.assertNotIn("takeaway.production.manage", result)
            self.assertNotIn("takeaway.central_order.manage", result)
            self.assertEqual("takeaway.credit.manage" in result, role in {"company-owner", "takeaway-branch-manager"})
        with self.assertRaises(HTTPException):
            store_permissions(user=self.user, context=self.context, permissions=POLICIES["takeaway-central-kitchen"], device_id="device")

    def test_superuser_restaurant_and_missing_branch_rejected(self):
        for superuser, business, branch in [(True, "takeaway", uuid.uuid4()), (False, "restaurant", uuid.uuid4()), (False, "takeaway", None)]:
            with self.subTest(superuser=superuser, business=business, branch=branch), self.assertRaises(HTTPException):
                store_permissions(user=NS(is_superuser=superuser), context=NS(branch_id=branch, business_type=business, target_database=business), permissions=POLICIES["company-owner"], device_id="d")

    def test_named_uat_superadmin_gets_store_only_permissions(self):
        company_id = uuid.uuid4()
        user = NS(
            company_id=company_id,
            username="superadmin",
            is_superuser=True,
        )
        with patch("app.services.mobile_store_policy.settings") as configured:
            configured.uat_superadmin_all_logins_enabled = True
            configured.environment = "development"
            configured.saas_public_base_url = "https://uat-pos.foodchainservice.com"
            configured.uat_superadmin_company_id = company_id
            configured.uat_superadmin_username = "superadmin"
            self.assertTrue(uat_superadmin_store_access(user))
            result = store_permissions(
                user=user,
                context=self.context,
                permissions=["*"],
                device_id="device",
            )
        self.assertEqual(result, sorted(STORE_PERMISSIONS))
        self.assertNotIn("*", result)
        self.assertNotIn("takeaway.production.manage", result)

    def test_uat_superadmin_gate_fails_closed_outside_exact_scope(self):
        company_id = uuid.uuid4()
        base_user = NS(company_id=company_id, username="superadmin", is_superuser=True)
        cases = (
            {"enabled": False},
            {"environment": "production"},
            {"host": "pos.foodchainservice.com"},
            {"company_id": uuid.uuid4()},
            {"username": "another-admin"},
        )
        for override in cases:
            with self.subTest(override=override), patch("app.services.mobile_store_policy.settings") as configured:
                configured.uat_superadmin_all_logins_enabled = override.get("enabled", True)
                configured.environment = override.get("environment", "development")
                configured.saas_public_base_url = "https://" + override.get("host", "uat-pos.foodchainservice.com")
                configured.uat_superadmin_company_id = override.get("company_id", company_id)
                configured.uat_superadmin_username = override.get("username", "superadmin")
                self.assertFalse(uat_superadmin_store_access(base_user))
                with self.assertRaises(HTTPException):
                    store_permissions(
                        user=base_user,
                        context=self.context,
                        permissions=["*"],
                        device_id="device",
                    )

    def test_api_paths_and_methods_are_allowlisted(self):
        payload = dict(client_surface="takeaway_store", company_id="a", branch_id="b", store_device_id="d")
        headers = {"x-company-id": "a", "x-branch-id": "b", "x-store-device-id": "d"}
        enforce_store_request(payload, "GET", "/api/v1/takeaway/status", headers)
        for method, path in [("GET", "/api/v1/restaurant/menu"), ("GET", "/api/v1/retail/pos"),
            ("GET", "/api/v1/platform/tenants"), ("GET", "/api/v1/takeaway/central/orders"),
            ("POST", "/api/v1/takeaway/production/batches"), ("POST", "/api/v1/auth/switch-branch"),
            ("PUT", "/api/v1/takeaway/credit/accounts"), ("POST", "/api/v1/takeaway/credit/topups/a/review"),
            ("POST", "/api/v1/takeaway/transfers/a/ship"), ("GET", "/api/v1/takeaway/status/../recipes")]:
            with self.subTest(path=path), self.assertRaises(HTTPException):
                enforce_store_request(payload, method, path, headers)
        for name in headers:
            with self.subTest(header=name), self.assertRaises(HTTPException):
                enforce_store_request(payload, "GET", "/api/v1/takeaway/status", {**headers, name: "another"})


class StoreAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_store_cashier_cannot_charge_credit_or_impersonate_another_device(self):
        from app.routers.takeaway import create_sale, sync_offline_sale, capture_order_payment
        device = uuid.uuid4()
        current = TokenData(user_id=uuid.uuid4(), company_id=uuid.uuid4(), branch_id=uuid.uuid4(),
            permissions=POLICIES["takeaway-cashier"], client_surface="takeaway_store", store_device_id=str(device))
        for endpoint in (create_sale, sync_offline_sale):
            with self.assertRaises(HTTPException) as credit_error:
                await endpoint(NS(offline_device_id=device, payment=NS(method="credit")), current=current, db=AsyncMock())
            self.assertEqual(credit_error.exception.status_code, 403)
            with self.assertRaises(HTTPException) as device_error:
                await endpoint(NS(offline_device_id=uuid.uuid4(), payment=NS(method="cash")), current=current, db=AsyncMock())
            self.assertEqual(device_error.exception.status_code, 403)
        with self.assertRaises(HTTPException):
            await capture_order_payment(uuid.uuid4(), NS(payment=NS(method="credit")), current=current, db=AsyncMock())

    async def test_unknown_or_inactive_business_fails_and_active_filter_is_in_query(self):
        db = AsyncMock(); db.scalar.return_value = None
        for code in ("unknown-business", "inactive-company"):
            with self.assertRaises(HTTPException) as error:
                await resolve_active_business(db, code)
            self.assertEqual(error.exception.status_code, 404)
            self.assertIn("companies.is_active IS true", str(db.scalar.call_args.args[0]))

    async def test_create_and_refresh_retain_surface_device_and_branch_permissions(self):
        user = NS(id=uuid.uuid4(), company_id=uuid.uuid4(), is_superuser=False, credential_version=1)
        context = NS(branch_id=uuid.uuid4(), brand_id=uuid.uuid4(), business_type="takeaway", target_database="takeaway")
        company = NS(id=user.company_id, is_active=True, credential_version=1)
        db = AsyncMock(); db.add = Mock(); db.get.return_value = company
        service = AuthService(db)
        service.get_user_permissions = AsyncMock(return_value=(POLICIES["company-owner"], context.branch_id, context, None, [], ["company"]))
        access, refresh = await service.create_session(user, context.branch_id, None, None,
            station_key="counter-2", client_surface="takeaway_store", store_device_id="device-1")
        claims = decode_token(access); refresh_claims = decode_token(refresh)
        self.assertEqual(claims["scope_types"], ["branch"])
        self.assertNotIn("takeaway.import.apply", claims["permissions"])
        self.assertEqual(claims["station_key"], "counter-2")
        record = NS(id=uuid.UUID(refresh_claims["sid"]), revoked_at=None, expires_at=datetime.now(timezone.utc)+timedelta(days=1), user_id=user.id, user_agent="test")
        db.scalar.side_effect = [record, None]
        db.execute.return_value = NS(one_or_none=lambda: (user, company))
        renewed, next_refresh = await service.refresh_session(refresh, None)
        for raw in (renewed, next_refresh):
            payload = decode_token(raw)
            self.assertEqual(payload["client_surface"], "takeaway_store")
            self.assertEqual(payload["store_device_id"], "device-1")
            self.assertEqual(payload["branch_id"], str(context.branch_id))

    async def test_real_signed_dependency_rejects_other_company_branch_and_forbidden_api(self):
        for tenant in (uuid.uuid4(), uuid.uuid4()):
            user = NS(id=uuid.uuid4(), company_id=tenant, is_superuser=False, credential_version=1)
            branch, brand = uuid.uuid4(), uuid.uuid4()
            context = NS(branch_id=branch, brand_id=brand, business_type="takeaway", target_database="takeaway")
            db = AsyncMock(); db.execute.return_value = NS(one_or_none=lambda: (user, NS(credential_version=1)))
            db.scalar.return_value = uuid.uuid4()
            token = create_access_token(str(user.id), str(tenant), str(branch), POLICIES["takeaway-cashier"],
                brand_id=str(brand), business_type="takeaway", target_database="takeaway", session_id=str(uuid.uuid4()), client_surface="takeaway_store", store_device_id="d")
            valid = {"x-company-id": str(tenant), "x-branch-id": str(branch), "x-store-device-id": "d"}
            with patch("app.dependencies.resolve_user_branch_context", AsyncMock(return_value=context)), patch.object(AuthService, "get_user_permissions", AsyncMock(return_value=(POLICIES["takeaway-cashier"], branch, context, None, [], ["branch"]))):
                for path, headers, denied in [
                    ("/api/v1/takeaway/status", valid, False),
                    ("/api/v1/takeaway/status", {**valid, "x-company-id": str(uuid.uuid4())}, True),
                    ("/api/v1/takeaway/status", {**valid, "x-branch-id": str(uuid.uuid4())}, True),
                    ("/api/v1/takeaway/production/batches", valid, True),
                ]:
                    request = Request({"type": "http", "method": "GET", "path": path, "headers": [(k.encode(), v.encode()) for k, v in headers.items()]})
                    if denied:
                        with self.assertRaises(HTTPException): await get_current_user(token, db, request)
                    else:
                        result = await get_current_user(token, db, request)
                        self.assertEqual(result.company_id, tenant)
                        self.assertNotIn("takeaway.credit.manage", result.permissions)

    async def test_mobile_transfer_target_and_stock_location_require_own_branch(self):
        for tenant in (uuid.uuid4(), uuid.uuid4()):
            current = TokenData(user_id=uuid.uuid4(), company_id=tenant, branch_id=uuid.uuid4(), permissions=[], client_surface="takeaway_store")
            db = AsyncMock(); db.scalar.return_value = None
            service = TakeawayService(db, current)
            with self.assertRaises(HTTPException): await service._store_location(uuid.uuid4())
            params = db.scalar.call_args.args[0].compile().params
            self.assertIn(tenant, params.values())
            self.assertIn(current.branch_id, params.values())
            db.scalars.return_value = []
            await service.list_store_transfers()
            params = db.scalars.call_args.args[0].compile().params
            self.assertIn(tenant, params.values())
            self.assertIn(current.branch_id, params.values())
