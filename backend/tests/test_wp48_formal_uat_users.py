from __future__ import annotations

import argparse
import os
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

from app.cli.prepare_wp48_formal_uat_users import UAT_PROFILES, require_uat


def _args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "company_id": uuid.uuid4(),
        "branch_id": uuid.uuid4(),
        "actor_username": "admin",
        "rotate_passwords": False,
        "disable": False,
        "yes": True,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "saas_public_base_url": "https://uat-pos.foodchainservice.com",
        "environment": "development",
        "identity_database": "platform_core",
        "uat_auth_bypass_enabled": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class Wp48FormalUatUserGuardTests(unittest.TestCase):
    def test_refuses_non_uat_or_enabled_auth_bypass(self) -> None:
        for configured in (
            _settings(environment="production"),
            _settings(saas_public_base_url="https://pos.foodchainservice.com"),
            _settings(uat_auth_bypass_enabled=True),
        ):
            with self.subTest(configured=configured), patch(
                "app.cli.prepare_wp48_formal_uat_users.settings", configured
            ), self.assertRaises(RuntimeError):
                require_uat(_args())

    def test_requires_explicit_confirmation_and_passwords(self) -> None:
        with patch("app.cli.prepare_wp48_formal_uat_users.settings", _settings()):
            with self.assertRaisesRegex(RuntimeError, "--yes"):
                require_uat(_args(yes=False))
            with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(RuntimeError, "Missing password"):
                require_uat(_args())

    def test_accepts_bounded_uat_configuration_without_printing_passwords(self) -> None:
        passwords = {env_name: f"Safe-{index}-Pass!" for index, (_, _, env_name, _) in enumerate(UAT_PROFILES)}
        with patch("app.cli.prepare_wp48_formal_uat_users.settings", _settings()), patch.dict(os.environ, passwords, clear=True):
            require_uat(_args())

    def test_disable_mode_does_not_require_passwords(self) -> None:
        with patch("app.cli.prepare_wp48_formal_uat_users.settings", _settings()), patch.dict(os.environ, {}, clear=True):
            require_uat(_args(disable=True))


if __name__ == "__main__":
    unittest.main()
