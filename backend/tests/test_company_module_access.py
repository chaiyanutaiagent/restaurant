from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.models.audit import AuditLog
from app.models.company import Company
from app.schemas.module_access import CompanyModuleAccessUpdate
from app.services.company_module_access_service import (
    COMPANY_MODULES_BY_KEY,
    CompanyModuleAccessService,
    company_module_definition,
    evaluate_company_module_access,
    synchronize_legacy_module_flags,
)


class CompanyModuleAccessContractTests(unittest.TestCase):
    def test_catalog_uses_stable_allowlisted_keys(self) -> None:
        self.assertEqual(
            set(COMPANY_MODULES_BY_KEY),
            {
                "erp",
                "central_kitchen",
                "restaurant_pos",
                "takeaway_pos",
                "retail_pos",
                "hotel_pms",
            },
        )
        with self.assertRaises(HTTPException) as raised:
            company_module_definition("arbitrary_module")
        self.assertEqual(raised.exception.status_code, 404)

    def test_update_requires_auditable_reason(self) -> None:
        with self.assertRaises(ValidationError):
            CompanyModuleAccessUpdate(enabled=True, reason="   ")
        payload = CompanyModuleAccessUpdate(enabled=False, reason=" พักการใช้งานชั่วคราว ")
        self.assertEqual(payload.reason, "พักการใช้งานชั่วคราว")

    def test_legacy_flags_map_to_canonical_modules(self) -> None:
        definition = COMPANY_MODULES_BY_KEY["restaurant_pos"]
        result = evaluate_company_module_access(
            definition,
            company_active=True,
            company_flags={"restaurant": True},
            plan_flags={"restaurant": True},
            permissions=["fb.order.create"],
        )
        self.assertEqual(result, (True, True, True, True, "enabled"))

        synchronized = synchronize_legacy_module_flags(
            {"restaurant_pos": False, "takeaway_pos": True, "custom": True}
        )
        self.assertFalse(synchronized["restaurant"])
        self.assertTrue(synchronized["takeaway"])
        self.assertTrue(synchronized["custom"])

    def test_planned_runtime_and_permissions_fail_closed(self) -> None:
        planned = evaluate_company_module_access(
            COMPANY_MODULES_BY_KEY["hotel_pms"],
            company_active=True,
            company_flags={"hotel_pms": True},
            plan_flags={"hotel_pms": True},
            permissions=["*"],
        )
        self.assertFalse(planned[2])
        self.assertEqual(planned[4], "lifecycle_planned")

        with patch(
            "app.services.company_module_access_service.settings.takeaway_feature_enabled",
            False,
        ):
            dark = evaluate_company_module_access(
                COMPANY_MODULES_BY_KEY["takeaway_pos"],
                company_active=True,
                company_flags={"takeaway": True},
                plan_flags={"takeaway": True},
                permissions=["takeaway.catalog.view"],
            )
        self.assertFalse(dark[2])
        self.assertEqual(dark[4], "runtime_unavailable")

        denied = evaluate_company_module_access(
            COMPANY_MODULES_BY_KEY["restaurant_pos"],
            company_active=True,
            company_flags={"restaurant": True},
            plan_flags={"restaurant": True},
            permissions=[],
        )
        self.assertFalse(denied[3])
        self.assertEqual(denied[4], "permission_denied")


class CompanyModuleAccessServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_profile_without_plan_keeps_existing_restaurant_access(self) -> None:
        company_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        company = SimpleNamespace(id=company_id, is_active=True, updated_at=now)
        profile = SimpleNamespace(
            plan_code="legacy-uat",
            feature_flags={"restaurant": True},
            updated_at=now,
        )
        db = AsyncMock()
        db.get.return_value = company
        db.scalar.side_effect = [profile, None]

        rows = await CompanyModuleAccessService(db).list_for_company(
            company_id,
            permissions=["fb.order.create"],
        )

        restaurant = next(row for row in rows if row.module_key == "restaurant_pos")
        self.assertTrue(restaurant.plan_included)
        self.assertTrue(restaurant.effective_access)

    async def test_tenant_read_is_scoped_and_separates_plan_company_runtime(self) -> None:
        company_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        company = SimpleNamespace(id=company_id, is_active=True, updated_at=now)
        profile = SimpleNamespace(
            plan_code="starter",
            feature_flags={"restaurant": True, "takeaway": True},
            updated_at=now,
        )
        plan = SimpleNamespace(
            feature_flags={"restaurant": True, "takeaway": False}
        )
        db = AsyncMock()
        db.get.return_value = company
        db.scalar.side_effect = [profile, plan]

        rows = await CompanyModuleAccessService(db).list_for_company(
            company_id,
            permissions=["fb.order.create", "takeaway.catalog.view"],
        )

        db.get.assert_awaited_once_with(Company, company_id)
        by_key = {row.module_key: row for row in rows}
        self.assertTrue(by_key["restaurant_pos"].effective_access)
        self.assertTrue(by_key["takeaway_pos"].company_enabled)
        self.assertFalse(by_key["takeaway_pos"].plan_included)
        self.assertEqual(by_key["takeaway_pos"].reason_code, "not_in_plan")
        self.assertIsNone(by_key["restaurant_pos"].audit_id)

    async def test_platform_update_is_locked_audited_and_syncs_legacy_guard(self) -> None:
        company_id = uuid.uuid4()
        operator_id = uuid.uuid4()
        audit_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        company = SimpleNamespace(id=company_id, is_active=True, updated_at=now)
        profile = SimpleNamespace(
            plan_code="starter",
            feature_flags={"restaurant": True},
            plan_limits={},
            updated_at=now,
        )
        plan = SimpleNamespace(feature_flags={"restaurant": True})
        audit_row = SimpleNamespace(
            id=audit_id,
            user_id=operator_id,
            created_at=now,
            new_value={"module_key": "restaurant_pos"},
        )
        db = AsyncMock()
        db.add = MagicMock()
        db.scalar.side_effect = [company, profile, profile, plan]
        db.get.return_value = company
        db.scalars.return_value = [audit_row]
        service = CompanyModuleAccessService(db, operator_id=operator_id)

        row = await service.update_company_module(
            company_id,
            "restaurant_pos",
            CompanyModuleAccessUpdate(enabled=False, reason="พักโมดูลเพื่อทดสอบ"),
            ip_address="127.0.0.1",
            user_agent="test",
        )

        self.assertFalse(profile.feature_flags["restaurant_pos"])
        self.assertFalse(profile.feature_flags["restaurant"])
        db.commit.assert_awaited_once()
        audit = next(
            call.args[0]
            for call in db.add.call_args_list
            if isinstance(call.args[0], AuditLog)
        )
        self.assertEqual(audit.action, "platform.company.module.update")
        self.assertEqual(audit.new_value["reason"], "พักโมดูลเพื่อทดสอบ")
        self.assertFalse(row.effective_access)
        self.assertEqual(row.reason_code, "company_disabled")
        self.assertEqual(row.audit_id, audit_id)


if __name__ == "__main__":
    unittest.main()
