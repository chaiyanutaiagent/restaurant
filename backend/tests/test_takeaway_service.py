from __future__ import annotations

from decimal import Decimal
import inspect
import unittest
import uuid

from fastapi import HTTPException
from fastapi.params import Depends
from pydantic import ValidationError

from app.dependencies import TokenData
from app.models.takeaway import (
    TakeawayCentralOrder,
    TakeawayOrder,
    TakeawayReceipt,
    TakeawayStockBalance,
)
from app.routers import takeaway
from app.schemas.takeaway import (
    TakeawayPaymentCreate,
    TakeawayProductionBatchCreate,
    TakeawayProductionLineCreate,
    TakeawayReceiptPrintCreate,
    TakeawaySaleCreate,
    TakeawaySaleLine,
    TakeawayStoreCentralOrderCreate,
)
from app.services.takeaway_service import assert_takeaway_scope, money


def token(*, business_type: str = "takeaway", permissions: list[str] | None = None) -> TokenData:
    return TokenData(
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        branch_id=uuid.uuid4(),
        business_type=business_type,
        target_database=business_type,
        permissions=["*"] if permissions is None else permissions,
    )


class TakeawayServicePolicyTests(unittest.TestCase):
    def test_money_uses_two_decimal_half_up_rounding(self) -> None:
        self.assertEqual(money(Decimal("10.125")), Decimal("10.13"))

    def test_cross_business_and_cross_branch_access_fail_closed(self) -> None:
        restaurant = token(business_type="restaurant")
        with self.assertRaises(HTTPException) as wrong_business:
            assert_takeaway_scope(restaurant)
        self.assertEqual(wrong_business.exception.status_code, 404)

        current = token()
        with self.assertRaises(HTTPException) as wrong_branch:
            assert_takeaway_scope(current, branch_id=uuid.uuid4())
        self.assertEqual(wrong_branch.exception.status_code, 404)

    def test_shared_stock_identity_excludes_brand(self) -> None:
        unique_columns = {
            tuple(column.name for column in constraint.columns)
            for constraint in TakeawayStockBalance.__table__.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        self.assertIn(("company_id", "location_id", "item_id", "lot_code"), unique_columns)
        self.assertTrue(all("brand_id" not in columns for columns in unique_columns))

    def test_order_contract_is_paid_first(self) -> None:
        constraint_sql = " ".join(
            str(constraint.sqltext)
            for constraint in TakeawayOrder.__table__.constraints
            if hasattr(constraint, "sqltext")
        )
        self.assertIn("awaiting_payment", constraint_sql)
        self.assertIn("queued", constraint_sql)
        self.assertIn("paid", constraint_sql)

    def test_production_requires_input_and_output(self) -> None:
        with self.assertRaises(ValidationError):
            TakeawayProductionBatchCreate(
                brand_id=uuid.uuid4(),
                location_id=uuid.uuid4(),
                lines=[
                    TakeawayProductionLineCreate(
                        item_id=uuid.uuid4(),
                        line_type="input",
                        planned_qty=Decimal("1"),
                        unit="kg",
                    )
                ],
            )

    def test_offline_device_and_sequence_are_atomic_pair(self) -> None:
        with self.assertRaises(ValidationError):
            TakeawaySaleCreate(
                brand_id=uuid.uuid4(),
                branch_id=uuid.uuid4(),
                shift_id=uuid.uuid4(),
                idempotency_key="offline-sale-1",
                items=[
                    TakeawaySaleLine(
                        catalog_item_id=uuid.uuid4(),
                        quantity=Decimal("1"),
                    )
                ],
                payment=TakeawayPaymentCreate(
                    method="cash",
                    amount=Decimal("100"),
                    idempotency_key="offline-payment-1",
                ),
                offline_device_id=uuid.uuid4(),
            )

    def test_store_order_and_receipt_print_contracts_are_idempotent(self) -> None:
        store_order = TakeawayStoreCentralOrderCreate(
            business_date="2026-09-16",
            round_no=1,
            order_type="regular",
            idempotency_key="store-order-20260916-1",
            items=[
                {
                    "catalog_item_id": uuid.uuid4(),
                    "sku": "SKU-1",
                    "item_name": "สินค้า",
                    "quantity": Decimal("2"),
                    "unit": "ชิ้น",
                }
            ],
        )
        self.assertEqual(store_order.order_type, "regular")
        receipt_print = TakeawayReceiptPrintCreate(
            copy_type="merchant",
            idempotency_key="receipt-print-001",
        )
        self.assertEqual(receipt_print.copy_type, "merchant")

        central_unique_columns = {
            tuple(column.name for column in constraint.columns)
            for constraint in TakeawayCentralOrder.__table__.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        self.assertIn(("branch_id", "idempotency_key"), central_unique_columns)
        self.assertIn("print_count", TakeawayReceipt.__table__.columns)


class TakeawayRouterPermissionTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def permission_dependency(endpoint: object):
        default = inspect.signature(endpoint).parameters["current"].default
        if not isinstance(default, Depends):
            raise AssertionError("current is not a FastAPI dependency")
        return default.dependency

    async def test_central_order_list_accepts_store_or_central_role(self) -> None:
        checker = self.permission_dependency(takeaway.list_central_orders)
        store = token(permissions=["takeaway.central_order.create"])
        central = token(permissions=["takeaway.central_order.manage"])

        self.assertIs(await checker(store), store)
        self.assertIs(await checker(central), central)

        with self.assertRaises(HTTPException) as denied:
            await checker(token(permissions=["takeaway.catalog.view"]))
        self.assertEqual(denied.exception.status_code, 403)

    async def test_central_order_creation_remains_store_permission_only(self) -> None:
        checker = self.permission_dependency(takeaway.create_central_order)
        store = token(permissions=["takeaway.central_order.create"])
        self.assertIs(await checker(store), store)

        with self.assertRaises(HTTPException) as denied:
            await checker(token(permissions=["takeaway.central_order.manage"]))
        self.assertEqual(denied.exception.status_code, 403)

    async def test_store_receive_remains_store_permission_only(self) -> None:
        checker = self.permission_dependency(takeaway.receive_store_central_order)
        store = token(permissions=["takeaway.central_order.create"])
        self.assertIs(await checker(store), store)

        with self.assertRaises(HTTPException) as denied:
            await checker(token(permissions=["takeaway.central_order.manage"]))
        self.assertEqual(denied.exception.status_code, 403)

if __name__ == "__main__":
    unittest.main()
