from __future__ import annotations

import unittest
from unittest.mock import patch

from app.database import AsyncSessionLocal, RetailSessionLocal
from app.services.shared_reporting_worker import configured_reporting_sources


class SharedReportingSourceTests(unittest.TestCase):
    def test_legacy_mode_does_not_add_retail_stream(self) -> None:
        with patch(
            "app.services.shared_reporting_worker.settings.retail_service_database",
            "legacy",
        ):
            names = [source.name for source in configured_reporting_sources()]
        self.assertIn("legacy_pos", names)
        self.assertNotIn("retail_pos", names)

    def test_cutover_adds_retail_stream_when_database_is_configured(self) -> None:
        if RetailSessionLocal is None:
            self.skipTest("RETAIL_DATABASE_URL is not configured in this test process")
        with patch(
            "app.services.shared_reporting_worker.settings.retail_service_database",
            "retail",
        ):
            sources = {source.name: source for source in configured_reporting_sources()}
        self.assertIs(sources["legacy_pos"].session_factory, AsyncSessionLocal)
        self.assertIs(sources["retail_pos"].session_factory, RetailSessionLocal)
        self.assertEqual(sources["retail_pos"].kind, "legacy")
