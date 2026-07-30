from __future__ import annotations

from decimal import Decimal
import unittest

from app.services.replenishment_service import (
    calculate_suggested_order,
    choose_forecast_usage,
)


class ReplenishmentCalculationTests(unittest.TestCase):
    def test_sparse_history_uses_latest_day(self) -> None:
        forecast, method = choose_forecast_usage(
            latest_day_usage=Decimal("8"),
            open_day_usage=[Decimal("8"), Decimal("5")],
            method="auto",
        )
        self.assertEqual(forecast, Decimal("8.0000"))
        self.assertEqual(method, "latest_day")

    def test_seven_open_days_use_average(self) -> None:
        forecast, method = choose_forecast_usage(
            latest_day_usage=Decimal("20"),
            open_day_usage=[
                Decimal("7"),
                Decimal("6"),
                Decimal("5"),
                Decimal("4"),
                Decimal("3"),
                Decimal("2"),
                Decimal("1"),
            ],
            method="auto",
        )
        self.assertEqual(forecast, Decimal("4.0000"))
        self.assertEqual(method, "average_7_open_days")

    def test_suggestion_deducts_store_and_incoming_then_rounds_pack(self) -> None:
        result = calculate_suggested_order(
            forecast_qty=Decimal("10"),
            safety_stock_percent=Decimal("10"),
            safety_stock_qty=Decimal("0"),
            store_on_hand=Decimal("2"),
            confirmed_incoming=Decimal("1"),
            pack_size=Decimal("3"),
            minimum_order_qty=Decimal("0"),
        )
        self.assertEqual(result["safety_stock_qty"], Decimal("1.0000"))
        self.assertEqual(result["raw_suggested_qty"], Decimal("8.0000"))
        self.assertEqual(result["suggested_qty"], Decimal("9.0000"))

    def test_nonpositive_gap_does_not_force_minimum_order(self) -> None:
        result = calculate_suggested_order(
            forecast_qty=Decimal("5"),
            safety_stock_percent=Decimal("10"),
            store_on_hand=Decimal("10"),
            confirmed_incoming=Decimal("2"),
            pack_size=Decimal("1"),
            minimum_order_qty=Decimal("6"),
        )
        self.assertEqual(result["suggested_qty"], Decimal("0.0000"))


if __name__ == "__main__":
    unittest.main()
