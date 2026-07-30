from __future__ import annotations

from decimal import Decimal
import unittest
from unittest.mock import AsyncMock
import uuid

from pydantic import ValidationError

from app.schemas.restaurant import (
    WapOfflinePaidOrderRequest,
    WapOfflineSyncRequest,
    WapOrderRead,
)
from app.services.dining_service import DiningService


def _offline_order(client_order_id: str = "android-installation:order-001") -> WapOfflinePaidOrderRequest:
    return WapOfflinePaidOrderRequest(
        client_order_id=client_order_id,
        items=[{"product_id": uuid.uuid4(), "qty": 1}],
        payment_method="cash",
        paid_amount=Decimal("35"),
    )


def _wap_order(client_order_id: str = "android-installation:order-001") -> WapOrderRead:
    return WapOrderRead(
        session_id=uuid.uuid4(),
        order_id=uuid.uuid4(),
        sale_order_id=uuid.uuid4(),
        sale_order_number="SO20260722-0001",
        queue_number=1,
        queue_display="A001",
        status="closed",
        subtotal=Decimal("35"),
        total_amount=Decimal("35"),
        paid_amount=Decimal("35"),
        change_amount=Decimal("0"),
        payment_method="cash",
        client_order_id=client_order_id,
    )


class WapOfflineSchemaTests(unittest.TestCase):
    def test_sync_requires_client_order_id(self) -> None:
        with self.assertRaises(ValidationError):
            WapOfflineSyncRequest(orders=[{
                "items": [{"product_id": uuid.uuid4(), "qty": 1}],
                "payment_method": "cash",
                "paid_amount": "35",
            }])

    def test_sync_batch_is_limited_to_fifty_orders(self) -> None:
        with self.assertRaises(ValidationError):
            WapOfflineSyncRequest(
                orders=[_offline_order(f"device:order-{index}") for index in range(51)]
            )


class WapOfflineIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_order_is_returned_before_new_session_is_opened(self) -> None:
        service = DiningService(AsyncMock())
        existing = _wap_order()
        service.get_wap_order_by_client_order_id = AsyncMock(return_value=existing)
        service.open_session = AsyncMock()

        result = await service.create_wap_paid_order(
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            _offline_order(),
        )

        self.assertIs(result, existing)
        service.open_session.assert_not_awaited()

    async def test_client_order_lookup_resolves_linked_wap_session(self) -> None:
        db = AsyncMock()
        sale_order_id = uuid.uuid4()
        session_id = uuid.uuid4()
        db.scalar.side_effect = [sale_order_id, session_id]
        service = DiningService(db)
        existing = _wap_order()
        service.get_wap_order = AsyncMock(return_value=existing)

        result = await service.get_wap_order_by_client_order_id(
            uuid.uuid4(),
            uuid.uuid4(),
            existing.client_order_id,
        )

        self.assertIs(result, existing)
        service.get_wap_order.assert_awaited_once()

    async def test_stale_offline_shift_is_not_silently_reassigned(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = None
        service = DiningService(db)

        with self.assertRaisesRegex(ValueError, "กะที่บันทึกไว้"):
            await service._resolve_shift_and_location(
                uuid.uuid4(),
                uuid.uuid4(),
                uuid.uuid4(),
                uuid.uuid4(),
                None,
                strict_shift=True,
            )


if __name__ == "__main__":
    unittest.main()
