from __future__ import annotations

import argparse
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

from app.cli.prepare_qa_isolation_fixture import require_bounded_qa_uat


class QaIsolationFixtureSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.company_id = uuid.uuid4()
        self.args = argparse.Namespace(
            primary_company_id=self.company_id,
            host="uat-pos.foodchainservice.com",
            base_url="http://nginx",
            yes=True,
        )

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

    def test_accepts_only_bounded_https_uat(self) -> None:
        with patch("app.cli.prepare_qa_isolation_fixture.settings", self._settings()):
            require_bounded_qa_uat(self.args)

        rejected = (
            self._settings(environment="production"),
            self._settings(saas_public_base_url="https://pos.foodchainservice.com"),
            self._settings(identity_database="legacy"),
            self._settings(qa_access_mode_enabled=False),
            self._settings(uat_auth_bypass_enabled=True),
            self._settings(qa_access_company_id=uuid.uuid4()),
        )
        for candidate in rejected:
            with self.subTest(candidate=candidate):
                with patch("app.cli.prepare_qa_isolation_fixture.settings", candidate):
                    with self.assertRaises(RuntimeError):
                        require_bounded_qa_uat(self.args)

    def test_requires_confirmation_and_matching_host(self) -> None:
        with patch("app.cli.prepare_qa_isolation_fixture.settings", self._settings()):
            with self.assertRaisesRegex(RuntimeError, "--yes"):
                require_bounded_qa_uat(argparse.Namespace(**{**vars(self.args), "yes": False}))
            with self.assertRaisesRegex(RuntimeError, "Host"):
                require_bounded_qa_uat(
                    argparse.Namespace(**{**vars(self.args), "host": "wrong.example.com"})
                )


if __name__ == "__main__":
    unittest.main()
