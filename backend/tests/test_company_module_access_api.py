from __future__ import annotations

from datetime import datetime, timezone
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.database import get_identity_db
from app.dependencies import (
    PlatformTokenData,
    TokenData,
    get_current_platform_operator,
    get_current_user,
)
from app.main import app
from app.schemas.module_access import CompanyModuleAccessRead


class CompanyModuleAccessApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.company_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.operator_id = uuid.uuid4()
        self.db = MagicMock()

        async def current_user() -> TokenData:
            return TokenData(
                user_id=self.user_id,
                company_id=self.company_id,
                branch_id=None,
                permissions=["fb.order.create"],
            )

        async def current_operator() -> PlatformTokenData:
            return PlatformTokenData(
                operator_id=self.operator_id,
                session_id=uuid.uuid4(),
                username="platform.owner",
                display_name="Platform Owner",
                is_superuser=True,
                mfa_verified=True,
            )

        async def identity_db():
            return self.db

        app.dependency_overrides[get_identity_db] = identity_db
        app.dependency_overrides[get_current_user] = current_user
        app.dependency_overrides[get_current_platform_operator] = current_operator
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()

    @staticmethod
    def module_row(*, enabled: bool = True) -> CompanyModuleAccessRead:
        return CompanyModuleAccessRead(
            module_key="restaurant_pos",
            lifecycle="active",
            company_enabled=enabled,
            plan_included=True,
            runtime_ready=True,
            user_permitted=True,
            effective_access=enabled,
            reason_code="enabled" if enabled else "company_disabled",
            updated_at=datetime.now(timezone.utc),
        )

    def test_tenant_endpoint_uses_company_from_signed_session_only(self) -> None:
        service = MagicMock()
        service.list_for_company = AsyncMock(return_value=[self.module_row()])
        with patch(
            "app.routers.membership.CompanyModuleAccessService",
            return_value=service,
        ):
            response = self.client.get("/api/v1/membership/modules")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"][0]["module_key"], "restaurant_pos")
        service.list_for_company.assert_awaited_once_with(
            self.company_id,
            permissions=["fb.order.create"],
        )

    def test_platform_update_forwards_allowlisted_state_and_audit_reason(self) -> None:
        service = MagicMock()
        service.update_company_module = AsyncMock(return_value=self.module_row(enabled=False))
        with patch(
            "app.routers.platform.CompanyModuleAccessService",
            return_value=service,
        ) as service_class:
            response = self.client.put(
                f"/api/v1/platform/companies/{self.company_id}/modules/restaurant_pos",
                json={"enabled": False, "reason": "พักเพื่อทดสอบ WP2"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["data"]["effective_access"])
        service_class.assert_called_once_with(self.db, operator_id=self.operator_id)
        call = service.update_company_module.await_args
        self.assertEqual(call.args[0], self.company_id)
        self.assertEqual(call.args[1], "restaurant_pos")
        self.assertFalse(call.args[2].enabled)
        self.assertEqual(call.args[2].reason, "พักเพื่อทดสอบ WP2")

    def test_platform_update_rejects_missing_reason_before_service_write(self) -> None:
        response = self.client.put(
            f"/api/v1/platform/companies/{self.company_id}/modules/restaurant_pos",
            json={"enabled": True, "reason": "   "},
        )
        self.assertEqual(response.status_code, 422, response.text)


if __name__ == "__main__":
    unittest.main()
