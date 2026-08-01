from __future__ import annotations

from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import AsyncMock

from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.platform import (
    PlatformCompanyCreate,
    PlatformLifecycleAction,
    PlatformTenantControlsUpdate,
    PlatformTenantExportRequest,
)
from app.services.platform_service import PlatformTenantService
from app.services.tenant_export_service import (
    REDACTED,
    is_sensitive_export_column,
    sanitize_export_value,
)
from app.services.tenant_control_policy import TenantControlPolicy
from app.utils.security import (
    create_access_token,
    create_device_access_token,
    create_platform_access_token,
    decode_token,
)


class PlatformTenantSchemaTests(unittest.TestCase):
    def test_company_onboarding_normalizes_owner_and_manual_controls(self) -> None:
        payload = PlatformCompanyCreate(
            name=" ร้านทดสอบ ",
            owner={
                "username": " Owner.One ",
                "password": "a-secure-password",
                "display_name": " เจ้าของร้าน ",
            },
            plan_code=" Starter ",
            feature_flags={"Restaurant": True},
            plan_limits={"Branches": 2},
            reason=" เปิดร้านใหม่ ",
        )
        self.assertEqual(payload.name, "ร้านทดสอบ")
        self.assertEqual(payload.owner.username, "owner.one")
        self.assertEqual(payload.owner.display_name, "เจ้าของร้าน")
        self.assertEqual(payload.plan_code, "starter")
        self.assertEqual(payload.feature_flags, {"restaurant": True})
        self.assertEqual(payload.plan_limits, {"branches": 2})
        self.assertEqual(payload.reason, "เปิดร้านใหม่")

    def test_lifecycle_and_controls_require_auditable_reason(self) -> None:
        with self.assertRaises(ValidationError):
            PlatformLifecycleAction(reason="   ")
        with self.assertRaises(ValidationError):
            PlatformTenantControlsUpdate(
                plan_code="starter",
                plan_limits={"users": -1},
                reason="test",
            )
        with self.assertRaises(ValidationError):
            PlatformTenantExportRequest(reason="   ")


class TenantExportSecurityTests(unittest.TestCase):
    def test_credential_columns_are_redacted(self) -> None:
        for column_name in (
            "hashed_password",
            "initial_password_hash",
            "token_hash",
            "refresh_credential_hash",
            "pairing_pin_hash",
            "omise_secret_key",
            "smtp_password",
            "line_notify_token",
            "scb_api_key",
            "secret",
        ):
            self.assertTrue(is_sensitive_export_column(column_name), column_name)
        self.assertFalse(is_sensitive_export_column("credential_version"))
        self.assertFalse(is_sensitive_export_column("password_changed_at"))
        self.assertEqual(REDACTED, "[REDACTED]")

    def test_nested_json_credentials_are_redacted(self) -> None:
        sanitized, redactions = sanitize_export_value(
            {
                "event": "payment.completed",
                "authorization": "Bearer nested-secret",
                "gateway": {"accessToken": "secret", "reference": "PAY-01"},
            }
        )
        self.assertEqual(redactions, 2)
        self.assertEqual(sanitized["authorization"], REDACTED)
        self.assertEqual(sanitized["gateway"]["accessToken"], REDACTED)
        self.assertEqual(sanitized["gateway"]["reference"], "PAY-01")


class PlatformCredentialTests(unittest.TestCase):
    def test_platform_identity_token_cannot_be_confused_with_tenant_token(self) -> None:
        operator_id = uuid.uuid4()
        token = create_platform_access_token(
            operator_id=operator_id,
            credential_version=3,
            is_superuser=True,
        )
        claims = decode_token(token)
        self.assertEqual(claims["type"], "platform_access")
        self.assertEqual(claims["sub"], str(operator_id))
        self.assertEqual(claims["credential_version"], 3)
        self.assertNotIn("company_id", claims)

    def test_tenant_and_device_tokens_bind_company_generation(self) -> None:
        company_id = uuid.uuid4()
        access = create_access_token(
            subject=str(uuid.uuid4()),
            company_id=str(company_id),
            branch_id=None,
            permissions=["*"],
            company_credential_version=4,
        )
        device = create_device_access_token(
            device_id=uuid.uuid4(),
            company_id=company_id,
            brand_id=uuid.uuid4(),
            branch_id=uuid.uuid4(),
            device_type="counter",
            station_key=None,
            credential_version=2,
            company_credential_version=4,
        )
        self.assertEqual(decode_token(access)["company_credential_version"], 4)
        self.assertEqual(decode_token(device)["company_credential_version"], 4)


class TenantControlPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_feature_is_denied(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = SimpleNamespace(feature_flags={"restaurant": False})
        with self.assertRaises(HTTPException) as raised:
            await TenantControlPolicy(db).require_feature(uuid.uuid4(), "restaurant")
        self.assertEqual(raised.exception.status_code, 403)

    async def test_capacity_limit_is_denied_at_limit(self) -> None:
        db = AsyncMock()
        db.scalar.side_effect = [
            SimpleNamespace(feature_flags={}, plan_limits={"users": 1}),
            1,
        ]
        with self.assertRaises(HTTPException) as raised:
            await TenantControlPolicy(db).require_capacity(uuid.uuid4(), "users")
        self.assertEqual(raised.exception.status_code, 409)

    async def test_existing_company_without_profile_remains_compatible(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = None
        await TenantControlPolicy(db).require_feature(uuid.uuid4(), "restaurant")
        await TenantControlPolicy(db).require_capacity(uuid.uuid4(), "users")

    async def test_zero_limit_is_unlimited(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = SimpleNamespace(feature_flags={}, plan_limits={"users": 0})
        await TenantControlPolicy(db).require_capacity(uuid.uuid4(), "users")
        self.assertEqual(db.scalar.await_count, 1)


class PlatformControlsCompatibilityTests(unittest.TestCase):
    def test_existing_company_without_profile_receives_non_destructive_defaults(self) -> None:
        controls = PlatformTenantService._controls(None)
        self.assertTrue(controls.feature_flags["restaurant"])
        self.assertEqual(controls.plan_limits["branches"], 0)


if __name__ == "__main__":
    unittest.main()
