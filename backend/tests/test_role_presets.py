from __future__ import annotations

import unittest
import uuid

from app.models.role import Permission
from app.services.admin_service import forbidden_branch_role_permissions
from app.services.role_preset_service import (
    COMPANY_OWNER_PERMISSION_CODES,
    ROLE_PRESET_POLICIES,
    ROLE_PRESET_POLICY_VERSION,
    build_role_preset_reads,
    missing_role_preset_permissions,
)
from app.utils.seed_permissions import PERMISSIONS


class RolePresetPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policies = {policy.key: policy for policy in ROLE_PRESET_POLICIES}
        self.registered_codes = {item["code"] for item in PERMISSIONS}

    def test_phase_two_gate_personas_are_canonical(self) -> None:
        self.assertEqual(
            list(self.policies),
            [
                "company-owner",
                "brand-manager",
                "branch-manager",
                "cashier",
                "kitchen-staff",
            ],
        )
        self.assertEqual(ROLE_PRESET_POLICY_VERSION, "2026-08-01")

    def test_every_preset_uses_registered_permissions_without_duplicates(self) -> None:
        for policy in ROLE_PRESET_POLICIES:
            with self.subTest(policy=policy.key):
                self.assertEqual(len(policy.permission_codes), len(set(policy.permission_codes)))
                self.assertEqual(set(policy.permission_codes) - self.registered_codes, set())

    def test_company_owner_catalog_is_explicit_and_complete(self) -> None:
        self.assertEqual(set(COMPANY_OWNER_PERMISSION_CODES), self.registered_codes)

    def test_branch_assignable_presets_pass_central_permission_guard(self) -> None:
        for policy in ROLE_PRESET_POLICIES:
            if not policy.is_branch_assignable:
                continue
            with self.subTest(policy=policy.key):
                self.assertEqual(forbidden_branch_role_permissions(policy.permission_codes), [])

    def test_cashier_cannot_void_refund_override_or_access_finance_and_settings(self) -> None:
        codes = set(self.policies["cashier"].permission_codes)
        denied = {
            "pos.sale.void",
            "pos.discount.override",
            "pos.refund.create",
            "inventory.stock.adjust",
            "accounting.report.view",
            "fb.settings.manage",
        }
        self.assertEqual(codes.intersection(denied), set())
        self.assertIn("pos.sale.create", codes)
        self.assertIn("pos.discount.apply", codes)

    def test_kitchen_staff_is_station_scoped_and_kitchen_only(self) -> None:
        policy = self.policies["kitchen-staff"]
        self.assertEqual(policy.default_scope, "station")
        self.assertEqual(policy.allowed_scopes, ("station",))
        self.assertEqual(set(policy.permission_codes), {"fb.menu.view", "fb.kitchen.manage"})

    def test_missing_catalog_codes_disable_only_affected_presets(self) -> None:
        kitchen_permissions = [
            Permission(
                id=uuid.uuid4(),
                code=code,
                name=code,
                module="fb",
            )
            for code in self.policies["kitchen-staff"].permission_codes
        ]
        rows = {row.key: row for row in build_role_preset_reads(kitchen_permissions)}

        self.assertTrue(rows["kitchen-staff"].is_available)
        self.assertEqual(rows["kitchen-staff"].missing_permission_codes, [])
        self.assertFalse(rows["cashier"].is_available)
        self.assertIn("pos.sale.create", rows["cashier"].missing_permission_codes)

        missing = missing_role_preset_permissions(permission.code for permission in kitchen_permissions)
        self.assertNotIn("kitchen-staff", missing)
        self.assertIn("cashier", missing)


if __name__ == "__main__":
    unittest.main()
