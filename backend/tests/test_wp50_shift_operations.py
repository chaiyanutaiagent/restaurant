from __future__ import annotations

from decimal import Decimal
import unittest
import uuid

from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.pos import CashMovementCreateRequest, CloseShiftRequest, OpenShiftRequest
from app.services.approval_service import normalize_approval_request_payload


class WP50ShiftSchemaTests(unittest.TestCase):
    def test_open_shift_rejects_negative_opening_cash(self) -> None:
        with self.assertRaises(ValidationError):
            OpenShiftRequest(location_id=uuid.uuid4(), opening_cash=Decimal("-0.01"))

    def test_denomination_total_must_match_counted_cash(self) -> None:
        valid = CloseShiftRequest(
            closing_cash=Decimal("1520"),
            cash_count=[
                {"denomination": "1000", "quantity": 1},
                {"denomination": "500", "quantity": 1},
                {"denomination": "20", "quantity": 1},
            ],
        )
        self.assertEqual(valid.closing_cash, Decimal("1520"))

        with self.assertRaises(ValidationError):
            CloseShiftRequest(
                closing_cash=Decimal("1500"),
                cash_count=[{"denomination": "1000", "quantity": 1}],
            )

    def test_cash_movement_requires_positive_amount_reason_and_version(self) -> None:
        with self.assertRaises(ValidationError):
            CashMovementCreateRequest(
                movement_type="cash_out",
                amount=0,
                reason_code="cash_drop",
                reason="x",
                expected_shift_version=0,
                idempotency_key="short",
            )

    def test_close_contract_carries_optimistic_version_and_idempotency(self) -> None:
        payload = CloseShiftRequest(
            closing_cash=Decimal("500"),
            expected_version=7,
            idempotency_key="wp50-close-idempotency",
        )
        self.assertEqual(payload.expected_version, 7)
        self.assertEqual(payload.idempotency_key, "wp50-close-idempotency")


class WP50ApprovalPayloadTests(unittest.TestCase):
    def test_cash_movement_approval_normalization_binds_shift(self) -> None:
        shift_id = uuid.uuid4()
        normalized = normalize_approval_request_payload(
            "pos.cash_movement.approve",
            {
                "shift_id": str(shift_id),
                "movement_type": "cash_in",
                "amount": "1000",
                "reason_code": "change_fund",
                "reason": "เติมเงินทอนรอบเย็น",
                "expected_shift_version": 2,
                "idempotency_key": "wp50-cash-movement",
            },
        )
        self.assertEqual(normalized["shift_id"], str(shift_id))
        self.assertEqual(normalized["expected_shift_version"], 2)
        self.assertNotIn("approval_token", normalized)

    def test_variance_approval_normalization_binds_exact_count(self) -> None:
        shift_id = uuid.uuid4()
        normalized = normalize_approval_request_payload(
            "pos.shift.variance.approve",
            {
                "shift_id": str(shift_id),
                "closing_cash": "950",
                "reason_code": "count_short",
                "note": "เงินขาดจากการทอน",
                "cash_count": [{"denomination": "500", "quantity": 1}, {"denomination": "100", "quantity": 4}, {"denomination": "50", "quantity": 1}],
                "expected_version": 8,
                "idempotency_key": "wp50-close-variance",
            },
        )
        self.assertEqual(normalized["shift_id"], str(shift_id))
        self.assertEqual(normalized["closing_cash"], "950")
        self.assertEqual(normalized["expected_version"], 8)

    def test_shift_approval_requires_shift_id(self) -> None:
        with self.assertRaises(HTTPException):
            normalize_approval_request_payload(
                "pos.shift.variance.approve",
                {"closing_cash": "0", "idempotency_key": "wp50-no-shift"},
            )


if __name__ == "__main__":
    unittest.main()
