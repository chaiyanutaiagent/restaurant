from __future__ import annotations

import argparse
import asyncio
from contextlib import redirect_stderr
import io
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

from app.cli.seed_ui_showcase import (
    SHOWCASE_COMPANY_PROFILE,
    build_parser,
    fixture_id,
    mirror_platform_references_to_legacy,
    require_uat,
)


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

    def test_company_showcase_profile_is_explicitly_synthetic(self) -> None:
        self.assertIn("เดโม", SHOWCASE_COMPANY_PROFILE["name"])
        self.assertIn("[ข้อมูลตัวอย่าง]", SHOWCASE_COMPANY_PROFILE["address"])
        self.assertTrue(SHOWCASE_COMPANY_PROFILE["email"].endswith("@example.invalid"))
        self.assertEqual(len(SHOWCASE_COMPANY_PROFILE["tax_id"]), 13)

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

    def test_legacy_brand_branch_is_reused_by_business_key(self) -> None:
        company_id = uuid.uuid4()
        brand_id = uuid.uuid4()
        branch_id = uuid.uuid4()
        platform_link_id = uuid.uuid4()
        existing_link_id = uuid.uuid4()
        company = SimpleNamespace(
            id=company_id,
            business_slug="uat",
            **SHOWCASE_COMPANY_PROFILE,
        )
        existing_link = SimpleNamespace(
            id=existing_link_id,
            company_id=company_id,
            brand_id=brand_id,
            branch_id=branch_id,
            branch_type="franchise",
            is_active=False,
        )

        class FakeSession:
            async def get(self, model: object, object_id: uuid.UUID) -> object | None:
                if getattr(model, "__name__", "") == "Company":
                    return company
                return None

            async def scalar(self, _statement: object) -> object:
                return existing_link

            def add(self, _row: object) -> None:
                self.fail("a duplicate BrandBranch must not be inserted")

            async def flush(self) -> None:
                return None

            async def commit(self) -> None:
                return None

            def fail(self, message: str) -> None:
                raise AssertionError(message)

        class FakeContext:
            async def __aenter__(self) -> FakeSession:
                return FakeSession()

            async def __aexit__(self, *_args: object) -> None:
                return None

        references = {
            "branches": [],
            "brands": [],
            "links": [
                {
                    "id": platform_link_id,
                    "brand_id": brand_id,
                    "branch_id": branch_id,
                    "branch_type": "company_owned",
                    "is_active": True,
                }
            ],
        }
        with patch("app.cli.seed_ui_showcase.AsyncSessionLocal", return_value=FakeContext()):
            asyncio.run(mirror_platform_references_to_legacy(company, references))

        self.assertEqual(existing_link.id, existing_link_id)
        self.assertNotEqual(existing_link.id, platform_link_id)
        self.assertEqual(existing_link.branch_type, "company_owned")
        self.assertTrue(existing_link.is_active)


if __name__ == "__main__":
    unittest.main()
