from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
import unittest
import uuid

from app.config import settings
from app.dependencies import DeviceTokenData, TokenData
from app.schemas.restaurant import WapOfflinePaidOrderRequest
from app.services.offline_sync_service import (
    OFFLINE_SCHEMA_VERSION,
    OfflineSyncError,
    OfflineSyncService,
    offline_request_document,
    offline_request_hash,
)


class WP47OfflineSyncRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc)
        self.company_id = uuid.uuid4()
        self.branch_id = uuid.uuid4()
        self.brand_id = uuid.uuid4()
        self.shift_id = uuid.uuid4()
        self.location_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.device_id = uuid.uuid4()
        self.product_id = uuid.uuid4()
        self.client_id = "offline-test-operation-001"
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
            device_code="C-WP47000001",
            name="WP47 Counter",
            device_type="counter",
            station_key=None,
            business_type="restaurant",
            target_database="restaurant",
            credential_version=1,
            paired_at=self.now,
            last_seen_at=self.now,
        )

    def payload(self, **updates: object) -> WapOfflinePaidOrderRequest:
        values = {
            "client_order_id": self.client_id,
            "client_operation_id": self.client_id,
            "idempotency_key": f"offline-sale:{self.device_id}:{self.client_id}",
            "schema_version": OFFLINE_SCHEMA_VERSION,
            "request_hash": "0" * 64,
            "company_id": self.company_id,
            "brand_id": self.brand_id,
            "branch_id": self.branch_id,
            "station_key": self.device.device_code,
            "shift_id": self.shift_id,
            "location_id": self.location_id,
            "operation_type": "cash_sale",
            "sequence_no": 1,
            "price_snapshot_version": "menu-snapshot-1",
            "currency": "THB",
            "local_created_at": self.now,
            "offline_policy_version": 1,
            "offline_authorization": "signed-lease",
            "items": [{
                "product_id": self.product_id,
                "qty": 2,
                "special_request": None,
                "expected_unit_price": Decimal("35.0000"),
                "expected_price_version": "menu-snapshot-1",
            }],
            "payment_method": "cash",
            "paid_amount": Decimal("70.00"),
            "payments": [{"payment_method": "cash", "amount": Decimal("70.00"), "reference_no": None}],
        }
        values.update(updates)
        payload = WapOfflinePaidOrderRequest(**values)
        return payload.model_copy(update={"request_hash": offline_request_hash(payload)})

    def enabled_patches(self):
        return (
            patch.object(settings, "pos_offline_mode_enabled", True),
            patch.object(settings, "pos_offline_company_allowlist", str(self.company_id)),
            patch.object(settings, "pos_offline_branch_allowlist", str(self.branch_id)),
        )

    def test_canonical_hash_is_stable_and_detects_payload_change(self) -> None:
        payload = self.payload()
        self.assertEqual(offline_request_hash(payload), payload.request_hash)
        changed = payload.model_copy(update={"paid_amount": Decimal("71.00")})
        self.assertNotEqual(offline_request_hash(changed), payload.request_hash)

    def test_canonical_timestamp_matches_javascript_millisecond_iso(self) -> None:
        payload = self.payload(local_created_at=datetime(2026, 9, 21, 3, 4, 5, 123456, timezone.utc))
        self.assertEqual(
            offline_request_document(payload)["created_at_device"],
            "2026-09-21T03:04:05.123Z",
        )

    def test_kill_switch_fails_closed(self) -> None:
        with patch.object(settings, "pos_offline_mode_enabled", False):
            with self.assertRaisesRegex(OfflineSyncError, "disabled"):
                OfflineSyncService.assert_runtime_scope(
                    self.current, self.device, self.payload(), brand_id=self.brand_id,
                )

    def test_offline_promptpay_is_rejected(self) -> None:
        payload = self.payload(
            payment_method="promptpay",
            payments=[{"payment_method": "promptpay", "amount": Decimal("70.00")}],
        )
        first, second, third = self.enabled_patches()
        with first, second, third:
            with self.assertRaisesRegex(OfflineSyncError, "cash"):
                OfflineSyncService.assert_runtime_scope(
                    self.current, self.device, payload, brand_id=self.brand_id,
                )

    def test_cross_tenant_payload_is_quarantined(self) -> None:
        payload = self.payload(company_id=uuid.uuid4())
        first, second, third = self.enabled_patches()
        with first, second, third:
            with self.assertRaises(OfflineSyncError) as raised:
                OfflineSyncService.assert_runtime_scope(
                    self.current, self.device, payload, brand_id=self.brand_id,
                )
        self.assertEqual(raised.exception.code, "tenant_scope_mismatch")
        self.assertEqual(raised.exception.state, "quarantined")


if __name__ == "__main__":
    unittest.main()
