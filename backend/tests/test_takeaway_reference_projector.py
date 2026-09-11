from __future__ import annotations

from datetime import datetime, timezone
import unittest
import uuid

from app.services.takeaway_reference_projector import (
    canonical_reference_payload,
    safe_reference_columns,
)


class TakeawayReferenceProjectorTests(unittest.TestCase):
    def test_user_projection_excludes_credentials(self) -> None:
        columns = safe_reference_columns("user")
        self.assertNotIn("hashed_password", columns)
        self.assertIn("username", columns)
        self.assertIn("is_active", columns)

    def test_reference_digest_is_deterministic_and_json_safe(self) -> None:
        row = {
            "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
            "updated_at": datetime(2026, 9, 11, tzinfo=timezone.utc),
            "name": "สาขาทดสอบ",
        }
        first_payload, first_digest = canonical_reference_payload(row)
        second_payload, second_digest = canonical_reference_payload(dict(reversed(row.items())))
        self.assertEqual(first_payload, second_payload)
        self.assertEqual(first_digest, second_digest)
        self.assertEqual(len(first_digest), 64)


if __name__ == "__main__":
    unittest.main()
