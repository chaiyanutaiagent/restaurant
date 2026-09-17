from __future__ import annotations

from decimal import Decimal
import unittest
import uuid

from pydantic import ValidationError

from app.models.takeaway import (
    TakeawayCentralOrder,
    TakeawayCreditTopupRequest,
    TakeawayProductionLine,
    TakeawayTransfer,
)
from app.schemas.takeaway import (
    TakeawayRecipeCreate,
    TakeawayReplenishmentPolicyUpsert,
)
from app.services.takeaway_central_policy import (
    convert_quantity,
    recipe_cost_per_yield,
    suggested_replenishment_quantity,
)


class TakeawayCentralParityTests(unittest.TestCase):
    def test_unit_conversion_rejects_incompatible_families(self) -> None:
        self.assertEqual(convert_quantity(Decimal("1.5"), "kg", "g"), Decimal("1500.0000"))
        with self.assertRaises(ValueError):
            convert_quantity(Decimal("1"), "kg", "ml")

    def test_recipe_cost_applies_yield_loss(self) -> None:
        self.assertEqual(
            recipe_cost_per_yield(Decimal("90"), Decimal("10"), Decimal("10")),
            Decimal("10.0000"),
        )

    def test_replenishment_rounds_up_to_pack_and_minimum(self) -> None:
        suggestion = suggested_replenishment_quantity(
            average_daily_demand=Decimal("3"),
            lead_time_days=2,
            safety_stock_percent=Decimal("25"),
            safety_stock_qty=Decimal("1"),
            on_hand_qty=Decimal("2"),
            confirmed_incoming_qty=Decimal("0"),
            pack_size=Decimal("4"),
            minimum_order_qty=Decimal("6"),
        )
        self.assertEqual(suggestion, Decimal("8.0000"))

    def test_recipe_rejects_direct_self_reference(self) -> None:
        item_id = uuid.uuid4()
        with self.assertRaises(ValidationError):
            TakeawayRecipeCreate(
                brand_id=uuid.uuid4(),
                output_item_id=item_id,
                name="สูตรวนซ้ำ",
                yield_qty=Decimal("1"),
                yield_unit="ชิ้น",
                ingredients=[
                    {
                        "item_id": item_id,
                        "sku": "SELF",
                        "quantity": Decimal("1"),
                        "unit": "ชิ้น",
                    }
                ],
            )

    def test_replenishment_policy_requires_positive_pack(self) -> None:
        with self.assertRaises(ValidationError):
            TakeawayReplenishmentPolicyUpsert(
                brand_id=uuid.uuid4(),
                branch_id=uuid.uuid4(),
                item_id=uuid.uuid4(),
                pack_size=Decimal("0"),
            )

    def test_parity_models_include_discrepancy_waste_and_topup(self) -> None:
        self.assertIn("discrepancy_status", TakeawayCentralOrder.__table__.columns)
        self.assertIn("waste_qty", TakeawayProductionLine.__table__.columns)
        self.assertIn("discrepancy_status", TakeawayTransfer.__table__.columns)
        self.assertEqual(TakeawayCreditTopupRequest.__tablename__, "takeaway_credit_topup_requests")


if __name__ == "__main__":
    unittest.main()
