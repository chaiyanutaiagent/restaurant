from __future__ import annotations

import argparse
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

from app.cli.prepare_qa_access_personas import (
    PLATFORM_PERSONAS,
    TENANT_PERSONAS,
    require_bounded_qa_uat,
)


class QaPersonaPreparationSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.company_id = uuid.uuid4()
        self.args = argparse.Namespace(company_id=self.company_id, yes=True)

    def _settings(self, **overrides):
        values = {
            "saas_public_base_url": "https://uat-pos.foodchainservice.com",
            "environment": "development",
            "identity_database": "platform_core",
            "qa_access_mode_enabled": True,
            "uat_auth_bypass_enabled": False,
            "qa_access_company_id": self.company_id,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_persona_matrix_covers_required_roles(self) -> None:
        self.assertEqual(
            {item.key for item in TENANT_PERSONAS},
            {
                "company_admin",
                "branch_manager",
                "cashier_service",
                "kitchen",
                "accountant",
                "purchasing",
                "warehouse",
                "auditor",
            },
        )
        self.assertEqual(
            {item.key for item in PLATFORM_PERSONAS},
            {"platform_admin", "platform_operator", "platform_auditor"},
        )

    def test_accepts_only_explicit_https_uat_development(self) -> None:
        with patch("app.cli.prepare_qa_access_personas.settings", self._settings()):
            require_bounded_qa_uat(self.args)

        rejected = (
            self._settings(environment="production"),
            self._settings(saas_public_base_url="https://pos.foodchainservice.com"),
            self._settings(saas_public_base_url="http://uat-pos.foodchainservice.com"),
            self._settings(identity_database="legacy"),
            self._settings(qa_access_mode_enabled=False),
            self._settings(uat_auth_bypass_enabled=True),
            self._settings(qa_access_company_id=uuid.uuid4()),
        )
        for candidate in rejected:
            with self.subTest(candidate=candidate):
                with patch("app.cli.prepare_qa_access_personas.settings", candidate):
                    with self.assertRaises(RuntimeError):
                        require_bounded_qa_uat(self.args)

    def test_requires_explicit_confirmation(self) -> None:
        args = argparse.Namespace(company_id=self.company_id, yes=False)
        with patch("app.cli.prepare_qa_access_personas.settings", self._settings()):
            with self.assertRaises(RuntimeError):
                require_bounded_qa_uat(args)


if __name__ == "__main__":
    unittest.main()
