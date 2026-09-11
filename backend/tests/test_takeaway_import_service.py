from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from app.services.takeaway_import_service import (
    CONTRACT,
    MAPPING_CONTRACT,
    SCHEMA_VERSION,
    canonical_record_hash,
    validate_takeaway_import_package,
)
from app.cli.validate_takeaway_import import validate_bundle


class TakeawayImportValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.company_id = uuid.uuid4()
        self.brand_id = uuid.uuid4()
        self.export_id = uuid.uuid4()
        self.category_id = uuid.uuid4()
        category_data = {
            "code": "food",
            "name": "อาหาร",
            "parent_source_id": None,
            "sort_order": 0,
            "is_active": True,
        }
        self.records = [
            {
                "record_type": "category",
                "source_id": str(self.category_id),
                "source_updated_at": "2026-09-11T00:00:00Z",
                "source_hash": canonical_record_hash(
                    "category", str(self.category_id), category_data
                ),
                "data": category_data,
            }
        ]
        self.manifest = {
            "contract": CONTRACT,
            "schema_version": SCHEMA_VERSION,
            "export_id": str(self.export_id),
            "generated_at": "2026-09-11T00:00:00Z",
            "cutoff_at": "2026-09-11T00:00:00Z",
            "timezone": "Asia/Bangkok",
            "source": {
                "system": "erp-pos-run",
                "repository": "chaiyanutaiagent/erp-pos-run",
                "repository_commit": "1" * 40,
                "migration_head": "synthetic",
                "environment": "synthetic",
                "snapshot_id": "synthetic-fixture",
                "read_only": True,
            },
            "scope": {},
            "mapping": {"path": "mapping.json", "sha256": "0" * 64},
            "files": [],
            "omitted_sections": [],
            "record_totals": {"categories": 1},
            "security_attestation": {
                "forbidden_field_findings": 0,
                "unapproved_pii_findings": 0,
                "unsafe_media_findings": 0,
                "scanner_version": "test",
            },
        }
        self.mapping = {
            "contract": MAPPING_CONTRACT,
            "schema_version": SCHEMA_VERSION,
            "mapping_id": str(uuid.uuid4()),
            "export_id": str(self.export_id),
            "company": {"source_id": str(uuid.uuid4()), "target_id": str(self.company_id)},
            "brand": {
                "source_id": str(uuid.uuid4()),
                "target_id": str(self.brand_id),
                "business_type": "takeaway",
            },
            "branches": [],
        }

    def validate(self, *, manifest=None, mapping=None, records=None):
        return validate_takeaway_import_package(
            manifest=self.manifest if manifest is None else manifest,
            mapping=self.mapping if mapping is None else mapping,
            records=self.records if records is None else records,
            expected_company_id=self.company_id,
            expected_brand_id=self.brand_id,
        )

    def test_valid_synthetic_package_passes(self) -> None:
        report = self.validate()
        self.assertEqual(report.status, "ok")
        self.assertEqual(report.accepted_records, 1)
        self.assertEqual(report.side_effects_planned_for_history, 0)

    def test_tampered_record_hash_is_rejected(self) -> None:
        records = copy.deepcopy(self.records)
        records[0]["data"]["name"] = "ถูกแก้หลัง seal"
        report = self.validate(records=records)
        self.assertEqual(report.status, "rejected")
        self.assertIn("record_hash_mismatch", {row["code"] for row in report.findings})

    def test_forbidden_credentials_and_unapproved_pii_are_rejected(self) -> None:
        records = copy.deepcopy(self.records)
        records[0]["data"]["access_token"] = "secret"
        records[0]["data"]["customer_phone"] = "0800000000"
        records[0]["source_hash"] = canonical_record_hash(
            "category", records[0]["source_id"], records[0]["data"]
        )
        report = self.validate(records=records)
        codes = {row["code"] for row in report.findings}
        self.assertIn("forbidden_field", codes)
        self.assertIn("unapproved_pii", codes)

    def test_historical_records_never_plan_side_effects(self) -> None:
        source_id = str(uuid.uuid4())
        data = {"legacy_document_number": "OLD-1"}
        record = {
            "record_type": "historical_sale",
            "source_id": source_id,
            "source_updated_at": "2026-09-11T00:00:00Z",
            "source_hash": canonical_record_hash("historical_sale", source_id, data),
            "data": data,
        }
        manifest = copy.deepcopy(self.manifest)
        manifest["record_totals"] = {"historical_sales": 1}
        report = self.validate(manifest=manifest, records=[record])
        self.assertEqual(report.status, "ok")
        self.assertEqual(report.historical_records, 1)
        self.assertEqual(report.side_effects_planned_for_history, 0)

    def test_sealed_bundle_is_verified_offline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            mapping_bytes = json.dumps(self.mapping, sort_keys=True).encode()
            (bundle / "mapping.json").write_bytes(mapping_bytes)
            records_bytes = (
                "\n".join(json.dumps(row, sort_keys=True) for row in self.records) + "\n"
            ).encode()
            (bundle / "records.ndjson").write_bytes(records_bytes)
            manifest = copy.deepcopy(self.manifest)
            manifest["mapping"]["sha256"] = hashlib.sha256(mapping_bytes).hexdigest()
            manifest["files"] = [
                {
                    "path": "records.ndjson",
                    "media_type": "application/x-ndjson",
                    "sha256": hashlib.sha256(records_bytes).hexdigest(),
                    "byte_size": len(records_bytes),
                    "record_count": 1,
                }
            ]
            (bundle / "manifest.json").write_text(
                json.dumps(manifest, sort_keys=True), encoding="utf-8"
            )
            report = validate_bundle(bundle)
            self.assertEqual(report["status"], "ok")
            self.assertEqual(report["bundle_findings"], [])

    def test_bundle_path_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            mapping_bytes = json.dumps(self.mapping, sort_keys=True).encode()
            (bundle / "mapping.json").write_bytes(mapping_bytes)
            manifest = copy.deepcopy(self.manifest)
            manifest["mapping"]["sha256"] = hashlib.sha256(mapping_bytes).hexdigest()
            manifest["files"] = [
                {
                    "path": "../records.ndjson",
                    "media_type": "application/x-ndjson",
                    "sha256": "0" * 64,
                    "byte_size": 0,
                    "record_count": 0,
                }
            ]
            manifest["record_totals"] = {}
            (bundle / "manifest.json").write_text(
                json.dumps(manifest, sort_keys=True), encoding="utf-8"
            )
            report = validate_bundle(bundle)
            self.assertEqual(report["status"], "rejected")
            self.assertIn("unsafe_file_path", {row["code"] for row in report["bundle_findings"]})


if __name__ == "__main__":
    unittest.main()
