from __future__ import annotations

import argparse
from contextlib import redirect_stderr
import io
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

from app.cli.seed_ui_showcase import build_parser, fixture_id, require_uat


def args(*, yes: bool = True) -> argparse.Namespace:
    return argparse.Namespace(company_id=uuid.uuid4(), username="admin", yes=yes)


def uat_settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "saas_public_base_url": "https://uat-pos.foodchainservice.com",
        "environment": "development",
        "identity_database": "platform_core",
        "restaurant_service_database": "legacy",
        "retail_service_database": "retail",
        "takeaway_feature_enabled": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class SeedUiShowcaseGuardTests(unittest.TestCase):
    def test_parser_requires_explicit_company_and_username(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args([])

    def test_fixture_ids_are_stable_and_namespaced(self) -> None:
        self.assertEqual(fixture_id("customer", "1"), fixture_id("customer", "1"))
        self.assertNotEqual(fixture_id("customer", "1"), fixture_id("customer", "2"))
        self.assertNotEqual(fixture_id("customer", "1"), fixture_id("employee", "1"))

    def test_persistent_seed_requires_yes(self) -> None:
        with patch("app.cli.seed_ui_showcase.settings", uat_settings()), patch(
            "app.cli.seed_ui_showcase.TakeawaySessionLocal", object()
        ), patch("app.cli.seed_ui_showcase.RetailSessionLocal", object()):
            with self.assertRaisesRegex(RuntimeError, "--yes"):
                require_uat(args(yes=False))

    def test_command_refuses_production_and_non_uat_hosts(self) -> None:
        for unsafe in (
            uat_settings(environment="production"),
            uat_settings(saas_public_base_url="https://pos.foodchainservice.com"),
        ):
            with self.subTest(settings=unsafe), patch("app.cli.seed_ui_showcase.settings", unsafe):
                with self.assertRaisesRegex(RuntimeError, "restricted"):
                    require_uat(args())

    def test_command_accepts_complete_uat_boundaries(self) -> None:
        with patch("app.cli.seed_ui_showcase.settings", uat_settings()), patch(
            "app.cli.seed_ui_showcase.TakeawaySessionLocal", object()
        ), patch("app.cli.seed_ui_showcase.RetailSessionLocal", object()):
            require_uat(args())

    def test_command_requires_expected_boundary_databases(self) -> None:
        for unsafe in (
            uat_settings(identity_database="legacy"),
            uat_settings(restaurant_service_database="restaurant"),
            uat_settings(retail_service_database="legacy"),
            uat_settings(takeaway_feature_enabled=False),
        ):
            with self.subTest(settings=unsafe), patch("app.cli.seed_ui_showcase.settings", unsafe), patch(
                "app.cli.seed_ui_showcase.TakeawaySessionLocal", object()
            ), patch("app.cli.seed_ui_showcase.RetailSessionLocal", object()):
                with self.assertRaises(RuntimeError):
                    require_uat(args())


if __name__ == "__main__":
    unittest.main()
