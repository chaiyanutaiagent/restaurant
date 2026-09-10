from __future__ import annotations

import unittest
import uuid

from app.config import validate_uat_auth_bypass_config


class UatAuthBypassConfigTests(unittest.TestCase):
    company_id = uuid.UUID("1b8a1818-44d6-4d5f-9d22-e5e17b23c081")

    def test_disabled_bypass_is_safe_in_any_environment(self) -> None:
        validate_uat_auth_bypass_config(
            environment="production",
            enabled=False,
            public_base_url="https://foodchainservice.com",
            company_id=None,
            username=None,
        )

    def test_enabled_bypass_accepts_only_https_uat_development(self) -> None:
        validate_uat_auth_bypass_config(
            environment="development",
            enabled=True,
            public_base_url="https://uat-pos.foodchainservice.com",
            company_id=self.company_id,
            username="admin",
        )

        invalid_cases = (
            ("production", "https://uat-pos.foodchainservice.com"),
            ("staging", "https://uat-pos.foodchainservice.com"),
            ("development", "http://uat-pos.foodchainservice.com"),
            ("development", "https://foodchainservice.com"),
        )
        for environment, public_base_url in invalid_cases:
            with self.subTest(environment=environment, public_base_url=public_base_url):
                with self.assertRaises(ValueError):
                    validate_uat_auth_bypass_config(
                        environment=environment,
                        enabled=True,
                        public_base_url=public_base_url,
                        company_id=self.company_id,
                        username="admin",
                    )

    def test_enabled_bypass_requires_explicit_identity(self) -> None:
        for company_id, username in ((None, "admin"), (self.company_id, None), (self.company_id, " ")):
            with self.subTest(company_id=company_id, username=username):
                with self.assertRaises(ValueError):
                    validate_uat_auth_bypass_config(
                        environment="development",
                        enabled=True,
                        public_base_url="https://uat-pos.foodchainservice.com",
                        company_id=company_id,
                        username=username,
                    )


if __name__ == "__main__":
    unittest.main()
