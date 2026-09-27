from __future__ import annotations

import unittest

from app.cli.prepare_sketch_biz_test_staff import TEST_STAFF_PROFILES
from app.services.role_preset_service import ROLE_PRESET_POLICIES


class SketchBizTestStaffContractTests(unittest.TestCase):
    def test_one_named_profile_exists_for_every_role_preset(self) -> None:
        expected = {policy.key for policy in ROLE_PRESET_POLICIES}
        actual = {profile.preset_key for profile in TEST_STAFF_PROFILES}
        self.assertEqual(actual, expected)
        self.assertEqual(len(TEST_STAFF_PROFILES), len(expected))
        self.assertEqual(len({profile.username for profile in TEST_STAFF_PROFILES}), len(expected))
        self.assertTrue(all(profile.first_name and profile.last_name for profile in TEST_STAFF_PROFILES))


if __name__ == "__main__":
    unittest.main()
