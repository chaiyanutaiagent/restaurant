from __future__ import annotations

from decimal import Decimal
import unittest
import uuid

from app.config import validate_refund_runtime_config
from app.schemas.pos import RefundExecuteRequest, RefundQuoteCreateRequest
from app.services.approval_service import approval_request_hash, normalize_approval_request_payload
from app.services.refund_service import (
    BLOCKING_SHIFT_STATES,
    REFUND_POLICY_VERSION,
    SandboxRefundAdapter,
    provider_webhook_signature,
)


class WP46RefundContractTests(unittest.TestCase):
    def test_policy_and_blocking_states_are_explicit(self) -> None:
        self.assertEqual(REFUND_POLICY_VERSION, "wp46-refund-v1")
        self.assertTrue({"processing", "unknown", "cash_due", "needs_reconciliation", "tax_pending"}.issubset(BLOCKING_SHIFT_STATES))

    def test_sandbox_state_machine_is_deterministic(self) -> None:
        self.assertEqual(SandboxRefundAdapter.result("succeeded", 1), "succeeded")
        self.assertEqual(SandboxRefundAdapter.result("failed", 1), "failed")
        self.assertEqual(SandboxRefundAdapter.result("failed", 2), "succeeded")
        self.assertEqual(SandboxRefundAdapter.result("processing_then_succeeded", 1), "processing")
        self.assertEqual(SandboxRefundAdapter.result("processing_then_succeeded", 2, inquiry=True), "succeeded")
        self.assertEqual(SandboxRefundAdapter.result("unknown_then_succeeded", 1), "unknown")
        self.assertEqual(SandboxRefundAdapter.result("unknown_then_succeeded", 2, inquiry=True), "succeeded")
        self.assertEqual(SandboxRefundAdapter.result("unknown_persistent", 9, inquiry=True), "unknown")

    def test_webhook_signature_is_order_independent_and_tamper_evident(self) -> None:
        secret = "uat-refund-secret-123"
        first = provider_webhook_signature({"state": "succeeded", "sequence": 2}, secret)
        second = provider_webhook_signature({"sequence": 2, "state": "succeeded"}, secret)
        tampered = provider_webhook_signature({"sequence": 2, "state": "failed"}, secret)
        self.assertEqual(first, second)
        self.assertNotEqual(first, tampered)

    def test_refund_execute_approval_payload_is_canonical(self) -> None:
        payload = RefundExecuteRequest(
            quote_id=uuid.uuid4(),
            quote_hash="a" * 64,
            order_id=uuid.uuid4(),
            expected_order_version=3,
            total_amount=Decimal("107.00"),
            reason_code="customer_request",
            reason_note="ลูกค้าขอคืน",
            stock_disposition="none",
            provider_scenario="unknown_then_succeeded",
            idempotency_key="refund-execute-001",
            approval_token="secret-one-time-token",
        )
        raw = payload.model_dump(mode="json", exclude={"approval_token"})
        normalized = normalize_approval_request_payload("pos.refund.create", raw)
        self.assertNotIn("approval_token", normalized)
        self.assertEqual(normalized["quote_hash"], "a" * 64)
        self.assertEqual(approval_request_hash(normalized), approval_request_hash(normalize_approval_request_payload("pos.refund.create", raw)))

    def test_quote_does_not_accept_free_refund_amount(self) -> None:
        data = RefundQuoteCreateRequest.model_validate({
            "order_id": str(uuid.uuid4()), "shift_id": str(uuid.uuid4()),
            "items": [], "reason_code": "quality_issue", "stock_disposition": "none",
            "currency": "THB", "idempotency_key": "refund-quote-001", "amount": "999999.00",
        })
        self.assertFalse(hasattr(data, "amount"))

    def test_live_provider_and_production_sandbox_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Live refund"):
            validate_refund_runtime_config(
                environment="development", provider_mode="live", webhook_secret="long-enough-secret", non_fiscal_credit_note_enabled=False,
            )
        with self.assertRaisesRegex(ValueError, "forbidden"):
            validate_refund_runtime_config(
                environment="production", provider_mode="sandbox", webhook_secret="long-enough-secret", non_fiscal_credit_note_enabled=False,
            )
        with self.assertRaisesRegex(ValueError, "non-fiscal"):
            validate_refund_runtime_config(
                environment="production", provider_mode="disabled", webhook_secret=None, non_fiscal_credit_note_enabled=True,
            )


if __name__ == "__main__":
    unittest.main()
