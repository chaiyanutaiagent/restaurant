from decimal import Decimal
import unittest

from app.services.recipe_service import convert_quantity, unit_conversion_factor
from app.services.restaurant_report_service import build_financial_reconciliation


class RecipeCostingUnitConversionTests(unittest.TestCase):
    def test_weight_and_volume_aliases_are_converted(self) -> None:
        self.assertEqual(convert_quantity(Decimal("1.25"), "kg", "g"), Decimal("1250.0000"))
        self.assertEqual(convert_quantity(Decimal("2"), "ลิตร", "ml"), Decimal("2000.0000"))
        self.assertEqual(unit_conversion_factor("ขีด", "กรัม"), Decimal("100.00000000"))

    def test_identical_auditable_units_do_not_require_a_conversion_table(self) -> None:
        self.assertEqual(convert_quantity(Decimal("3"), "piece", "piece"), Decimal("3.0000"))
        self.assertEqual(convert_quantity(Decimal("3"), "piece", "PCS"), Decimal("3.0000"))
        self.assertEqual(convert_quantity(Decimal("3"), "ชิ้น", "PCS"), Decimal("3.0000"))

    def test_missing_unknown_or_incompatible_conversion_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "ต้องระบุหน่วย"):
            convert_quantity(Decimal("1"), "", "g")
        with self.assertRaisesRegex(ValueError, "ไม่พบกฎแปลงหน่วย"):
            convert_quantity(Decimal("1"), "bag", "g")
        with self.assertRaisesRegex(ValueError, "คนละประเภท"):
            convert_quantity(Decimal("1"), "kg", "ml")


class RestaurantFinancialReconciliationTests(unittest.TestCase):
    def test_equal_source_branch_and_payment_totals_reconcile(self) -> None:
        result = build_financial_reconciliation(
            source_sales_total=Decimal("1250.00"),
            branch_rows_total=Decimal("1250.00"),
            source_payment_total=Decimal("1250.00"),
        )
        self.assertTrue(result["sales"]["is_reconciled"])
        self.assertTrue(result["payments"]["is_reconciled"])

    def test_payment_difference_is_exposed_without_hiding_the_delta(self) -> None:
        result = build_financial_reconciliation(
            source_sales_total=Decimal("1250.00"),
            branch_rows_total=Decimal("1250.00"),
            source_payment_total=Decimal("1249.50"),
        )
        self.assertEqual(result["payments"]["delta"], Decimal("-0.50"))
        self.assertFalse(result["payments"]["is_reconciled"])


if __name__ == "__main__":
    unittest.main()
