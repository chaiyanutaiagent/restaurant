from __future__ import annotations

import unittest

from app.services.fb_setup import (
    DiningTableZonePlan,
    normalize_table_prefix,
    normalize_table_zone,
    plan_dining_tables,
    plan_dining_table_zones,
    service_mode_for,
)


class FBSetupTests(unittest.TestCase):
    def test_store_with_tables_maps_to_both_for_legacy_compatibility(self) -> None:
        self.assertEqual(service_mode_for(True), "both")

    def test_store_without_tables_maps_to_quick_service(self) -> None:
        self.assertEqual(service_mode_for(False), "quick_service")

    def test_table_plan_normalizes_prefix_and_uses_stable_sort_order(self) -> None:
        plan = plan_dining_tables(prefix="  โต๊ะ   A  ", count=3, capacity=4)

        self.assertEqual(
            [(item.name, item.capacity, item.sort_order) for item in plan],
            [
                ("โต๊ะ A 1", 4, 1),
                ("โต๊ะ A 2", 4, 2),
                ("โต๊ะ A 3", 4, 3),
            ],
        )

    def test_empty_prefix_falls_back_to_thai_table_label(self) -> None:
        self.assertEqual(normalize_table_prefix("   "), "โต๊ะ")

    def test_multiple_zones_keep_their_own_counts_and_capacities(self) -> None:
        plan = plan_dining_table_zones(
            [
                DiningTableZonePlan(
                    zone_name="ห้องแอร์",
                    table_name_prefix="A",
                    table_count=2,
                    table_capacity=4,
                ),
                DiningTableZonePlan(
                    zone_name="สวน",
                    table_name_prefix="G",
                    table_count=3,
                    table_capacity=6,
                ),
            ]
        )

        self.assertEqual(
            [(item.name, item.zone, item.capacity, item.sort_order) for item in plan],
            [
                ("A 1", "ห้องแอร์", 4, 1),
                ("A 2", "ห้องแอร์", 4, 2),
                ("G 1", "สวน", 6, 3),
                ("G 2", "สวน", 6, 4),
                ("G 3", "สวน", 6, 5),
            ],
        )

    def test_duplicate_zone_names_are_rejected_after_normalization(self) -> None:
        with self.assertRaisesRegex(ValueError, "ชื่อโซน"):
            plan_dining_table_zones(
                [
                    DiningTableZonePlan("โซน A", "A", 1, 4),
                    DiningTableZonePlan("  โซน   A ", "B", 1, 2),
                ]
            )

    def test_duplicate_generated_table_names_across_zones_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "ชื่อโต๊ะ"):
            plan_dining_table_zones(
                [
                    DiningTableZonePlan("ชั้น 1", "T", 1, 4),
                    DiningTableZonePlan("ชั้น 2", "T", 1, 6),
                ]
            )

    def test_total_tables_are_limited_across_zones(self) -> None:
        with self.assertRaisesRegex(ValueError, "รวมไม่เกิน"):
            plan_dining_table_zones(
                [
                    DiningTableZonePlan("ชั้น 1", "A", 60, 4),
                    DiningTableZonePlan("ชั้น 2", "B", 41, 4),
                ]
            )

    def test_empty_zone_falls_back_to_general_zone(self) -> None:
        self.assertEqual(normalize_table_zone("   "), "โซนทั่วไป")

if __name__ == "__main__":
    unittest.main()
