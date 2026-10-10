from __future__ import annotations

from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from app.config import settings
from app.database import get_db, get_identity_db
from app.dependencies import TokenData, get_current_user
from app.main import app


class BranchOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.company_id = uuid.uuid4()
        self.db = MagicMock()
        self.db.commit = AsyncMock()
        self.db.flush = AsyncMock()
        self.db.rollback = AsyncMock()
        async def current():
            return TokenData(user_id=uuid.uuid4(), company_id=self.company_id, branch_id=None,
                             permissions=["system.branch.view", "system.branch.create"], scope_types=["company"])
        async def identity():
            return self.db
        async def legacy():
            raise AssertionError("Branch onboarding must not use the legacy DB dependency")
        app.dependency_overrides[get_current_user] = current
        app.dependency_overrides[get_identity_db] = identity
        app.dependency_overrides[get_db] = legacy
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()

    def test_split_first_branch_explains_workspace_step_before_any_write(self):
        with patch.object(settings, "identity_database", "platform_core"):
            response = self.client.post("/api/v1/system/branches", json={"code": "TEST2-BKK-01", "name": "สาขาทดสอบกรุงเทพ"},
                                        headers={"X-Company-ID": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "BRANCH_WORKSPACE_REQUIRED")
        self.assertEqual(response.json()["detail"]["next"], "/workspaces")
        self.assertIn("แบรนด์", response.json()["detail"]["message"])
        self.db.add.assert_not_called()
        self.db.flush.assert_not_awaited()
        self.db.commit.assert_not_awaited()

    def test_listing_uses_canonical_company_not_spoofed_header(self):
        service = MagicMock()
        service.list_branches = AsyncMock(return_value=[])
        with patch.object(settings, "identity_database", "platform_core"), patch("app.routers.system.AdminService", return_value=service) as constructor:
            response = self.client.get("/api/v1/system/branches", headers={"X-Company-ID": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        constructor.assert_called_once_with(self.db)
        self.assertEqual(service.list_branches.await_args.args[0], self.company_id)
        self.assertFalse(service.list_branches.await_args.kwargs["include_settings"])
        self.assertEqual(response.json()["meta"]["branch_creation_mode"], "workspace")

    def test_field_validation_rejects_bad_inputs_without_writes(self):
        for field, value in (("code", "x" * 21), ("name", "   "), ("latitude", 91), ("phone", "1" * 21)):
            with self.subTest(field=field):
                response = self.client.post("/api/v1/system/branches", json={"code": "BKK-01", "name": "Test", field: value})
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn(["body", field], [item["loc"] for item in response.json()["detail"]])
        self.db.add.assert_not_called()
        self.db.commit.assert_not_awaited()

    def test_legacy_mode_retains_existing_creation_path(self):
        branch_id = uuid.uuid4()
        service = MagicMock()
        service.create_branch = AsyncMock(return_value=SimpleNamespace(id=branch_id))
        service.get_branch_detail = AsyncMock(return_value=SimpleNamespace(model_dump=lambda: {"id": str(branch_id)}))
        policy = MagicMock(require_capacity=AsyncMock())
        with patch.object(settings, "identity_database", "legacy"), patch("app.routers.system.AdminService", return_value=service), patch("app.routers.system.TenantControlPolicy", return_value=policy):
            response = self.client.post("/api/v1/system/branches", json={"code": "BKK-01", "name": "Test"})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(service.create_branch.await_args.args[0], self.company_id)


if __name__ == "__main__":
    unittest.main()
