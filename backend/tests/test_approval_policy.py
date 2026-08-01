from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import unittest
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException
from pydantic import ValidationError

from app.dependencies import TokenData
from app.schemas.approval import ManagerPinSetRequest
from app.schemas.pos import CartItem, CreateSaleRequest
from app.services.approval_service import (
    ApprovalService,
    approval_request_hash,
    normalize_approval_request_payload,
)
from app.services.sale_service import sale_discount_percentage
from app.utils.security import create_approval_token


class ApprovalPolicyTests(unittest.TestCase):
    def test_manager_pin_rejects_trivial_or_non_six_digit_values(self) -> None:
        for pin in ("123456", "654321", "111111", "12345", "12345a"):
            with self.subTest(pin=pin), self.assertRaises(ValidationError):
                ManagerPinSetRequest(current_password="Password123!", pin=pin)

        request = ManagerPinSetRequest(
            current_password="Password123!",
            pin="482915",
        )
        self.assertEqual(request.pin, "482915")

    def test_request_hash_is_stable_but_payload_sensitive(self) -> None:
        first = approval_request_hash({"order_id": "one", "nested": {"qty": 2}})
        reordered = approval_request_hash({"nested": {"qty": 2}, "order_id": "one"})
        changed = approval_request_hash({"order_id": "one", "nested": {"qty": 3}})

        self.assertEqual(first, reordered)
        self.assertNotEqual(first, changed)

    def test_discount_percentage_combines_line_and_order_discounts(self) -> None:
        request = CreateSaleRequest(
            shift_id="00000000-0000-0000-0000-000000000001",
            location_id="00000000-0000-0000-0000-000000000002",
            items=[
                CartItem(
                    product_id="00000000-0000-0000-0000-000000000003",
                    qty=Decimal("2"),
                    unit_price=Decimal("90"),
                    original_price=Decimal("100"),
                    discount_amount=Decimal("10"),
                    discount_type="percent",
                    vat_type="none",
                )
            ],
            discount_amount=Decimal("10"),
            discount_type="amount",
            payment_method="cash",
            paid_amount=Decimal("200"),
        )

        self.assertEqual(sale_discount_percentage(request), Decimal("15.00"))

    def test_approval_payload_normalizes_json_numbers_like_operation_schema(self) -> None:
        raw = {
            "location_id": "00000000-0000-0000-0000-000000000002",
            "product_id": "00000000-0000-0000-0000-000000000003",
            "qty": 2,
            "note": "count correction",
        }
        normalized = normalize_approval_request_payload(
            "inventory.stock.adjust",
            raw,
        )

        self.assertEqual(normalized["qty"], "2")
        self.assertEqual(normalized["note"], "count correction")

    def test_restaurant_checkout_uses_a_stable_discount_fingerprint(self) -> None:
        session_id = "00000000-0000-0000-0000-000000000001"
        raw = {
            "session_id": session_id,
            "payment_method": "cash",
            "paid_amount": 80,
            "discount_amount": 20,
        }
        normalized = normalize_approval_request_payload(
            "pos.discount.override",
            raw,
        )

        self.assertEqual(normalized["session_id"], session_id)
        self.assertEqual(normalized["paid_amount"], "80")
        self.assertEqual(normalized["discount_amount"], "20")


class ApprovalBindingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.company_id = uuid.uuid4()
        self.branch_id = uuid.uuid4()
        self.requester_id = uuid.uuid4()
        self.approver_id = uuid.uuid4()
        self.stock_payload = {
            "location_id": str(uuid.uuid4()),
            "product_id": str(uuid.uuid4()),
            "qty": 2,
            "note": "count correction",
        }
        normalized = normalize_approval_request_payload(
            "inventory.stock.adjust",
            self.stock_payload,
        )
        self.token = create_approval_token(
            grant_id=uuid.uuid4(),
            company_id=self.company_id,
            branch_id=self.branch_id,
            requester_id=self.requester_id,
            approver_id=self.approver_id,
            action="inventory.stock.adjust",
            reason="approve count correction",
            request_hash=approval_request_hash(normalized),
        )

    def current(
        self,
        *,
        branch_id: uuid.UUID | None = None,
        requester_id: uuid.UUID | None = None,
    ) -> TokenData:
        return TokenData(
            user_id=requester_id or self.requester_id,
            company_id=self.company_id,
            branch_id=branch_id or self.branch_id,
            permissions=["inventory.stock.adjust.request"],
        )

    async def test_grant_rejects_cross_branch_requester_and_action(self) -> None:
        service = ApprovalService(AsyncMock())
        cases = (
            (
                self.current(branch_id=uuid.uuid4()),
                "inventory.stock.adjust",
                self.stock_payload,
            ),
            (
                self.current(requester_id=uuid.uuid4()),
                "inventory.stock.adjust",
                self.stock_payload,
            ),
            (
                self.current(),
                "pos.sale.void",
                {"order_id": str(uuid.uuid4()), "void_reason": "wrong action"},
            ),
        )
        for current, action, payload in cases:
            with self.subTest(action=action, current=current), self.assertRaises(
                HTTPException
            ) as raised:
                await service.authorize_operation(
                    current=current,
                    action=action,
                    request_payload=payload,
                    approval_token=self.token,
                    reason="must not authorize",
                )
            self.assertEqual(raised.exception.status_code, 403)
            self.assertEqual(raised.exception.detail["code"], "approval_mismatch")

    async def test_expired_grant_is_rejected(self) -> None:
        normalized = normalize_approval_request_payload(
            "inventory.stock.adjust",
            self.stock_payload,
        )
        expired = create_approval_token(
            grant_id=uuid.uuid4(),
            company_id=self.company_id,
            branch_id=self.branch_id,
            requester_id=self.requester_id,
            approver_id=self.approver_id,
            action="inventory.stock.adjust",
            reason="expired approval",
            request_hash=approval_request_hash(normalized),
            expires_delta=timedelta(seconds=-1),
        )
        with self.assertRaises(HTTPException) as raised:
            await ApprovalService(AsyncMock()).authorize_operation(
                current=self.current(),
                action="inventory.stock.adjust",
                request_payload=self.stock_payload,
                approval_token=expired,
                reason="must not authorize",
            )
        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
