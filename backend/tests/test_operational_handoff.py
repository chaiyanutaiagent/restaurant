from decimal import Decimal
import unittest
import uuid

from app.services.operational_handoff_service import (
    SALE_COMPLETED_EVENT,
    SALE_STATE_CHANGED_EVENT,
    sale_completed_idempotency_key,
    sale_completed_payload,
    sale_state_changed_idempotency_key,
    sale_state_changed_payload,
)


class OperationalHandoffContractTests(unittest.TestCase):
    def test_sale_contract_is_deterministic_and_contains_no_customer_data(self) -> None:
        order_id = uuid.uuid4()
        payload = sale_completed_payload(
            order_id=order_id,
            order_number="SO20260801-0001",
            total_amount=Decimal("109.5"),
            item_count=2,
            payment_methods=["promptpay", "cash", "cash"],
        )
        self.assertEqual(payload["schema"], "restaurant.sale.completed")
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["total_amount"], "109.50")
        self.assertEqual(payload["payment_methods"], ["cash", "promptpay"])
        self.assertNotIn("customer_name", payload)
        self.assertNotIn("customer_phone", payload)

    def test_idempotency_key_is_one_per_sale(self) -> None:
        order_id = uuid.uuid4()
        expected = f"{SALE_COMPLETED_EVENT}:{order_id}"
        self.assertEqual(sale_completed_idempotency_key(order_id), expected)
        self.assertEqual(sale_completed_idempotency_key(order_id), expected)

    def test_sale_state_contract_is_deterministic_and_contains_no_customer_data(self) -> None:
        order_id = uuid.uuid4()
        payload = sale_state_changed_payload(
            order_id=order_id,
            order_number="SO20260914-0001",
            source_status="partially_refunded",
            total_amount=Decimal("100"),
            refund_amount=Decimal("25.5"),
        )
        self.assertEqual(payload["schema"], "pos.sale.state.changed")
        self.assertEqual(payload["source_status"], "partially_refunded")
        self.assertEqual(payload["net_amount"], "74.50")
        self.assertNotIn("customer_name", payload)
        self.assertNotIn("customer_phone", payload)
        expected = f"{SALE_STATE_CHANGED_EVENT}:{order_id}:partially_refunded:25.50"
        self.assertEqual(
            sale_state_changed_idempotency_key(
                order_id,
                "partially_refunded",
                Decimal("25.5"),
            ),
            expected,
        )


if __name__ == "__main__":
    unittest.main()
