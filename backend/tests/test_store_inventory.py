from __future__ import annotations

from decimal import Decimal
import unittest

from app.services.store_inventory_service import calculate_recipe_usage


class StoreRecipeUsageTests(unittest.TestCase):
    def test_usage_scales_with_sold_quantity(self) -> None:
        self.assertEqual(
            calculate_recipe_usage(
                Decimal("2"),
                Decimal("3"),
                Decimal("1"),
                Decimal("0"),
            ),
            Decimal("6.0000"),
        )

    def test_loss_reduces_effective_yield(self) -> None:
        self.assertEqual(
            calculate_recipe_usage(
                Decimal("8"),
                Decimal("4"),
                Decimal("10"),
                Decimal("20"),
            ),
            Decimal("4.0000"),
        )

    def test_invalid_full_loss_does_not_divide_by_zero(self) -> None:
        self.assertEqual(
            calculate_recipe_usage(
                Decimal("1"),
                Decimal("1"),
                Decimal("1"),
                Decimal("100"),
            ),
            Decimal("10000.0000"),
        )


if __name__ == "__main__":
    unittest.main()
