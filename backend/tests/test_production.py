from __future__ import annotations

from decimal import Decimal
import unittest

from app.services.production_service import calculate_production_required


class ProductionPlanningTests(unittest.TestCase):
    def test_required_subtracts_ready_and_active_batches(self) -> None:
        self.assertEqual(
            calculate_production_required(
                Decimal("10"),
                Decimal("3"),
                Decimal("2"),
            ),
            Decimal("5"),
        )

    def test_required_never_goes_below_zero(self) -> None:
        self.assertEqual(
            calculate_production_required(
                Decimal("5"),
                Decimal("8"),
                Decimal("1"),
            ),
            Decimal("0"),
        )

    def test_negative_available_increases_required(self) -> None:
        self.assertEqual(
            calculate_production_required(
                Decimal("5"),
                Decimal("-2"),
                Decimal("1"),
            ),
            Decimal("6"),
        )


if __name__ == "__main__":
    unittest.main()
