from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import unittest
import uuid

from app.routers.restaurant import _serialize_order_center_session
from app.schemas.pos import HoldDraftRead


class WP51HoldOrderCenterTests(unittest.TestCase):
    def test_hold_read_exposes_server_context_without_changing_authority(self) -> None:
        now = datetime.now(timezone.utc)
        value = HoldDraftRead.model_validate(
            {
                "id": uuid.uuid4(),
                "draft_no": "HD20260921-0001",
                "company_id": uuid.uuid4(),
                "brand_id": None,
                "branch_id": uuid.uuid4(),
                "location_id": uuid.uuid4(),
                "origin_shift_id": uuid.uuid4(),
                "owner_user_id": uuid.uuid4(),
                "owner_display": "Cashier A",
                "assignee_user_id": None,
                "assignee_display": None,
                "origin_device_id": None,
                "origin_device_code": "COUNTER-01",
                "origin_shift_number": "S20260921-001",
                "location_name": "คลังหน้าร้าน",
                "label": "โต๊ะ A1",
                "source_type": "restaurant_table",
                "content": {"items": []},
                "pricing_context": {},
                "pricing_snapshot": {},
                "status": "active",
                "version": 4,
                "expires_at": now,
                "created_at": now,
                "updated_at": now,
            }
        )

        self.assertEqual(value.owner_display, "Cashier A")
        self.assertEqual(value.origin_shift_number, "S20260921-001")
        self.assertEqual(value.version, 4)

    def test_order_center_uses_only_non_cancelled_orders_and_canonical_item_states(self) -> None:
        now = datetime.now(timezone.utc)
        active_1 = SimpleNamespace(
            status="submitted",
            order_number="ORD-001",
            created_at=now,
            items=[
                SimpleNamespace(unit_price=Decimal("50"), qty=2, status="pending"),
                SimpleNamespace(unit_price=Decimal("30"), qty=1, status="done"),
            ],
        )
        active_2 = SimpleNamespace(
            status="submitted",
            order_number="ORD-002",
            created_at=now,
            items=[SimpleNamespace(unit_price=Decimal("20"), qty=1, status="served")],
        )
        cancelled = SimpleNamespace(
            status="cancelled",
            order_number="ORD-X",
            created_at=now,
            items=[SimpleNamespace(unit_price=Decimal("999"), qty=1, status="cooking")],
        )
        session = SimpleNamespace(
            id=uuid.uuid4(),
            status="open",
            table_id=uuid.uuid4(),
            queue_number=None,
            customer_name="Customer",
            customer_phone=None,
            note="No peanuts",
            opened_at=now,
            updated_at=now,
            closed_at=None,
            sale_order_id=None,
            orders=[active_1, active_2, cancelled],
        )

        result = _serialize_order_center_session(session, SimpleNamespace(name="A1"))

        self.assertEqual(result["order_numbers"], ["ORD-001", "ORD-002"])
        self.assertEqual(result["latest_order_number"], "ORD-002")
        self.assertEqual(result["pending_count"], 2)
        self.assertEqual(result["ready_count"], 1)
        self.assertEqual(result["served_count"], 1)
        self.assertEqual(result["cooking_count"], 0)
        self.assertEqual(result["total_amount"], 150.0)


if __name__ == "__main__":
    unittest.main()
