from __future__ import annotations

from datetime import datetime, timezone
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.database import get_identity_db
from app.dependencies import TokenData, get_current_user
from app.main import app
from app.schemas.company_workspace import (
    CompanyWorkspaceDirectoryRead,
    CompanyWorkspaceModuleRead,
    CompanyWorkspaceProvisionRead,
    CompanyWorkspaceRead,
)
from app.schemas.module_access import CompanyModuleAccessRead


class CompanyWorkspaceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.company_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.workspace_id = uuid.uuid4()
        self.db = MagicMock()

        async def current_user() -> TokenData:
            return TokenData(
                user_id=self.user_id,
                company_id=self.company_id,
                branch_id=None,
                permissions=["system.company.edit", "fb.settings.manage"],
            )

        async def identity_db():
            return self.db

        app.dependency_overrides[get_identity_db] = identity_db
        app.dependency_overrides[get_current_user] = current_user
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()

    def workspace(self, *, active: bool = True) -> CompanyWorkspaceRead:
        return CompanyWorkspaceRead(
            workspace_id=self.workspace_id,
            module_key="restaurant_pos",
            business_type="restaurant",
            brand_id=uuid.uuid4(),
            brand_slug="sample-cafe",
            brand_name="Sample Cafe",
            branch_id=uuid.uuid4(),
            branch_code="BKK-01",
            branch_name="Main Branch",
            branch_type="company_owned",
            storefront_mode="food_stall",
            is_active=active,
            can_open=active,
            entry_route="/restaurant",
        )

    @staticmethod
    def access() -> CompanyModuleAccessRead:
        return CompanyModuleAccessRead(
            module_key="restaurant_pos",
            lifecycle="active",
            company_enabled=True,
            plan_included=True,
            runtime_ready=True,
            user_permitted=True,
            effective_access=True,
            reason_code="enabled",
            updated_at=datetime.now(timezone.utc),
        )

    def test_directory_uses_company_from_signed_session(self) -> None:
        service = MagicMock()
        service.directory = AsyncMock(return_value=CompanyWorkspaceDirectoryRead(
            company_id=self.company_id,
            generated_at=datetime.now(timezone.utc),
            modules=[CompanyWorkspaceModuleRead(
                module_key="restaurant_pos",
                kind="workspace_collection",
                entry_route="/restaurant",
                can_provision=True,
                access=self.access(),
                workspaces=[self.workspace()],
            )],
        ))
        with patch("app.routers.membership.CompanyWorkspaceService", return_value=service):
            response = self.client.get("/api/v1/membership/workspaces")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["company_id"], str(self.company_id))
        self.assertNotIn("target_database", response.json()["data"]["modules"][0]["workspaces"][0])
        current = service.directory.await_args.args[0]
        self.assertEqual(current.company_id, self.company_id)

    def test_provision_forbids_client_selected_database(self) -> None:
        response = self.client.post("/api/v1/membership/workspaces", json={
            "idempotency_key": "workspace-request-001",
            "module_key": "restaurant_pos",
            "brand_slug": "sample-cafe",
            "brand_name": "Sample Cafe",
            "branch_code": "BKK-01",
            "branch_name": "Main Branch",
            "branch_type": "company_owned",
            "storefront_mode": "food_stall",
            "target_database": "takeaway",
        })
        self.assertEqual(response.status_code, 422, response.text)

    def test_provision_and_deactivate_forward_auditable_context(self) -> None:
        workspace = self.workspace()
        service = MagicMock()
        service.provision = AsyncMock(return_value=CompanyWorkspaceProvisionRead(
            created=True,
            created_resources=["brand", "branch", "workspace"],
            workspace=workspace,
        ))
        service.update_status = AsyncMock(return_value=self.workspace(active=False))
        with patch("app.routers.membership.CompanyWorkspaceService", return_value=service):
            created = self.client.post("/api/v1/membership/workspaces", json={
                "idempotency_key": "workspace-request-001",
                "module_key": "restaurant_pos",
                "brand_slug": "sample-cafe",
                "brand_name": "Sample Cafe",
                "branch_code": "BKK-01",
                "branch_name": "Main Branch",
                "branch_type": "company_owned",
                "storefront_mode": "food_stall",
            })
            deactivated = self.client.patch(
                f"/api/v1/membership/workspaces/{self.workspace_id}",
                json={"active": False, "reason": "พักเพื่อ rollback WP3"},
            )

        self.assertEqual(created.status_code, 200, created.text)
        self.assertTrue(created.json()["data"]["created"])
        provision_call = service.provision.await_args
        self.assertEqual(provision_call.args[0].company_id, self.company_id)
        self.assertEqual(provision_call.args[1].module_key, "restaurant_pos")
        self.assertEqual(deactivated.status_code, 200, deactivated.text)
        status_call = service.update_status.await_args
        self.assertEqual(status_call.args[1], self.workspace_id)
        self.assertEqual(status_call.args[2].reason, "พักเพื่อ rollback WP3")


if __name__ == "__main__":
    unittest.main()
