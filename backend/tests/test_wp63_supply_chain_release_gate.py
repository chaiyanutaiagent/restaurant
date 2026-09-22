from __future__ import annotations

import unittest

from app.config import validate_company_supply_chain_write_activation_config


class CompanySupplyChainReleaseConfigTests(unittest.TestCase):
    def test_disabled_flags_are_valid_in_every_environment(self) -> None:
        validate_company_supply_chain_write_activation_config(
            environment="production",
            public_base_url="https://pos.foodchainservice.com",
            kitchen_writes_enabled=False,
            distribution_writes_enabled=False,
        )

    def test_write_flags_fail_closed_outside_uat(self) -> None:
        with self.assertRaisesRegex(ValueError, "only in UAT"):
            validate_company_supply_chain_write_activation_config(
                environment="production",
                public_base_url="https://pos.foodchainservice.com",
                kitchen_writes_enabled=True,
                distribution_writes_enabled=False,
            )
        with self.assertRaisesRegex(ValueError, "HTTPS uat"):
            validate_company_supply_chain_write_activation_config(
                environment="development",
                public_base_url="https://pos.foodchainservice.com",
                kitchen_writes_enabled=True,
                distribution_writes_enabled=False,
            )

    def test_distribution_cannot_open_before_kitchen(self) -> None:
        with self.assertRaisesRegex(ValueError, "Kitchen writes first"):
            validate_company_supply_chain_write_activation_config(
                environment="development",
                public_base_url="https://uat-pos.foodchainservice.com",
                kitchen_writes_enabled=False,
                distribution_writes_enabled=True,
            )

    def test_bounded_uat_sequence_is_valid(self) -> None:
        validate_company_supply_chain_write_activation_config(
            environment="development",
            public_base_url="https://uat-pos.foodchainservice.com",
            kitchen_writes_enabled=True,
            distribution_writes_enabled=False,
        )
        validate_company_supply_chain_write_activation_config(
            environment="development",
            public_base_url="https://uat-pos.foodchainservice.com",
            kitchen_writes_enabled=True,
            distribution_writes_enabled=True,
        )


if __name__ == "__main__":
    unittest.main()
