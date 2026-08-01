from __future__ import annotations

from datetime import datetime, timezone
import unittest
import uuid

from fastapi import HTTPException

from app.dependencies import DeviceTokenData, TokenData
from app.routers.pos import _require_matching_counter_device


class CounterShiftSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.company_id = uuid.uuid4()
        self.branch_id = uuid.uuid4()
        self.current = TokenData(
            user_id=uuid.uuid4(),
            company_id=self.company_id,
            branch_id=self.branch_id,
            permissions=["pos.cashier.open_shift", "pos.cashier.close_shift"],
        )

    def device(self, *, company_id: uuid.UUID | None = None, branch_id: uuid.UUID | None = None) -> DeviceTokenData:
        now = datetime.now(timezone.utc)
        return DeviceTokenData(
            device_id=uuid.uuid4(),
            company_id=company_id or self.company_id,
            brand_id=uuid.uuid4(),
            branch_id=branch_id or self.branch_id,
            device_code="C-TESTSHIFT",
            name="Counter Test",
            device_type="counter",
            station_key=None,
            business_type="restaurant",
            target_database="restaurant",
            credential_version=1,
            paired_at=now,
            last_seen_at=now,
        )

    def test_matching_counter_device_is_allowed(self) -> None:
        _require_matching_counter_device(self.current, self.device())

    def test_generic_pos_without_device_is_allowed(self) -> None:
        _require_matching_counter_device(self.current, None)

    def test_cross_branch_counter_device_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            _require_matching_counter_device(self.current, self.device(branch_id=uuid.uuid4()))

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(
            raised.exception.detail,
            "Counter device Branch does not match staff Branch",
        )


if __name__ == "__main__":
    unittest.main()
