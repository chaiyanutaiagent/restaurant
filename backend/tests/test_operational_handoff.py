from decimal import Decimal
import unittest
import uuid

from app.services.operational_handoff_service import (
    SALE_COMPLETED_EVENT,
    sale_completed_idempotency_key,
    sale_completed_payload,
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


if __name__ == "__main__":
    unittest.main()
