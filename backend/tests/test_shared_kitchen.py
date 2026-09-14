from __future__ import annotations

from datetime import date
from decimal import Decimal
import unittest
import uuid

from app.config import settings
from app.routers.company_kitchen import require_write_activation
from app.services.admin_service import forbidden_branch_role_permissions
from app.services.role_preset_service import COMPANY_OWNER_PERMISSION_CODES
from app.services.shared_kitchen_service import (
    aggregate_demands,
    expected_conversion_factor,
    plan_fifo_allocations,
    unit_dimension,
)


class SharedKitchenUnitPolicyTests(unittest.TestCase):
    def test_mass_and_volume_conversion_are_explicit(self) -> None:
        self.assertEqual(expected_conversion_factor("kg", "g"), Decimal("1000.00000000"))
        self.assertEqual(expected_conversion_factor("g", "kg"), Decimal("0.00100000"))
        self.assertEqual(expected_conversion_factor("l", "ml"), Decimal("1000.00000000"))
        self.assertEqual(unit_dimension("ชิ้น"), "count")

    def test_cross_dimension_conversion_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "คนละมิติ"):
            expected_conversion_factor("kg", "ml")

    def test_unknown_unit_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "ไม่รองรับหน่วย"):
            unit_dimension("ลังพิเศษ")


class SharedKitchenFifoTests(unittest.TestCase):
    def test_fifo_spans_lots_without_going_negative(self) -> None:
        first, second = uuid.uuid4(), uuid.uuid4()
        allocations = plan_fifo_allocations(
            [
                (first, Decimal("3"), Decimal("10")),
                (second, Decimal("5"), Decimal("12")),
            ],
            Decimal("6"),
        )
        self.assertEqual(
            allocations,
            [
                (first, Decimal("3.0000"), Decimal("10.0000")),
                (second, Decimal("3.0000"), Decimal("12.0000")),
            ],
        )

    def test_fifo_rejects_insufficient_stock(self) -> None:
        with self.assertRaisesRegex(ValueError, "ขาด 2.0000"):
            plan_fifo_allocations(
                [(uuid.uuid4(), Decimal("3"), Decimal("10"))],
                Decimal("5"),
            )


class SharedKitchenOwnershipTests(unittest.TestCase):
    def test_demand_aggregation_keeps_brand_and_product_dimensions(self) -> None:
        brand_a, brand_b, product, day = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), date(2026, 9, 14)
        result = aggregate_demands(
            [
                (brand_a, product, day, Decimal("2")),
                (brand_a, product, day, Decimal("3")),
                (brand_b, product, day, Decimal("7")),
            ]
        )
        self.assertEqual(result[(brand_a, product, day)], Decimal("5.0000"))
        self.assertEqual(result[(brand_b, product, day)], Decimal("7.0000"))

    def test_company_owner_has_shared_kitchen_permissions(self) -> None:
        self.assertIn("company.kitchen.view", COMPANY_OWNER_PERMISSION_CODES)
        self.assertIn("company.kitchen.manage", COMPANY_OWNER_PERMISSION_CODES)
        self.assertEqual(
            forbidden_branch_role_permissions({"company.kitchen.view", "company.kitchen.manage"}),
            ["company.kitchen.manage", "company.kitchen.view"],
        )

    def test_write_path_is_dark_by_default(self) -> None:
        original = settings.company_kitchen_writes_enabled
        settings.company_kitchen_writes_enabled = False
        try:
            with self.assertRaisesRegex(Exception, "rollout sign-off"):
                require_write_activation()
        finally:
            settings.company_kitchen_writes_enabled = original


if __name__ == "__main__":
    unittest.main()
