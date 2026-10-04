from __future__ import annotations

import unittest

from app.config import resolve_api_docs_enabled


class ApiDocsConfigTests(unittest.TestCase):
    def test_production_defaults_to_disabled(self) -> None:
        self.assertFalse(resolve_api_docs_enabled("production", None))

    def test_non_production_defaults_to_enabled(self) -> None:
        for environment in ("development", "staging", "test"):
            with self.subTest(environment=environment):
                self.assertTrue(resolve_api_docs_enabled(environment, None))

    def test_explicit_setting_wins(self) -> None:
        self.assertTrue(resolve_api_docs_enabled("production", True))
        self.assertFalse(resolve_api_docs_enabled("development", False))


if __name__ == "__main__":
    unittest.main()
