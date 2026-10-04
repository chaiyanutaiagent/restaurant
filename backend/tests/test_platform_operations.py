from __future__ import annotations

import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from app.main import health_ready
from app.schemas.platform import PlatformOperationsEvidenceImport
from app.services.platform_operations_service import resilience_evidence_to_import


class PlatformOperationsEvidenceTests(unittest.TestCase):
    def test_schema_rejects_paths_raw_errors_and_unknown_codes(self) -> None:
        base = {
            "captured_at": "2026-08-03T08:00:00Z",
            "overall_status": "ok",
            "component_checks": {"public_api": "ok"},
        }
        with self.assertRaises(ValidationError):
            PlatformOperationsEvidenceImport(
                **base,
                backup_path="/secure/backups/private.dump",
            )
        with self.assertRaises(ValidationError):
            PlatformOperationsEvidenceImport(
                **{**base, "component_checks": {"postgres_exception": "error"}},
            )
        with self.assertRaises(ValidationError):
            PlatformOperationsEvidenceImport(
                **base,
                alert_codes=["raw-stack-trace"],
            )

    def test_resilience_evidence_is_reduced_to_allowlisted_state(self) -> None:
        parsed = resilience_evidence_to_import(
            {
                "timestamp": "2026-08-03T08:00:00Z",
                "status": "critical",
                "health_http_code": "503",
                "reference_projector_failed_events": 2,
                "reference_projector_loop_errors": 0,
                "disk_usage_percent": 81,
                "latest_backup": "/secure/backups/private-tenant",
                "backup_age_hours": 30,
                "alert_delivery_configured": False,
                "restore_status": "passed",
                "restore_drill_at": "2026-08-02T08:00:00Z",
                "alerts": [
                    "latest tenant backup is 30h old; maximum is 26h",
                    "private database password=must-not-persist",
                ],
            }
        )
        serialized = json.dumps(parsed.model_dump(mode="json"), sort_keys=True)
        self.assertEqual(parsed.backup_status, "stale")
        self.assertEqual(parsed.restore_status, "passed")
        self.assertIn("backup_stale", parsed.alert_codes)
        self.assertNotIn("/secure/backups", serialized)
        self.assertNotIn("must-not-persist", serialized)


class PublicHealthSanitizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_readiness_returns_only_status_and_version(self) -> None:
        runtime = SimpleNamespace(status="ok")
        with patch("app.main.collect_runtime_state", new=AsyncMock(return_value=runtime)):
            response = await health_ready()
        payload = json.loads(response.body)
        self.assertEqual(set(payload), {"status", "version"})
        self.assertNotIn("runtime", payload)
        self.assertNotIn("checks", payload)


if __name__ == "__main__":
    unittest.main()
