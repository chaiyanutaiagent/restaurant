from __future__ import annotations

from decimal import Decimal
import unittest
import uuid

from pydantic import ValidationError

from app.models.restaurant import DiningOrderItem
from app.schemas.restaurant import RestaurantCancellationRequest
from app.services.approval_service import (
    DIRECT_PERMISSION_BY_ACTION,
    REQUEST_PERMISSION_BY_ACTION,
    approval_request_hash,
    normalize_approval_request_payload,
)
from app.services.restaurant_cancellation_service import (
    CANCELLATION_POLICY_VERSION,
    RestaurantCancellationService,
)
from app.services.role_preset_service import ROLE_PRESET_POLICIES


def cancellation_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "target_type": "item",
        "target_id": str(uuid.uuid4()),
        "expected_order_version": 2,
        "expected_item_version": 3,
        "reason_code": "wrong_item",
        "reason_note": "ลูกค้าสั่งผิด",
        "idempotency_key": "wp45-cancel-0001",
    }
    payload.update(overrides)
    return payload


def order_item(status: str, line_total: str) -> DiningOrderItem:
    return DiningOrderItem(
        id=uuid.uuid4(),
        order_id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        product_name="เมนูทดสอบ",
        qty=1,
        unit_price=Decimal(line_total),
        original_price=Decimal(line_total),
        vat_type="included",
        vat_rate=Decimal("7"),
        vat_amount=Decimal("0"),
        line_total=Decimal(line_total),
        status=status,
        row_version=1,
    )


class WP45CancellationContractTests(unittest.TestCase):
    def test_policy_version_is_explicit(self) -> None:
        self.assertEqual(CANCELLATION_POLICY_VERSION, "restaurant-cancellation-v1")

    def test_other_reason_requires_note(self) -> None:
        with self.assertRaises(ValidationError):
            RestaurantCancellationRequest.model_validate(
                cancellation_payload(reason_code="other", reason_note="")
            )

    def test_item_cancellation_requires_item_version(self) -> None:
        with self.assertRaises(ValidationError):
            RestaurantCancellationRequest.model_validate(
                cancellation_payload(expected_item_version=None)
            )

    def test_order_cancellation_does_not_require_item_version(self) -> None:
        payload = RestaurantCancellationRequest.model_validate(
            cancellation_payload(
                target_type="order",
                expected_item_version=None,
            )
        )
        self.assertEqual(payload.target_type, "order")

    def test_stage_uses_highest_kitchen_impact(self) -> None:
        items = [order_item("pending", "20"), order_item("done", "30"), order_item("cooking", "10")]
        self.assertEqual(RestaurantCancellationService._stage(items), "done")

    def test_bill_impact_explicitly_excludes_refund_and_tax(self) -> None:
        impact = RestaurantCancellationService._bill_impact(
            [order_item("pending", "19.90"), order_item("cooking", "30.10")]
        )
        self.assertEqual(impact["amount_removed"], "50.00")
        self.assertFalse(impact["sale_return_created"])
        self.assertFalse(impact["payment_refund_created"])
        self.assertFalse(impact["tax_document_created"])

    def test_approval_payload_is_canonical_and_does_not_include_token(self) -> None:
        request = RestaurantCancellationRequest.model_validate(
            cancellation_payload(approval_token="one-time-secret")
        )
        normalized = normalize_approval_request_payload(
            "fb.order.cancel_after_kitchen",
            request.approval_payload(),
        )
        self.assertNotIn("approval_token", normalized)
        self.assertEqual(normalized["reason_code"], "wrong_item")
        self.assertEqual(
            approval_request_hash(normalized),
            approval_request_hash(normalize_approval_request_payload("fb.order.cancel_after_kitchen", normalized)),
        )

    def test_approval_actions_use_separate_request_and_approve_permissions(self) -> None:
        self.assertEqual(
            DIRECT_PERMISSION_BY_ACTION["fb.order.cancel_after_kitchen"],
            "fb.order.cancel.approve",
        )
        self.assertEqual(
            REQUEST_PERMISSION_BY_ACTION["fb.order.cancel_after_kitchen"],
            "fb.order.cancel.request",
        )
        self.assertEqual(
            DIRECT_PERMISSION_BY_ACTION["fb.order.cancel.reopen"],
            "fb.order.cancel.reopen",
        )
        self.assertEqual(
            REQUEST_PERMISSION_BY_ACTION["fb.order.cancel.reopen"],
            "fb.order.cancel.reopen.request",
        )

    def test_service_staff_cannot_approve_own_cancellation(self) -> None:
        service_staff = next(policy for policy in ROLE_PRESET_POLICIES if policy.key == "service-staff")
        self.assertIn("fb.order.cancel", service_staff.permission_codes)
        self.assertIn("fb.order.cancel.request", service_staff.permission_codes)
        self.assertNotIn("fb.order.cancel.approve", service_staff.permission_codes)

    def test_branch_manager_has_full_cancellation_governance(self) -> None:
        branch_manager = next(policy for policy in ROLE_PRESET_POLICIES if policy.key == "branch-manager")
        for permission in (
            "fb.order.cancel",
            "fb.order.cancel.request",
            "fb.order.cancel.approve",
            "fb.order.cancel.reopen.request",
            "fb.order.cancel.reopen",
        ):
            self.assertIn(permission, branch_manager.permission_codes)


if __name__ == "__main__":
    unittest.main()
