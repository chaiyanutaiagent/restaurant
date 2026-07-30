from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.schemas.restaurant import RawMaterialCreate
from app.services.recipe_service import resolve_recipe_inventory_role


class RecipeInventoryRoleTests(unittest.TestCase):
    def test_production_input_defaults_to_raw(self) -> None:
        self.assertEqual(
            resolve_recipe_inventory_role(
                "production_recipe",
                is_output=False,
                current_role=None,
            ),
            "central_raw",
        )

    def test_nested_production_input_defaults_to_ready(self) -> None:
        self.assertEqual(
            resolve_recipe_inventory_role(
                "production_recipe",
                is_output=False,
                current_role=None,
                has_production_recipe=True,
            ),
            "central_ready",
        )

    def test_production_output_is_ready(self) -> None:
        self.assertEqual(
            resolve_recipe_inventory_role(
                "production_recipe",
                is_output=True,
                current_role=None,
            ),
            "central_ready",
        )

    def test_menu_input_defaults_to_ready(self) -> None:
        self.assertEqual(
            resolve_recipe_inventory_role(
                "menu_recipe",
                is_output=False,
                current_role=None,
            ),
            "central_ready",
        )

    def test_menu_input_preserves_store_local(self) -> None:
        self.assertEqual(
            resolve_recipe_inventory_role(
                "menu_recipe",
                is_output=False,
                current_role="store_local",
            ),
            "store_local",
        )

    def test_menu_output_does_not_create_stock_role(self) -> None:
        self.assertIsNone(
            resolve_recipe_inventory_role(
                "menu_recipe",
                is_output=True,
                current_role=None,
            )
        )

    def test_conflicting_role_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "CENTRAL-READY"):
            resolve_recipe_inventory_role(
                "production_recipe",
                is_output=True,
                current_role="store_local",
            )
        with self.assertRaisesRegex(ValueError, "STORE-STOCK"):
            resolve_recipe_inventory_role(
                "menu_recipe",
                is_output=False,
                current_role="central_raw",
            )

    def test_quick_add_rejects_not_stocked_role(self) -> None:
        with self.assertRaises(ValidationError):
            RawMaterialCreate(
                sku="RAW-TEST",
                name="Test",
                inventory_role="not_stocked",
            )


if __name__ == "__main__":
    unittest.main()
