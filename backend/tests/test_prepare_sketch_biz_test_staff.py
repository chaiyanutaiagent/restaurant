from __future__ import annotations

import unittest

from app.cli.prepare_sketch_biz_test_staff import TEST_STAFF_PROFILES
from app.services.role_preset_service import ROLE_PRESET_POLICIES


class SketchBizTestStaffContractTests(unittest.TestCase):
    def test_named_profiles_cover_every_role_with_separate_workspace_staff(self) -> None:
        expected = {policy.key for policy in ROLE_PRESET_POLICIES}
        actual = {profile.preset_key for profile in TEST_STAFF_PROFILES}
        self.assertEqual(actual, expected)
        self.assertEqual(len(TEST_STAFF_PROFILES), 37)
        self.assertEqual(len({profile.username for profile in TEST_STAFF_PROFILES}), 37)
        self.assertTrue(all(profile.first_name and profile.last_name for profile in TEST_STAFF_PROFILES))
        shared = [profile for profile in TEST_STAFF_PROFILES if profile.workspace_key is None]
        self.assertEqual(
            {profile.preset_key for profile in shared},
            {"company-owner", "accountant", "purchasing", "hr", "auditor"},
        )
        counts = {
            key: sum(profile.workspace_key == key for profile in TEST_STAFF_PROFILES)
            for key in ("krua-pa-pla-khuen", "the-loft-kitchen", "the-loft-mini-mart", "chambo")
        }
        self.assertEqual(
            counts,
            {
                "krua-pa-pla-khuen": 8,
                "the-loft-kitchen": 8,
                "the-loft-mini-mart": 6,
                "chambo": 10,
            },
        )
        retail_roles = {
            profile.preset_key
            for profile in TEST_STAFF_PROFILES
            if profile.workspace_key == "the-loft-mini-mart"
        }
        self.assertNotIn("kitchen-manager", retail_roles)
        self.assertNotIn("kitchen-staff", retail_roles)
        takeaway_roles = {
            profile.preset_key
            for profile in TEST_STAFF_PROFILES
            if profile.workspace_key == "chambo"
        }
        self.assertEqual(
            takeaway_roles,
            {"brand-manager", "area-manager", "branch-manager", "takeaway-store-operator",
             "takeaway-cashier", "takeaway-branch-manager", "takeaway-stock-receiving", "takeaway-central-kitchen"},
        )
        self.assertEqual(
            sum(profile.preset_key == "takeaway-store-operator" for profile in TEST_STAFF_PROFILES),
            3,
        )


if __name__ == "__main__":
    unittest.main()
