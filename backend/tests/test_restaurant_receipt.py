from __future__ import annotations

from types import SimpleNamespace
import unittest

from app.routers.restaurant import _branch_promptpay_payload


class RestaurantReceiptPromptPayTests(unittest.TestCase):
    def test_branch_targets_generate_different_receipt_qr_payloads(self) -> None:
        first_branch = SimpleNamespace(promptpay_target="0812345678")
        second_branch = SimpleNamespace(promptpay_target="0898765432")

        first_payload = _branch_promptpay_payload(first_branch)
        second_payload = _branch_promptpay_payload(second_branch)

        self.assertIsNotNone(first_payload)
        self.assertIsNotNone(second_payload)
        self.assertNotEqual(first_payload, second_payload)

    def test_missing_or_invalid_branch_target_hides_receipt_qr(self) -> None:
        self.assertIsNone(_branch_promptpay_payload(None))
        self.assertIsNone(_branch_promptpay_payload(SimpleNamespace(promptpay_target=None)))
        self.assertIsNone(_branch_promptpay_payload(SimpleNamespace(promptpay_target="1234")))


if __name__ == "__main__":
    unittest.main()
