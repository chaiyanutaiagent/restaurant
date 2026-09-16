from __future__ import annotations

import argparse
from contextlib import redirect_stderr
import io
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

from app.cli.prepare_multibusiness_uat import build_parser, require_uat


def args(*, yes: bool = True) -> argparse.Namespace:
    return argparse.Namespace(
        company_id=uuid.uuid4(),
        username="admin",
        yes=yes,
    )


def uat_settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "saas_public_base_url": "https://uat-pos.foodchainservice.com",
        "environment": "development",
        "identity_database": "platform_core",
        "reference_projector_enabled": True,
        "takeaway_feature_enabled": True,
        "takeaway_service_database": "takeaway",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class PrepareMultibusinessUatGuardTests(unittest.TestCase):
    def test_parser_requires_explicit_company_and_username(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args([])

    def test_persistent_uat_seed_requires_yes(self) -> None:
        with patch(
            "app.cli.prepare_multibusiness_uat.settings",
            uat_settings(),
        ), patch(
            "app.cli.prepare_multibusiness_uat.TakeawaySessionLocal",
            object(),
        ), patch(
            "app.cli.prepare_multibusiness_uat.RetailSessionLocal",
            object(),
        ):
            with self.assertRaisesRegex(RuntimeError, "--yes"):
                require_uat(args(yes=False))

    def test_command_refuses_production_or_non_uat_hosts(self) -> None:
        for unsafe in (
            uat_settings(environment="production"),
            uat_settings(saas_public_base_url="https://pos.foodchainservice.com"),
        ):
            with self.subTest(settings=unsafe), patch(
                "app.cli.prepare_multibusiness_uat.settings",
                unsafe,
            ):
                with self.assertRaisesRegex(RuntimeError, "restricted"):
                    require_uat(args())

    def test_command_accepts_complete_uat_boundary_configuration(self) -> None:
        with patch(
            "app.cli.prepare_multibusiness_uat.settings",
            uat_settings(),
        ), patch(
            "app.cli.prepare_multibusiness_uat.TakeawaySessionLocal",
            object(),
        ), patch(
            "app.cli.prepare_multibusiness_uat.RetailSessionLocal",
            object(),
        ):
            require_uat(args())

    def test_command_requires_dedicated_boundary_sessions(self) -> None:
        with patch(
            "app.cli.prepare_multibusiness_uat.settings",
            uat_settings(),
        ), patch(
            "app.cli.prepare_multibusiness_uat.TakeawaySessionLocal",
            None,
        ), patch(
            "app.cli.prepare_multibusiness_uat.RetailSessionLocal",
            object(),
        ):
            with self.assertRaisesRegex(RuntimeError, "database URLs"):
                require_uat(args())


if __name__ == "__main__":
    unittest.main()
