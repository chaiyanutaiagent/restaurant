from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
import unittest
import uuid
from unittest.mock import AsyncMock

from fastapi import HTTPException
from pydantic import ValidationError

from app.routers.company_foundation import _audit_deep_link, _redact_audit_value
from app.schemas.company_access import CompanyAccessReviewRequest
from app.services.company_access_service import CompanyAccessService, invalidate_user_access
from app.utils.security import create_access_token, decode_token


class CompanyAccessContractTests(unittest.TestCase):
    def test_tenant_mfa_is_visible_but_remains_hold(self) -> None:
        posture = CompanyAccessService.security_posture()
        self.assertEqual(posture.tenant_mfa_policy, "hold")
        self.assertFalse(posture.tenant_mfa_enforcement_enabled)
        self.assertTrue(posture.session_management_enabled)
        self.assertEqual(posture.recovery_process_state, "product_owner_decision_required")

    def test_reduce_review_requires_exact_assignment(self) -> None:
        with self.assertRaises(ValidationError):
            CompanyAccessReviewRequest(
                outcome="reduce",
                reason="remove excessive permission",
                request_id=uuid.uuid4(),
                expected_credential_version=1,
            )

    def test_access_token_carries_user_version_and_session_id(self) -> None:
        session_id = uuid.uuid4()
        token = create_access_token(
            subject=str(uuid.uuid4()),
            company_id=str(uuid.uuid4()),
            branch_id=None,
            permissions=["system.user.view"],
            user_credential_version=7,
            session_id=str(session_id),
        )
        payload = decode_token(token)
        self.assertEqual(payload["user_credential_version"], 7)
        self.assertEqual(payload["sid"], str(session_id))

    def test_qa_token_is_marked_and_short_lived(self) -> None:
        deadline = datetime.now(timezone.utc) + timedelta(minutes=20)
        token = create_access_token(
            subject=str(uuid.uuid4()),
            company_id=str(uuid.uuid4()),
            branch_id=None,
            permissions=[],
            expires_delta=timedelta(minutes=20),
            qa_persona="company_owner",
            qa_deadline=deadline,
        )
        payload = decode_token(token)
        self.assertTrue(payload["qa_mode"])
        self.assertEqual(payload["qa_persona"], "company_owner")
        self.assertLessEqual(payload["exp"] - payload["iat"], 20 * 60)

    def test_company_audit_redacts_nested_credentials(self) -> None:
        value = _redact_audit_value({
            "password": "never-return",
            "nested": {"refresh_token": "never-return", "reason": "approved"},
            "items": [{"otp_code": "123456"}],
        })
        self.assertEqual(value["password"], "[REDACTED]")
        self.assertEqual(value["nested"]["refresh_token"], "[REDACTED]")
        self.assertEqual(value["nested"]["reason"], "approved")
        self.assertEqual(value["items"][0]["otp_code"], "[REDACTED]")

    def test_company_audit_user_event_has_safe_internal_deep_link(self) -> None:
        user_id = uuid.uuid4()
        row = SimpleNamespace(resource="User", resource_id=str(user_id), new_value={})
        self.assertEqual(_audit_deep_link(row), f"/company/access-reviews?user={user_id}")


class CompanyAccessAuthorityTests(unittest.IsolatedAsyncioTestCase):
    async def test_access_change_increments_version_and_revokes_sessions(self) -> None:
        db = AsyncMock()
        db.execute.return_value = SimpleNamespace(rowcount=3)
        user = SimpleNamespace(id=uuid.uuid4(), company_id=uuid.uuid4(), credential_version=4)
        count = await invalidate_user_access(db, user, reason="role changed")
        self.assertEqual(user.credential_version, 5)
        self.assertEqual(count, 3)
        db.execute.assert_awaited_once()

    async def test_stale_access_version_fails_closed(self) -> None:
        user = SimpleNamespace(credential_version=9)
        with self.assertRaises(HTTPException) as raised:
            CompanyAccessService._check_version(user, 8)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["code"], "stale_access_state")

    async def test_unknown_or_cross_tenant_user_is_not_disclosed(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = None
        with self.assertRaises(HTTPException) as raised:
            await CompanyAccessService(db).list_sessions(uuid.uuid4(), uuid.uuid4())
        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
