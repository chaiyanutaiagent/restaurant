from __future__ import annotations

import unittest

from app.config import validate_pos_offline_mode_config


class WP47OfflineSyncDesignGateTests(unittest.TestCase):
    def test_disabled_is_safe_in_every_environment(self) -> None:
        validate_pos_offline_mode_config(
            environment="production",
            enabled=False,
            public_base_url="https://pos.foodchainservice.com",
            company_allowlist="",
            branch_allowlist="",
        )

    def test_production_cannot_enable_planned_offline_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "not approved"):
            validate_pos_offline_mode_config(
                environment="production",
                enabled=True,
                public_base_url="https://pos.foodchainservice.com",
                company_allowlist="company-a",
                branch_allowlist="branch-a",
            )

    def test_uat_requires_https_uat_hostname_and_allowlists(self) -> None:
        for url, companies, branches in (
            ("http://uat-pos.foodchainservice.com", "company-a", "branch-a"),
            ("https://pos.foodchainservice.com", "company-a", "branch-a"),
            ("https://uat-pos.foodchainservice.com", "", "branch-a"),
            ("https://uat-pos.foodchainservice.com", "company-a", ""),
        ):
            with self.subTest(url=url, companies=companies, branches=branches):
                with self.assertRaises(ValueError):
                    validate_pos_offline_mode_config(
                        environment="development",
                        enabled=True,
                        public_base_url=url,
                        company_allowlist=companies,
                        branch_allowlist=branches,
                    )

    def test_bounded_uat_configuration_is_accepted(self) -> None:
        validate_pos_offline_mode_config(
            environment="development",
            enabled=True,
            public_base_url="https://uat-pos.foodchainservice.com",
            company_allowlist="company-a",
            branch_allowlist="branch-a",
        )


if __name__ == "__main__":
    unittest.main()
