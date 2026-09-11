from __future__ import annotations

from datetime import date
import unittest

from pydantic import ValidationError

from app.schemas.saas_privacy_support import (
    PrivacyRequestUpdate,
    RetentionDecisionCreate,
    SupportAccessRequest,
    SupportTicketCreate,
)


class PrivacySupportSchemaTests(unittest.TestCase):
    def test_resolved_privacy_request_requires_safe_response_summary(self) -> None:
        with self.assertRaises(ValidationError):
            PrivacyRequestUpdate(status="fulfilled", reason="done")
        row = PrivacyRequestUpdate(
            status="fulfilled",
            response_summary="Account-level export delivered through an approved channel",
            reason="requester identity and delivery were verified",
        )
        self.assertEqual(row.status, "fulfilled")

    def test_retention_intent_is_explicit_and_non_executing(self) -> None:
        with self.assertRaises(ValidationError):
            RetentionDecisionCreate(
                data_category="billing_records",
                action="retain",
                rationale="Required for an unresolved accounting review",
                reason="propose retention",
            )
        row = RetentionDecisionCreate(
            data_category="billing_records",
            action="retain",
            rationale="Required for an unresolved accounting review",
            retain_until=date(2027, 8, 3),
            reason="propose retention",
        )
        self.assertEqual(row.action, "retain")
        with self.assertRaises(ValidationError):
            RetentionDecisionCreate(
                data_category="support_records",
                action="delete",
                rationale="request accepted",
                retain_until=date(2027, 8, 3),
                reason="invalid mixed intent",
            )

    def test_support_access_is_named_unique_and_time_capped(self) -> None:
        request = SupportAccessRequest(
            requested_scopes=["billing_state", "account_state"],
            purpose="Investigate account lifecycle mismatch",
            duration_minutes=30,
            reason="Tenant approval required",
        )
        self.assertEqual(request.requested_scopes, ["account_state", "billing_state"])
        with self.assertRaises(ValidationError):
            SupportAccessRequest(
                requested_scopes=["account_state", "account_state"],
                purpose="duplicate scope",
                duration_minutes=30,
                reason="reject duplicate",
            )
        with self.assertRaises(ValidationError):
            SupportAccessRequest(
                requested_scopes=["account_state"],
                purpose="too long",
                duration_minutes=61,
                reason="reject duration",
            )

    def test_ticket_payload_rejects_unbounded_extra_fields(self) -> None:
        with self.assertRaises(ValidationError):
            SupportTicketCreate(
                category="technical",
                subject="ช่วยตรวจสอบ",
                initial_message="พบปัญหาเข้าสู่ระบบ",
                remote_shell=True,
            )


if __name__ == "__main__":
    unittest.main()
