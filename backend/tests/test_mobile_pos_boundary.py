from __future__ import annotations
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
import unittest
import uuid
from unittest.mock import AsyncMock, Mock, patch
from fastapi import HTTPException
from starlette.requests import Request
from app.dependencies import get_current_user
from app.services.auth_service import AuthService
from app.services.mobile_pos_policy import POS_SURFACES, pos_permissions, enforce_pos_request
from app.services.role_preset_service import ROLE_PRESET_POLICIES
from app.utils.security import create_access_token, decode_token

OWNER = list(next(role.permission_codes for role in ROLE_PRESET_POLICIES if role.key == "company-owner"))
def request(path, headers, method="GET"):
    path, _, query = path.partition("?")
    return Request({"type": "http", "path": path, "method": method, "query_string": query.encode(),
        "headers": [(k.encode(), v.encode()) for k, v in headers.items()]})

class NativePosPolicyTests(unittest.TestCase):
    def test_only_selected_product_front_office_permissions_are_granted(self):
        for surface, product in POS_SURFACES.items():
            context = NS(branch_id=uuid.uuid4(), business_type=product, target_database=product)
            permissions = pos_permissions(surface=surface, user=NS(is_superuser=False), context=context, permissions=OWNER, device_id="d")
            self.assertIn("pos.sale.create", permissions)
            for forbidden in ("*", "system.user.create", "accounting.tax.manage", "takeaway.sale.create", "fb.recipe.manage"):
                self.assertNotIn(forbidden, permissions)
            self.assertEqual("fb.table.manage" in permissions, product == "restaurant")

    def test_wrong_product_superuser_wildcard_and_missing_device_fail_closed(self):
        for surface, product in POS_SURFACES.items():
            for override in ({"business_type": "takeaway"}, {"target_database": "takeaway"}, {"branch_id": None}):
                context = NS(**{**dict(branch_id=uuid.uuid4(), business_type=product, target_database=product), **override})
                with self.subTest(surface=surface, override=override), self.assertRaises(HTTPException):
                    pos_permissions(surface=surface, user=NS(is_superuser=False), context=context, permissions=OWNER, device_id="d")
            context = NS(branch_id=uuid.uuid4(), business_type=product, target_database=product)
            for superuser, permissions, device in ((True, OWNER, "d"), (False, ["*"], "d"), (False, OWNER, None), (False, ["inventory.product.view"], "d")):
                with self.assertRaises(HTTPException):
                    pos_permissions(surface=surface, user=NS(is_superuser=superuser), context=context, permissions=permissions, device_id=device)

    def test_endpoint_method_catalog_and_context_boundaries(self):
        for surface, product in POS_SURFACES.items():
            company, branch, brand = (str(uuid.uuid4()) for _ in range(3))
            payload = dict(client_surface=surface, company_id=company, branch_id=branch, brand_id=brand,
                business_type=product, target_database=product, store_device_id="device")
            headers = {"x-company-id": company, "x-branch-id": branch, "x-store-device-id": "device"}
            context = NS(brand_id=brand, business_type=product, target_database=product)
            enforce_pos_request(payload, request("/api/v1/pos/shifts/current", headers), context)
            catalog = "restaurant_menu" if product == "restaurant" else "retail_sale"
            enforce_pos_request(payload, request("/api/v1/products?catalog_scope="+catalog, headers), context)
            for path in ("/api/v1/auth/switch-branch", "/api/v1/system/users", "/api/v1/platform/companies",
                "/api/v1/takeaway/status", "/api/v1/restaurant/central/test/recipes", "/api/v1/products",
                "/api/v1/products?catalog_scope=all", "/api/v1/pos/sales?branch_id=other",
                "/api/v1/pos/sales?company_id=other", "/api/v1/system/branches/aaaa/settings"):
                with self.subTest(surface=surface, path=path), self.assertRaises(HTTPException):
                    enforce_pos_request(payload, request(path, headers), context)
            for field in headers:
                with self.assertRaises(HTTPException):
                    enforce_pos_request(payload, request("/api/v1/pos/sales", {**headers, field: "other"}), context)
            with self.assertRaises(HTTPException):
                enforce_pos_request(payload, request("/api/v1/pos/sales", headers, "DELETE"), context)
            if product == "retail_pos":
                with self.assertRaises(HTTPException):
                    enforce_pos_request(payload, request("/api/v1/restaurant/tables", headers), context)
            else:
                enforce_pos_request(payload, request("/api/v1/restaurant/tables", headers), context)

class NativePosSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_and_refresh_keep_surface_branch_and_device_without_admin_permissions(self):
        for surface, product in POS_SURFACES.items():
            user = NS(id=uuid.uuid4(), company_id=uuid.uuid4(), is_superuser=False, credential_version=1)
            context = NS(branch_id=uuid.uuid4(), brand_id=uuid.uuid4(), business_type=product, target_database=product)
            company = NS(id=user.company_id, is_active=True, credential_version=1)
            db = AsyncMock(); db.add = Mock(); db.get.return_value = company
            service = AuthService(db)
            service.get_user_permissions = AsyncMock(return_value=(OWNER, context.branch_id, context, None, [], ["company"]))
            access, refresh = await service.create_session(user, context.branch_id, None, None,
                station_key="counter-1", client_surface=surface, store_device_id="native-device")
            claims = decode_token(access); refresh_claims = decode_token(refresh)
            self.assertEqual(claims["scope_types"], ["branch"])
            self.assertNotIn("system.company.edit", claims["permissions"])
            record = NS(id=uuid.UUID(refresh_claims["sid"]), revoked_at=None, expires_at=datetime.now(timezone.utc)+timedelta(days=1), user_id=user.id, user_agent="test")
            db.scalar.side_effect = [record, None]; db.execute.return_value = NS(one_or_none=lambda: (user, company))
            renewed, new_refresh = await service.refresh_session(refresh, None)
            for token in (renewed, new_refresh):
                actual = decode_token(token)
                self.assertEqual(actual["client_surface"], surface)
                self.assertEqual(actual["branch_id"], str(context.branch_id))
                self.assertEqual(actual["store_device_id"], "native-device")

    async def test_signed_dependency_rechecks_roles_and_rejects_changed_product_or_branch(self):
        for surface, product in POS_SURFACES.items():
            user = NS(id=uuid.uuid4(), company_id=uuid.uuid4(), is_superuser=False, credential_version=1)
            branch, brand = uuid.uuid4(), uuid.uuid4()
            context = NS(branch_id=branch, brand_id=brand, business_type=product, target_database=product)
            db = AsyncMock(); db.execute.return_value = NS(one_or_none=lambda: (user, NS(credential_version=1)))
            db.scalar.return_value = uuid.uuid4()
            token = create_access_token(str(user.id), str(user.company_id), str(branch), OWNER, brand_id=str(brand),
                business_type=product, target_database=product, session_id=str(uuid.uuid4()), client_surface=surface, store_device_id="d")
            headers = {"x-company-id": str(user.company_id), "x-branch-id": str(branch), "x-store-device-id": "d"}
            with patch("app.dependencies.resolve_user_branch_context", AsyncMock(return_value=context)), patch.object(AuthService, "get_user_permissions", AsyncMock(return_value=(OWNER, branch, context, None, [], ["company"]))):
                result = await get_current_user(token, db, request("/api/v1/pos/shifts/current", headers))
                self.assertEqual(result.scope_types, ["branch"])
                self.assertNotIn("system.user.create", result.permissions)
                for path, changed in (("/api/v1/system/users", headers), ("/api/v1/pos/shifts/current", {**headers, "x-branch-id": str(uuid.uuid4())})):
                    with self.assertRaises(HTTPException): await get_current_user(token, db, request(path, changed))
            with patch("app.dependencies.resolve_user_branch_context", AsyncMock(return_value=context)), patch.object(AuthService, "get_user_permissions", AsyncMock(return_value=([], branch, context, None, [], ["branch"]))):
                with self.assertRaises(HTTPException): await get_current_user(token, db, request("/api/v1/pos/shifts/current", headers))
