from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock
import uuid

from pydantic import ValidationError

from app.schemas.restaurant import PlaceOrderRequest, TableRead
from app.models.branch import Branch
from app.services.dining_service import DiningService


def _item(
    *,
    name: str,
    qty: int,
    unit_price: str,
    status: str = "pending",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        product_name=name,
        qty=qty,
        unit_price=Decimal(unit_price),
        special_request=None,
        status=status,
    )


class DiningSessionQrSchemaTests(unittest.TestCase):
    def test_table_contract_exposes_only_active_session_qr(self) -> None:
        self.assertNotIn("qr_token", TableRead.model_fields)
        self.assertIn("session_qr_token", TableRead.model_fields)

    def test_public_order_requires_at_least_one_item(self) -> None:
        with self.assertRaises(ValidationError):
            PlaceOrderRequest(items=[])

    def test_public_order_rejects_non_positive_quantity(self) -> None:
        with self.assertRaises(ValidationError):
            PlaceOrderRequest(items=[{"product_id": uuid.uuid4(), "qty": 0}])


class DiningSessionQrHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_token_lookup_accepts_only_active_sessions_with_qr_enabled(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = None
        service = DiningService(db)

        await service.get_session_by_token(uuid.uuid4())

        statement = db.scalar.await_args.args[0]
        compiled = statement.compile()
        sql = str(compiled)
        self.assertIn("dining_sessions.status IN", sql)
        self.assertIn("branch_settings.fb_table_qr_enabled IS true", sql)
        self.assertIn(["open", "bill_requested"], compiled.params.values())

    async def test_public_menu_accepts_counter_opened_takeaway_session(self) -> None:
        branch_id = uuid.uuid4()
        company_id = uuid.uuid4()
        session = SimpleNamespace(
            id=uuid.uuid4(),
            branch_id=branch_id,
            company_id=company_id,
            table_id=None,
            queue_number=18,
            status="open",
            opened_at=datetime(2026, 7, 31, 10, 0, tzinfo=timezone.utc),
        )
        branch = SimpleNamespace(id=branch_id, name="สาขากรุงเทพ")
        settings = SimpleNamespace(
            fb_table_qr_enabled=True,
            fb_service_mode="both",
            fb_bill_at_table=True,
        )
        empty_products = MagicMock()
        empty_products.all.return_value = []
        empty_categories = MagicMock()
        empty_categories.all.return_value = []
        db = AsyncMock()
        db.get.return_value = branch
        db.scalar.return_value = settings
        db.scalars.side_effect = [empty_products, empty_categories]
        service = DiningService(db)
        service.get_session_by_token = AsyncMock(return_value=session)

        result = await service.get_public_menu(uuid.uuid4())

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.source_type, "quick_service")
        self.assertIsNone(result.table_name)
        self.assertEqual(result.queue_number, 18)
        self.assertFalse(result.bill_at_table_enabled)
        db.get.assert_awaited_once_with(Branch, branch_id)

    async def test_history_is_grouped_and_cancelled_items_are_not_totalled(self) -> None:
        first_item = _item(name="ข้าวผัด", qty=2, unit_price="60")
        cancelled_item = _item(
            name="น้ำเปล่า",
            qty=1,
            unit_price="15",
            status="cancelled",
        )
        second_item = _item(name="ไอศกรีม", qty=1, unit_price="45", status="done")
        first_order = SimpleNamespace(
            id=uuid.uuid4(),
            order_number="DO-001",
            status="pending",
            note=None,
            created_at=datetime(2026, 7, 30, 10, 0, tzinfo=timezone.utc),
            items=[first_item, cancelled_item],
        )
        second_order = SimpleNamespace(
            id=uuid.uuid4(),
            order_number="DO-002",
            status="pending",
            note="เสิร์ฟทีหลัง",
            created_at=datetime(2026, 7, 30, 10, 15, tzinfo=timezone.utc),
            items=[second_item],
        )
        session = SimpleNamespace(
            id=uuid.uuid4(),
            queue_number=12,
            status="open",
            orders=[second_order, first_order],
        )
        service = DiningService(AsyncMock())
        service.get_session = AsyncMock(return_value=session)

        result = await service.get_public_order_status(session.id)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual([row.order_number for row in result.orders], ["DO-001", "DO-002"])
        self.assertEqual(result.total_item_count, 3)
        self.assertEqual(result.total_amount, Decimal("165"))
        self.assertEqual(result.orders[0].subtotal, Decimal("120"))
        self.assertEqual(len(result.items), 3)


if __name__ == "__main__":
    unittest.main()
