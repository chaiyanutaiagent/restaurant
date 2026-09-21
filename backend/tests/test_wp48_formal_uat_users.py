from __future__ import annotations

import argparse
import asyncio
import os
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import AsyncMock, Mock, patch

from app.cli.prepare_wp48_formal_uat_users import UAT_PROFILES, _ensure_role, require_uat
from app.models.role import Permission
from app.services.role_preset_service import ROLE_PRESET_POLICIES


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
    def test_new_role_populates_permissions_without_async_lazy_load(self) -> None:
        policy = next(item for item in ROLE_PRESET_POLICIES if item.key == "cashier")
        permissions = [Permission(code=code, name=code) for code in policy.permission_codes]
        scalars_result = SimpleNamespace(all=lambda: permissions)
        db = AsyncMock()
        db.scalars.return_value = scalars_result
        db.scalar.return_value = None
        db.add = Mock()

        role = asyncio.run(_ensure_role(db, uuid.uuid4(), "cashier"))

        self.assertEqual({permission.code for permission in role.permissions}, set(policy.permission_codes))
        db.add.assert_called_once_with(role)
        db.flush.assert_awaited_once()

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
