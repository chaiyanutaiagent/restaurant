from __future__ import annotations

import unittest

from app.services.role_preset_service import ROLE_PRESET_POLICIES
from app.services.shared_reporting_service import (
    ENTRY_ROUTE_BY_MODULE,
    MODULE_BY_BUSINESS_TYPE,
)


class TakeawayWP23SimulationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.permissions = {
            preset.key: set(preset.permission_codes)
            for preset in ROLE_PRESET_POLICIES
        }

    def test_each_operator_role_has_only_its_takeaway_workflow(self) -> None:
        owner = self.permissions["company-owner"]
        brand = self.permissions["brand-manager"]
        branch = self.permissions["branch-manager"]
        cashier = self.permissions["cashier"]
        kitchen = self.permissions["kitchen-staff"]

        self.assertIn("takeaway.import.apply", owner)
        self.assertIn("takeaway.production.manage", brand)
        self.assertNotIn("takeaway.import.apply", brand)
        self.assertIn("takeaway.central_order.create", branch)
        self.assertNotIn("takeaway.central_order.manage", branch)
        self.assertIn("takeaway.sale.create", cashier)
        self.assertNotIn("takeaway.stock.manage", cashier)
        self.assertEqual(
            {permission for permission in kitchen if permission.startswith("takeaway.")},
            {"takeaway.kitchen.manage"},
        )

    def test_shared_erp_report_has_exactly_three_business_dimensions(self) -> None:
        self.assertEqual(
            MODULE_BY_BUSINESS_TYPE,
            {
                "restaurant": "restaurant_pos",
                "takeaway": "takeaway_pos",
                "retail_pos": "retail_pos",
            },
        )
        self.assertEqual(
            set(ENTRY_ROUTE_BY_MODULE),
            {"restaurant_pos", "takeaway_pos", "retail_pos"},
        )
        self.assertEqual(len(set(ENTRY_ROUTE_BY_MODULE.values())), 3)


if __name__ == "__main__":
    unittest.main()
