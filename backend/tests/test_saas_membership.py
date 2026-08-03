from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from pydantic import ValidationError

from app.config import validate_saas_email_delivery_config
from app.schemas.membership import SaasSignupRequest
from app.services.saas_membership_service import (
    effective_membership_status,
    hash_account_credential,
    membership_access_error,
)


class SaasMembershipSchemaTests(unittest.TestCase):
    def test_signup_normalizes_identity_and_requires_consent(self) -> None:
        request = SaasSignupRequest(
            company_name=" ร้านตัวอย่าง ",
            owner_display_name=" เจ้าของร้าน ",
            owner_email=" OWNER@Example.COM ",
            username=" Owner.One ",
            password="A-Strong-Password!",
            terms_accepted=True,
            privacy_accepted=True,
        )
        self.assertEqual(request.company_name, "ร้านตัวอย่าง")
        self.assertEqual(request.owner_email, "owner@example.com")
        self.assertEqual(request.username, "owner.one")

        with self.assertRaises(ValidationError):
            SaasSignupRequest(
                company_name="ร้าน",
                owner_display_name="เจ้าของ",
                owner_email="owner@example.com",
                username="owner.one",
                password="A-Strong-Password!",
                terms_accepted=False,
                privacy_accepted=True,
            )

    def test_raw_account_credential_is_not_the_stored_value(self) -> None:
        raw = "raw-membership-token-that-must-not-be-stored"
        hashed = hash_account_credential(raw)
        self.assertNotEqual(raw, hashed)
        self.assertEqual(len(hashed), 64)
        self.assertEqual(hashed, hash_account_credential(raw))


class SaasMembershipAccessTests(unittest.TestCase):
    def test_pending_and_expired_trials_are_blocked(self) -> None:
        pending = SimpleNamespace(status="pending_verification", trial_ends_at=None)
        self.assertEqual(membership_access_error(pending), "Email verification is required")

        expired = SimpleNamespace(
            status="trial_active",
            trial_ends_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        self.assertEqual(effective_membership_status(expired), "trial_expired")
        self.assertEqual(membership_access_error(expired), "SaaS trial has expired")

    def test_active_trial_and_legacy_absence_policy_are_compatible(self) -> None:
        trial = SimpleNamespace(
            status="trial_active",
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        self.assertIsNone(membership_access_error(trial))


class SaasEmailConfigTests(unittest.TestCase):
    def test_production_requires_smtp_and_https(self) -> None:
        with self.assertRaises(ValueError):
            validate_saas_email_delivery_config(
                environment="production",
                mode="console",
                public_base_url="https://saas.example.com",
                smtp_host=None,
                smtp_from_email=None,
            )
        with self.assertRaises(ValueError):
            validate_saas_email_delivery_config(
                environment="production",
                mode="smtp",
                public_base_url="http://saas.example.com",
                smtp_host="smtp.example.com",
                smtp_from_email="no-reply@example.com",
            )
        validate_saas_email_delivery_config(
            environment="production",
            mode="smtp",
            public_base_url="https://saas.example.com",
            smtp_host="smtp.example.com",
            smtp_from_email="no-reply@example.com",
        )


if __name__ == "__main__":
    unittest.main()
