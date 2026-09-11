from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.dependencies import get_current_platform_operator
from app.services.platform_service import PlatformAuthService
from app.utils.platform_security import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_opaque_credential,
    generate_recovery_codes,
    hash_opaque_credential,
    hash_recovery_code,
    verify_totp,
)
from app.utils.security import create_platform_access_token


def operator_fixture(*, mfa_enabled: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        username="platform.owner",
        email="owner@example.com",
        display_name="Platform Owner",
        hashed_password="hashed",
        is_active=True,
        is_superuser=True,
        credential_version=2,
        failed_login_attempts=0,
        locked_until=None,
        last_login_at=None,
        password_changed_at=None,
        mfa_enabled=mfa_enabled,
        mfa_enabled_at=datetime.now(timezone.utc) if mfa_enabled else None,
        mfa_last_verified_step=None,
        mfa_secret_ciphertext=None,
        mfa_recovery_code_hashes=[],
    )


class PlatformSecurityPrimitiveTests(unittest.TestCase):
    def test_totp_matches_rfc_vector_with_six_digit_truncation(self) -> None:
        secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
        instant = datetime.fromtimestamp(59, tz=timezone.utc)
        self.assertTrue(verify_totp(secret, "287082", at=instant))
        self.assertFalse(verify_totp(secret, "287083", at=instant))

    def test_totp_secret_is_encrypted_at_rest(self) -> None:
        secret = "JBSWY3DPEHPK3PXP"
        ciphertext = encrypt_totp_secret(secret)
        self.assertNotIn(secret, ciphertext)
        self.assertEqual(decrypt_totp_secret(ciphertext), secret)

    def test_opaque_and_recovery_credentials_are_hashed(self) -> None:
        opaque = generate_opaque_credential()
        recovery_codes = generate_recovery_codes()
        self.assertEqual(len(recovery_codes), 10)
        self.assertEqual(len(set(recovery_codes)), 10)
        self.assertNotEqual(hash_opaque_credential(opaque), opaque)
        self.assertNotIn(recovery_codes[0], hash_recovery_code(recovery_codes[0]))


class PlatformAuthServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_mfa_enabled_login_requires_second_factor_before_session_creation(self) -> None:
        db = AsyncMock()
        operator = operator_fixture(mfa_enabled=True)
        db.scalar.return_value = operator
        with patch("app.services.platform_service.verify_password", return_value=True):
            with self.assertRaises(HTTPException) as raised:
                await PlatformAuthService(db).login(
                    operator.username,
                    "correct-password",
                    mfa_code=None,
                    ip_address="127.0.0.1",
                    user_agent="test",
                )
        self.assertEqual(raised.exception.status_code, 428)
        db.add.assert_not_called()

    async def test_recovery_code_is_consumed_once(self) -> None:
        operator = operator_fixture(mfa_enabled=True)
        operator.mfa_secret_ciphertext = encrypt_totp_secret("JBSWY3DPEHPK3PXP")
        recovery_code = "ABCD-EFGH-JKLM"
        operator.mfa_recovery_code_hashes = [hash_recovery_code(recovery_code)]

        self.assertTrue(PlatformAuthService._consume_mfa_code(operator, recovery_code))
        self.assertEqual(operator.mfa_recovery_code_hashes, [])
        self.assertFalse(PlatformAuthService._consume_mfa_code(operator, recovery_code))

    async def test_totp_code_is_consumed_once_per_time_step(self) -> None:
        operator = operator_fixture(mfa_enabled=True)
        secret = "JBSWY3DPEHPK3PXP"
        operator.mfa_secret_ciphertext = encrypt_totp_secret(secret)
        from app.utils.platform_security import totp_code

        code = totp_code(secret)
        self.assertTrue(PlatformAuthService._consume_mfa_code(operator, code))
        self.assertFalse(PlatformAuthService._consume_mfa_code(operator, code))

    async def test_refresh_rotates_both_opaque_and_csrf_credentials(self) -> None:
        db = AsyncMock()
        operator = operator_fixture()
        refresh_token = generate_opaque_credential()
        csrf_token = generate_opaque_credential()
        session = SimpleNamespace(
            id=uuid.uuid4(),
            operator_id=operator.id,
            credential_version=operator.credential_version,
            refresh_token_hash=hash_opaque_credential(refresh_token),
            csrf_token_hash=hash_opaque_credential(csrf_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            revoked_at=None,
            revocation_reason=None,
            mfa_verified_at=None,
            last_seen_at=datetime.now(timezone.utc),
            ip_address=None,
            user_agent=None,
        )
        old_refresh_hash = session.refresh_token_hash
        old_csrf_hash = session.csrf_token_hash
        db.scalar.return_value = session
        db.get.return_value = operator

        token_response, next_refresh = await PlatformAuthService(db).refresh(
            refresh_token,
            csrf_token,
            ip_address="127.0.0.2",
            user_agent="next-browser",
        )

        self.assertNotEqual(session.refresh_token_hash, old_refresh_hash)
        self.assertNotEqual(session.csrf_token_hash, old_csrf_hash)
        self.assertEqual(session.refresh_token_hash, hash_opaque_credential(next_refresh))
        self.assertEqual(session.csrf_token_hash, hash_opaque_credential(token_response.csrf_token))
        self.assertEqual(token_response.session_id, session.id)
        db.commit.assert_awaited_once()

    async def test_revoked_refresh_session_is_rejected(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = SimpleNamespace(revoked_at=datetime.now(timezone.utc))
        with self.assertRaises(HTTPException) as raised:
            await PlatformAuthService(db).refresh(
                "revoked-refresh",
                "csrf",
                ip_address=None,
                user_agent=None,
            )
        self.assertEqual(raised.exception.status_code, 401)


class PlatformSessionAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_access_token_is_bound_to_live_server_session(self) -> None:
        operator = operator_fixture()
        session = SimpleNamespace(
            id=uuid.uuid4(),
            mfa_verified_at=None,
        )
        token = create_platform_access_token(
            operator_id=operator.id,
            session_id=session.id,
            credential_version=operator.credential_version,
            is_superuser=True,
        )
        row = SimpleNamespace(one_or_none=lambda: (operator, session))
        db = AsyncMock()
        db.execute.return_value = row

        current = await get_current_platform_operator(token=token, db=db)

        self.assertEqual(current.operator_id, operator.id)
        self.assertEqual(current.session_id, session.id)
        self.assertFalse(current.mfa_verified)

    async def test_access_token_is_rejected_after_session_revocation(self) -> None:
        operator = operator_fixture()
        session_id = uuid.uuid4()
        token = create_platform_access_token(
            operator_id=operator.id,
            session_id=session_id,
            credential_version=operator.credential_version,
            is_superuser=True,
        )
        db = AsyncMock()
        db.execute.return_value = SimpleNamespace(one_or_none=lambda: None)

        with self.assertRaises(HTTPException) as raised:
            await get_current_platform_operator(token=token, db=db)
        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
