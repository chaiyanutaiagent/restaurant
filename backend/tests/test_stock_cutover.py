from __future__ import annotations

import unittest

from app.services.stock_cutover_service import make_preview_token, q4


class StockCutoverTokenTests(unittest.TestCase):
    def test_preview_token_is_deterministic_across_key_order(self) -> None:
        first = {"brand_id": "brand-1", "candidates": [{"qty": 10, "product_id": "p-1"}]}
        second = {"candidates": [{"product_id": "p-1", "qty": 10}], "brand_id": "brand-1"}

        self.assertEqual(make_preview_token(first), make_preview_token(second))
        self.assertEqual(len(make_preview_token(first)), 64)

    def test_preview_token_changes_when_balance_changes(self) -> None:
        before = {"candidates": [{"product_id": "p-1", "qty": 10.0}]}
        after = {"candidates": [{"product_id": "p-1", "qty": 9.0}]}

        self.assertNotEqual(make_preview_token(before), make_preview_token(after))

    def test_quantity_is_rounded_to_stock_precision(self) -> None:
        self.assertEqual(str(q4("1.23456")), "1.2346")


if __name__ == "__main__":
    unittest.main()
