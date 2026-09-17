from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import unittest
import uuid

from app.cli.snapshot_chambo_takeaway import _decimal, _location_type, _record, _utc


class ChamboSnapshotExporterTests(unittest.TestCase):
    def test_decimal_and_timestamp_are_deterministic_strings(self) -> None:
        self.assertEqual(_decimal(Decimal("10.5000")), "10.5000")
        self.assertEqual(
            _utc(datetime(2026, 9, 17, 7, 0, tzinfo=timezone.utc)),
            "2026-09-17T07:00:00Z",
        )

    def test_location_type_prefers_explicit_brand_ownership(self) -> None:
        location_id = str(uuid.uuid4())
        row = {"id": location_id, "code": "MAIN", "name": "คลังหลัก"}
        self.assertEqual(
            _location_type(
                row,
                central_raw_id=location_id,
                central_ready_id=None,
                store_location_ids=set(),
            ),
            "central_raw",
        )
        self.assertEqual(
            _location_type(
                row,
                central_raw_id=None,
                central_ready_id=None,
                store_location_ids={location_id},
            ),
            "store",
        )

    def test_record_does_not_add_credentials_or_customer_pii(self) -> None:
        record_id = uuid.uuid4()
        record = _record(
            "historical_sale",
            {
                "id": record_id,
                "created_at": datetime(2026, 9, 17, 7, 0, tzinfo=timezone.utc),
            },
            {"legacy_document_number": "SALE-1", "total_amount": "10.00"},
        )
        self.assertEqual(record["source_id"], str(record_id))
        self.assertNotIn("customer_name", record["data"])
        self.assertNotIn("access_token", record["data"])


if __name__ == "__main__":
    unittest.main()
