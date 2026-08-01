from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
import uuid

from fastapi import HTTPException
from pydantic import ValidationError

from app.dependencies import TokenData
from app.schemas.device import DeviceActionReason, DeviceCreate, DevicePairRequest
from app.services.device_service import DeviceService
from app.utils.security import create_device_access_token, decode_token


class DevicePairingSchemaTests(unittest.TestCase):
    def test_device_type_controls_station_shape(self) -> None:
        branch_id = uuid.uuid4()
        kitchen = DeviceCreate(
            name=" Main kitchen tablet ",
            device_type="kitchen",
            branch_id=branch_id,
            station_key=" ครัวหลัก ",
            reason=" install tablet ",
        )
        self.assertEqual(kitchen.name, "Main kitchen tablet")
        self.assertEqual(kitchen.station_key, "ครัวหลัก")
        self.assertEqual(kitchen.reason, "install tablet")

        invalid_payloads = (
            {"device_type": "kitchen"},
            {"device_type": "counter", "station_key": "Counter 1"},
            {"device_type": "pickup", "station_key": "Display"},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                DeviceCreate(
                    name="Device",
                    branch_id=branch_id,
                    reason="test",
                    **payload,
                )

    def test_pairing_pin_is_exactly_six_ascii_digits(self) -> None:
        request = DevicePairRequest(
            company_id=uuid.uuid4(),
            device_code=" k-abcd234567 ",
            pairing_pin=" 048291 ",
        )
        self.assertEqual(request.device_code, "K-ABCD234567")
        self.assertEqual(request.pairing_pin, "048291")

        for pin in ("12345", "1234567", "12345a", "１２３４５６"):
            with self.subTest(pin=pin), self.assertRaises(ValidationError):
                DevicePairRequest(
                    company_id=uuid.uuid4(),
                    device_code="K-ABCD234567",
                    pairing_pin=pin,
                )

    def test_device_action_reason_cannot_be_blank(self) -> None:
        with self.assertRaises(ValidationError):
            DeviceActionReason(reason="   ")


class DeviceCredentialPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.company_id = uuid.uuid4()
        self.brand_id = uuid.uuid4()
        self.branch_id = uuid.uuid4()
        self.device_id = uuid.uuid4()

    def test_device_token_is_server_context_bound(self) -> None:
        token = create_device_access_token(
            device_id=self.device_id,
            company_id=self.company_id,
            brand_id=self.brand_id,
            branch_id=self.branch_id,
            device_type="kitchen",
            station_key="ครัวหลัก",
            credential_version=3,
            expires_delta=timedelta(minutes=5),
        )
        payload = decode_token(token)
        self.assertEqual(payload["type"], "device_access")
        self.assertEqual(payload["sub"], str(self.device_id))
        self.assertEqual(payload["company_id"], str(self.company_id))
        self.assertEqual(payload["brand_id"], str(self.brand_id))
        self.assertEqual(payload["branch_id"], str(self.branch_id))
        self.assertEqual(payload["device_type"], "kitchen")
        self.assertEqual(payload["station_key"], "ครัวหลัก")
        self.assertEqual(payload["credential_version"], 3)
        self.assertEqual(payload["business_type"], "restaurant")
        self.assertEqual(payload["target_database"], "restaurant")
        self.assertNotIn("permissions", payload)

    def test_non_company_manager_is_limited_to_current_branch(self) -> None:
        current = TokenData(
            user_id=uuid.uuid4(),
            company_id=self.company_id,
            branch_id=self.branch_id,
            permissions=["system.device.manage"],
            scope_types=["branch"],
        )
        DeviceService._require_branch_access(current, self.branch_id)
        with self.assertRaises(HTTPException) as raised:
            DeviceService._require_branch_access(current, uuid.uuid4())
        self.assertEqual(raised.exception.status_code, 404)

    def test_device_status_distinguishes_pairing_pair_and_revoke(self) -> None:
        now = datetime.now(timezone.utc)
        device = SimpleNamespace(
            revoked_at=None,
            paired_at=None,
            pairing_pin_hash="hash",
            pairing_expires_at=now + timedelta(minutes=5),
        )
        self.assertEqual(DeviceService._status(device), "pending_pairing")
        device.pairing_expires_at = now - timedelta(seconds=1)
        self.assertEqual(DeviceService._status(device), "pairing_expired")
        device.pairing_pin_hash = None
        device.paired_at = now
        self.assertEqual(DeviceService._status(device), "paired")
        device.revoked_at = now
        self.assertEqual(DeviceService._status(device), "revoked")


if __name__ == "__main__":
    unittest.main()
