from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.dependencies import TokenData
from app.schemas.device import (
    DeviceActionReason,
    DeviceContextRead,
    DeviceCreate,
    DevicePairRequest,
    DeviceRenewRequest,
    DeviceWorkspaceBootstrapRead,
    DeviceWorkspaceBranchRead,
)
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

    def test_device_refresh_credential_requires_persistent_secret_shape(self) -> None:
        device_id = uuid.uuid4()
        token = DeviceService._new_refresh_credential(device_id)
        request = DeviceRenewRequest(refresh_token=f"  {token}  ")
        self.assertEqual(request.refresh_token, token)
        self.assertEqual(DeviceService._refresh_device_id(token), device_id)
        self.assertEqual(len(DeviceService._hash_refresh_credential(token)), 64)
        self.assertIsNone(DeviceService._refresh_device_id("not-a-refresh-token"))

    def test_counter_workspace_requires_staff_identity_for_sales(self) -> None:
        now = datetime.now(timezone.utc)
        company_id = uuid.uuid4()
        branch_id = uuid.uuid4()
        workspace = DeviceWorkspaceBootstrapRead(
            workspace="counter",
            device=DeviceContextRead(
                device_id=uuid.uuid4(),
                company_id=company_id,
                brand_id=uuid.uuid4(),
                branch_id=branch_id,
                device_code="C-ABCD234567",
                name="Counter",
                device_type="counter",
                business_type="restaurant",
                target_database="restaurant",
                credential_version=1,
                paired_at=now,
                last_seen_at=now,
            ),
            branch=DeviceWorkspaceBranchRead(id=branch_id, code="BKK-01", name="Bangkok"),
            requires_staff_login=True,
            capabilities=["staff_login", "pos_handoff"],
        )
        self.assertTrue(workspace.requires_staff_login)
        self.assertEqual(workspace.branch.id, workspace.device.branch_id)
        self.assertNotIn("sale_create", workspace.capabilities)


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
        self.assertIsInstance(payload["jti"], str)
        self.assertEqual(payload["business_type"], "restaurant")
        self.assertEqual(payload["target_database"], "restaurant")
        self.assertNotIn("permissions", payload)

    def test_takeaway_device_token_is_bound_to_takeaway_database(self) -> None:
        token = create_device_access_token(
            device_id=self.device_id,
            company_id=self.company_id,
            brand_id=self.brand_id,
            branch_id=self.branch_id,
            device_type="pickup",
            station_key=None,
            credential_version=1,
            business_type="takeaway",
            target_database="takeaway",
            expires_delta=timedelta(minutes=5),
        )
        payload = decode_token(token)
        self.assertEqual(payload["business_type"], "takeaway")
        self.assertEqual(payload["target_database"], "takeaway")

    def test_retail_counter_token_is_bound_to_retail_database(self) -> None:
        token = create_device_access_token(
            device_id=self.device_id,
            company_id=self.company_id,
            brand_id=self.brand_id,
            branch_id=self.branch_id,
            device_type="counter",
            station_key=None,
            credential_version=1,
            business_type="retail_pos",
            target_database="retail_pos",
            expires_delta=timedelta(minutes=5),
        )
        payload = decode_token(token)
        self.assertEqual(payload["business_type"], "retail_pos")
        self.assertEqual(payload["target_database"], "retail_pos")

    def test_retail_rejects_non_counter_device_types(self) -> None:
        service = DeviceService(AsyncMock())
        self.assertIsNone(
            asyncio.run(
                service._canonical_station(
                    self.company_id,
                    self.branch_id,
                    "counter",
                    None,
                    "retail_pos",
                )
            )
        )
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(
                service._canonical_station(
                    self.company_id,
                    self.branch_id,
                    "kitchen",
                    "main",
                    "retail_pos",
                )
            )
        self.assertEqual(raised.exception.status_code, 400)

    def test_retail_device_context_requires_company_entitlement(self) -> None:
        context = SimpleNamespace(
            company_id=self.company_id,
            brand_id=self.brand_id,
            branch_id=self.branch_id,
            business_type="retail_pos",
            target_database="retail_pos",
        )
        service = DeviceService(AsyncMock())
        with (
            patch(
                "app.services.device_service.load_branch_business_context",
                new=AsyncMock(return_value=context),
            ),
            patch(
                "app.services.device_service.TenantControlPolicy.require_feature",
                new=AsyncMock(),
            ) as require_feature,
        ):
            resolved = asyncio.run(
                service._device_context(self.company_id, self.branch_id)
            )
        self.assertIs(resolved, context)
        require_feature.assert_awaited_once_with(self.company_id, "retail_pos")

    def test_non_company_manager_is_limited_to_current_branch(self) -> None:
        current = TokenData(
            user_id=uuid.uuid4(),
            company_id=self.company_id,
            branch_id=self.branch_id,
            permissions=["system.device.manage"],
            scope_types=["branch"],
        )
        self.assertTrue(DeviceService._has_direct_branch_access(current, self.branch_id))
        self.assertFalse(DeviceService._has_direct_branch_access(current, uuid.uuid4()))

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


class DeviceBrandScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_brand_manager_can_manage_only_branches_in_its_brand(self) -> None:
        brand_id = uuid.uuid4()
        current = TokenData(
            user_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            branch_id=uuid.uuid4(),
            brand_id=brand_id,
            permissions=["system.device.manage"],
            scope_types=["brand"],
        )
        db = AsyncMock()
        service = DeviceService(db)
        permitted_branch = uuid.uuid4()
        db.scalar.return_value = uuid.uuid4()
        await service._require_branch_access(current, permitted_branch)

        db.scalar.return_value = None
        with self.assertRaises(HTTPException) as raised:
            await service._require_branch_access(current, uuid.uuid4())
        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
