from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.dependencies import TokenData
from app.models.audit import AuditLog
from app.schemas.company_workspace import CompanyWorkspaceProvisionRequest
from app.schemas.module_access import CompanyModuleAccessRead
from app.services.company_workspace_service import (
    CompanyWorkspaceService,
    require_workspace_management,
    workspace_request_fingerprint,
)


def module_access(
    *,
    effective: bool = True,
    module_key: str = "restaurant_pos",
) -> CompanyModuleAccessRead:
    return CompanyModuleAccessRead(
        module_key=module_key,  # type: ignore[arg-type]
        lifecycle="dark_launch" if module_key == "takeaway_pos" else "active",
        company_enabled=effective,
        plan_included=True,
        runtime_ready=True,
        user_permitted=True,
        effective_access=effective,
        reason_code="enabled" if effective else "company_disabled",
        updated_at=datetime.now(timezone.utc),
    )


def request(**overrides: object) -> CompanyWorkspaceProvisionRequest:
    values: dict[str, object] = {
        "idempotency_key": "workspace-request-001",
        "module_key": "restaurant_pos",
        "brand_slug": " sample-cafe ",
        "brand_name": " Sample   Cafe ",
        "branch_code": " bkk-01 ",
        "branch_name": " Main   Branch ",
        "branch_type": "company_owned",
        "storefront_mode": "food_stall",
    }
    values.update(overrides)
    return CompanyWorkspaceProvisionRequest(**values)


class CompanyWorkspaceContractTests(unittest.TestCase):
    def test_request_normalizes_identity_and_forbids_database_selection(self) -> None:
        payload = request()
        self.assertEqual(payload.brand_slug, "sample-cafe")
        self.assertEqual(payload.brand_name, "Sample Cafe")
        self.assertEqual(payload.branch_code, "BKK-01")
        self.assertEqual(payload.branch_name, "Main Branch")

        with self.assertRaises(ValidationError):
            request(target_database="restaurant")

    def test_request_fingerprint_is_stable_but_key_independent(self) -> None:
        first = request(idempotency_key="workspace-request-001")
        retry = request(idempotency_key="workspace-request-002")
        changed = request(idempotency_key="workspace-request-001", branch_code="CNX-01")
        self.assertEqual(workspace_request_fingerprint(first), workspace_request_fingerprint(retry))
        self.assertNotEqual(workspace_request_fingerprint(first), workspace_request_fingerprint(changed))

    def test_workspace_management_is_explicit(self) -> None:
        allowed = TokenData(
            user_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            branch_id=None,
            permissions=["system.company.edit"],
        )
        require_workspace_management(allowed)
        denied = TokenData(
            user_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            branch_id=None,
            permissions=["fb.order.create"],
        )
        with self.assertRaises(HTTPException) as raised:
            require_workspace_management(denied)
        self.assertEqual(raised.exception.status_code, 403)


class CompanyWorkspaceServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.company_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.current = TokenData(
            user_id=self.user_id,
            company_id=self.company_id,
            branch_id=None,
            permissions=["system.company.edit", "fb.settings.manage"],
        )
        self.brand = SimpleNamespace(
            id=uuid.uuid4(),
            company_id=self.company_id,
            slug="sample-cafe",
            name="Sample Cafe",
            business_type="restaurant",
            storefront_mode="food_stall",
            is_active=True,
        )
        self.branch = SimpleNamespace(
            id=uuid.uuid4(),
            company_id=self.company_id,
            code="BKK-01",
            name="Main Branch",
            is_active=True,
            deleted_at=None,
        )
        self.link = SimpleNamespace(
            id=uuid.uuid4(),
            company_id=self.company_id,
            brand_id=self.brand.id,
            branch_id=self.branch.id,
            branch_type="company_owned",
            is_active=True,
            brand=self.brand,
            branch=self.branch,
        )

    async def test_existing_natural_identity_is_idempotent_and_audited(self) -> None:
        db = AsyncMock()
        db.add = MagicMock()
        db.scalar.side_effect = [
            SimpleNamespace(id=self.company_id, is_active=True),
            None,
            self.brand,
            self.branch,
            None,
            self.link,
            self.link,
        ]
        with patch(
            "app.services.company_workspace_service.CompanyModuleAccessService.list_for_company",
            AsyncMock(return_value=[module_access()]),
        ):
            result = await CompanyWorkspaceService(db).provision(
                self.current,
                request(),
                ip_address="127.0.0.1",
                user_agent="test",
            )

        self.assertFalse(result.created)
        self.assertEqual(result.created_resources, [])
        self.assertEqual(result.workspace.workspace_id, self.link.id)
        self.assertNotIn("target_database", result.workspace.model_dump())
        db.commit.assert_awaited_once()
        audit = next(
            call.args[0]
            for call in db.add.call_args_list
            if isinstance(call.args[0], AuditLog)
        )
        self.assertEqual(audit.action, "company.workspace.provision")
        self.assertEqual(audit.company_id, self.company_id)
        self.assertEqual(audit.new_value["created_resources"], [])

    async def test_same_idempotency_key_replays_without_another_write(self) -> None:
        payload = request()
        replay = SimpleNamespace(
            new_value={
                "request_fingerprint": workspace_request_fingerprint(payload),
                "workspace_id": str(self.link.id),
            }
        )
        db = AsyncMock()
        db.add = MagicMock()
        db.scalar.side_effect = [
            SimpleNamespace(id=self.company_id, is_active=True),
            replay,
            self.link,
        ]
        with patch(
            "app.services.company_workspace_service.CompanyModuleAccessService.list_for_company",
            AsyncMock(return_value=[module_access()]),
        ):
            result = await CompanyWorkspaceService(db).provision(
                self.current,
                payload,
                ip_address=None,
                user_agent=None,
            )

        self.assertFalse(result.created)
        db.commit.assert_not_awaited()
        db.add.assert_not_called()

    async def test_module_denial_happens_before_company_write(self) -> None:
        db = AsyncMock()
        db.add = MagicMock()
        with patch(
            "app.services.company_workspace_service.CompanyModuleAccessService.list_for_company",
            AsyncMock(return_value=[module_access(effective=False)]),
        ):
            with self.assertRaises(HTTPException) as raised:
                await CompanyWorkspaceService(db).provision(
                    self.current,
                    request(),
                    ip_address=None,
                    user_agent=None,
                )
        self.assertEqual(raised.exception.status_code, 403)
        db.scalar.assert_not_awaited()
        db.commit.assert_not_awaited()

    async def test_takeaway_requires_and_accepts_only_an_effective_dark_launch_gate(self) -> None:
        service = CompanyWorkspaceService(AsyncMock())
        with patch(
            "app.services.company_workspace_service.CompanyModuleAccessService.list_for_company",
            AsyncMock(return_value=[module_access(module_key="takeaway_pos")]),
        ):
            allowed = await service._require_effective_module(self.current, "takeaway_pos")
        self.assertEqual(allowed.module_key, "takeaway_pos")
        self.assertTrue(allowed.effective_access)

        with patch(
            "app.services.company_workspace_service.CompanyModuleAccessService.list_for_company",
            AsyncMock(return_value=[
                module_access(effective=False, module_key="takeaway_pos")
            ]),
        ):
            with self.assertRaises(HTTPException) as raised:
                await service._require_effective_module(self.current, "takeaway_pos")
        self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
