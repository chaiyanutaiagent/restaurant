from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest
from unittest.mock import AsyncMock
import uuid
from types import SimpleNamespace

from pydantic import ValidationError

from app.schemas.restaurant import (
    WapOfflinePaidOrderRequest,
    WapOfflineSyncRequest,
    WapOrderRead,
)
from app.dependencies import DeviceTokenData, TokenData
from app.services.dining_service import DiningService
from app.services.offline_sale_authorization import OfflineSaleAuthorizationService
from app.utils.security import create_offline_sale_authorization


def _offline_order(
    client_order_id: str = "android-installation:order-001",
    **updates,
) -> WapOfflinePaidOrderRequest:
    data = {
        "client_order_id": client_order_id,
        "items": [{"product_id": uuid.uuid4(), "qty": 1}],
        "payment_method": "cash",
        "paid_amount": Decimal("35"),
    }
    data.update(updates)
    return WapOfflinePaidOrderRequest(**data)


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
    async def test_kitchen_slip_requires_customer_slip_first(self) -> None:
        db = AsyncMock()
        company_id = uuid.uuid4()
        service = DiningService(db)
        service.get_session = AsyncMock(return_value=SimpleNamespace(
            company_id=company_id,
            sale_order_id=uuid.uuid4(),
            customer_slip_printed_at=None,
        ))

        with self.assertRaisesRegex(ValueError, "สลิปลูกค้า"):
            await service.mark_kitchen_slip_printed(uuid.uuid4(), company_id)

        db.scalar.assert_not_awaited()

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


class WapOfflineAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc)
        self.company_id = uuid.uuid4()
        self.branch_id = uuid.uuid4()
        self.brand_id = uuid.uuid4()
        self.shift_id = uuid.uuid4()
        self.location_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.device_id = uuid.uuid4()
        self.current = TokenData(
            user_id=self.user_id,
            company_id=self.company_id,
            branch_id=self.branch_id,
            brand_id=self.brand_id,
            permissions=["fb.order.create"],
        )
        self.device = DeviceTokenData(
            device_id=self.device_id,
            company_id=self.company_id,
            brand_id=self.brand_id,
            branch_id=self.branch_id,
            device_code="C-ABCD234567",
            name="Counter",
            device_type="counter",
            station_key=None,
            business_type="restaurant",
            target_database="restaurant",
            credential_version=3,
            paired_at=self.now - timedelta(hours=1),
            last_seen_at=self.now,
        )

    async def test_signed_lease_binds_staff_branch_shift_location_and_device(self) -> None:
        token, _ = OfflineSaleAuthorizationService.issue(
            self.current,
            shift_id=self.shift_id,
            location_id=self.location_id,
            brand_id=self.brand_id,
            device=self.device,
        )
        payload = _offline_order(
            shift_id=self.shift_id,
            location_id=self.location_id,
            local_created_at=self.now,
            offline_policy_version=1,
            offline_authorization=token,
        )
        identity_db = AsyncMock()
        identity_db.get.return_value = SimpleNamespace(
            company_id=self.company_id,
            branch_id=self.branch_id,
            device_type="counter",
            station_key=None,
            paired_at=self.now - timedelta(hours=1),
            revoked_at=None,
        )
        await OfflineSaleAuthorizationService.validate(
            identity_db,
            self.current,
            payload,
            brand_id=self.brand_id,
        )
        identity_db.get.assert_awaited_once()

        mismatched = payload.model_copy(update={"location_id": uuid.uuid4()})
        with self.assertRaisesRegex(ValueError, "กะ หรือคลัง"):
            await OfflineSaleAuthorizationService.validate(
                identity_db,
                self.current,
                mismatched,
                brand_id=self.brand_id,
            )

    async def test_current_policy_rejects_missing_lease_but_allows_legacy_queue(self) -> None:
        identity_db = AsyncMock()
        with self.assertRaisesRegex(ValueError, "สิทธิ์ขายออฟไลน์ไม่ครบ"):
            await OfflineSaleAuthorizationService.validate(
                identity_db,
                self.current,
                _offline_order(offline_policy_version=1, local_created_at=self.now),
                brand_id=self.brand_id,
            )
        await OfflineSaleAuthorizationService.validate(
            identity_db,
            self.current,
            _offline_order(),
            brand_id=self.brand_id,
        )
        identity_db.get.assert_not_awaited()

    async def test_expired_lease_rejects_new_offline_payment_time(self) -> None:
        token = create_offline_sale_authorization(
            user_id=self.user_id,
            company_id=self.company_id,
            branch_id=self.branch_id,
            shift_id=self.shift_id,
            location_id=self.location_id,
            brand_id=self.brand_id,
            device_id=None,
            device_credential_version=None,
            expires_delta=timedelta(seconds=-1),
        )
        payload = _offline_order(
            shift_id=self.shift_id,
            location_id=self.location_id,
            local_created_at=self.now,
            offline_policy_version=1,
            offline_authorization=token,
        )
        with self.assertRaisesRegex(ValueError, "นอกช่วงเวลา"):
            await OfflineSaleAuthorizationService.validate(
                AsyncMock(),
                self.current,
                payload,
                brand_id=self.brand_id,
            )


if __name__ == "__main__":
    unittest.main()
