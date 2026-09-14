from __future__ import annotations

from decimal import Decimal
import unittest

from app.config import settings
from app.routers.company_distribution import require_write_activation
from app.services.admin_service import forbidden_branch_role_permissions
from app.services.distribution_service import expected_business_type, reconciliation
from app.services.role_preset_service import COMPANY_OWNER_PERMISSION_CODES


class DistributionPolicyTests(unittest.TestCase):
    def test_all_pos_modules_have_explicit_brand_business_type(self) -> None:
        self.assertEqual(expected_business_type("restaurant_pos"), "restaurant")
        self.assertEqual(expected_business_type("takeaway_pos"), "takeaway")
        self.assertEqual(expected_business_type("retail_pos"), "retail_pos")
        with self.assertRaisesRegex(ValueError, "ไม่รองรับโมดูล"):
            expected_business_type("hotel_pms")

    def test_reconciliation_keeps_in_transit_and_net_received_separate(self) -> None:
        result = reconciliation(Decimal("10"), Decimal("7"), Decimal("2"), Decimal("1"))
        self.assertEqual(result["in_transit_qty"], Decimal("1.0000"))
        self.assertEqual(result["net_received_qty"], Decimal("6.0000"))

    def test_reconciliation_rejects_impossible_totals(self) -> None:
        with self.assertRaisesRegex(ValueError, "มากกว่ายอดส่ง"):
            reconciliation(Decimal("10"), Decimal("9"), Decimal("2"), Decimal("0"))
        with self.assertRaisesRegex(ValueError, "มากกว่ายอดที่รับ"):
            reconciliation(Decimal("10"), Decimal("8"), Decimal("0"), Decimal("9"))

    def test_distribution_permissions_are_company_only(self) -> None:
        self.assertIn("company.distribution.view", COMPANY_OWNER_PERMISSION_CODES)
        self.assertIn("company.distribution.manage", COMPANY_OWNER_PERMISSION_CODES)
        self.assertEqual(
            forbidden_branch_role_permissions({"company.distribution.view", "company.distribution.manage"}),
            ["company.distribution.manage", "company.distribution.view"],
        )

    def test_write_path_is_dark_by_default(self) -> None:
        original = settings.company_distribution_writes_enabled
        settings.company_distribution_writes_enabled = False
        try:
            with self.assertRaisesRegex(Exception, "rollout sign-off"):
                require_write_activation()
        finally:
            settings.company_distribution_writes_enabled = original


if __name__ == "__main__":
    unittest.main()
