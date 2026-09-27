from __future__ import annotations

import argparse
from contextlib import redirect_stderr
import io
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

from app.cli.prepare_sketch_biz_uat import (
    LEGAL_NAME_EN,
    LEGAL_NAME_TH,
    REGISTRATION_ID,
    SKETCH_BIZ_COMPANY_ID,
    UAT_VAT_RATE,
    WORKSPACES,
    build_parser,
    require_uat,
    validate_registration_id,
    workspace_keys,
)


def args(*, company_id: uuid.UUID = SKETCH_BIZ_COMPANY_ID, yes: bool = True) -> argparse.Namespace:
    return argparse.Namespace(company_id=company_id, username="admin", yes=yes)


def uat_settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "saas_public_base_url": "https://uat-app.foodchainservice.com",
        "environment": "development",
        "identity_database": "platform_core",
        "reference_projector_enabled": True,
        "restaurant_service_database": "legacy",
        "retail_service_database": "retail",
        "takeaway_feature_enabled": True,
        "takeaway_service_database": "takeaway",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class SketchBizUatContractTests(unittest.TestCase):
    def test_parser_requires_explicit_target_and_confirmation(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args([])

    def test_legal_identity_is_exact(self) -> None:
        self.assertEqual(LEGAL_NAME_TH, "บริษัท สเก็ตช์ บีซ จำกัด")
        self.assertEqual(LEGAL_NAME_EN, "SKETCH BIZ CO., LTD.")
        self.assertEqual(REGISTRATION_ID, "0125568025206")
        validate_registration_id(REGISTRATION_ID)
        self.assertEqual(str(UAT_VAT_RATE), "7.00")

    def test_registration_id_rejects_invalid_values(self) -> None:
        for value in ("", "123", "012556802520A", "00125568025206"):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                validate_registration_id(value)

    def test_workspace_hierarchy_matches_approved_company_structure(self) -> None:
        self.assertEqual(
            workspace_keys(),
            ("krua-pa-pla-khuen", "the-loft-kitchen", "the-loft-mini-mart", "chambo"),
        )
        self.assertEqual([row.business_type for row in WORKSPACES], ["restaurant", "restaurant", "retail_pos", "takeaway"])
        self.assertEqual(len({row.brand_slug for row in WORKSPACES}), 4)
        self.assertEqual(len({row.branch_code for row in WORKSPACES}), 4)

    def test_guard_accepts_only_pinned_complete_uat(self) -> None:
        with patch("app.cli.prepare_sketch_biz_uat.settings", uat_settings()), patch(
            "app.cli.prepare_sketch_biz_uat.RetailSessionLocal", object()
        ), patch("app.cli.prepare_sketch_biz_uat.TakeawaySessionLocal", object()):
            require_uat(args())

    def test_guard_rejects_unsafe_boundaries(self) -> None:
        cases = (
            (args(yes=False), uat_settings(), "--yes"),
            (args(company_id=uuid.uuid4()), uat_settings(), "pinned"),
            (args(), uat_settings(environment="production"), "restricted"),
            (args(), uat_settings(saas_public_base_url="https://app.foodchainservice.com"), "restricted"),
            (args(), uat_settings(reference_projector_enabled=False), "projection"),
            (args(), uat_settings(restaurant_service_database="restaurant"), "Legacy"),
            (args(), uat_settings(retail_service_database="legacy"), "Retail"),
            (args(), uat_settings(takeaway_feature_enabled=False), "Takeaway"),
        )
        for configured_args, configured_settings, message in cases:
            with self.subTest(message=message), patch(
                "app.cli.prepare_sketch_biz_uat.settings", configured_settings
            ), patch("app.cli.prepare_sketch_biz_uat.RetailSessionLocal", object()), patch(
                "app.cli.prepare_sketch_biz_uat.TakeawaySessionLocal", object()
            ), self.assertRaisesRegex(RuntimeError, message):
                require_uat(configured_args)


if __name__ == "__main__":
    unittest.main()
