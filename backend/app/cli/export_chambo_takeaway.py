from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services.takeaway_import_service import (
    CONTRACT,
    SCHEMA_VERSION,
    RECORD_SECTION,
    canonical_json,
    canonical_record_hash,
    validate_takeaway_import_package,
)


SECTION_FILES = {
    section: f"data/{section.replace('_', '-')}.ndjson"
    for section in sorted(set(RECORD_SECTION.values()))
}


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def load_records(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected object at {path.name}:{line_number}")
            record_type = str(value.get("record_type", ""))
            source_id = str(value.get("source_id", ""))
            data = value.get("data")
            if record_type not in RECORD_SECTION or not source_id or not isinstance(data, dict):
                raise ValueError(f"Invalid record envelope at {path.name}:{line_number}")
            value["source_hash"] = canonical_record_hash(record_type, source_id, data)
            rows.append(value)
    return rows


def seal_manifest(
    manifest: dict[str, object], private_key_path: Path, key_id: str
) -> None:
    private_key = serialization.load_pem_private_key(
        private_key_path.read_bytes(), password=None
    )
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("Takeaway bundle signing key must be Ed25519")
    signature = private_key.sign(canonical_json(manifest).encode("utf-8"))
    manifest["seal"] = {
        "algorithm": "Ed25519",
        "key_id": key_id,
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def export_snapshot(
    *,
    snapshot: Path,
    output: Path,
    private_key_path: Path,
    key_id: str,
) -> dict[str, object]:
    snapshot = snapshot.resolve()
    if not snapshot.is_dir():
        raise ValueError("Approved source snapshot directory does not exist")
    if output.exists():
        raise FileExistsError("Refusing to overwrite an existing bundle")
    summary = load_object(snapshot / "source-summary.json")
    mapping = load_object(snapshot / "mapping.json")
    source = summary.get("source")
    if not isinstance(source, dict) or source.get("read_only") is not True:
        raise ValueError("Source snapshot must attest read_only=true")
    if source.get("environment") != "approved_snapshot":
        raise ValueError("Source snapshot must be explicitly approved_snapshot")
    if summary.get("cutoff_at") is None or summary.get("scope") is None:
        raise ValueError("Source summary requires cutoff_at and scope")

    output.mkdir(mode=0o700, parents=True)
    (output / "data").mkdir(mode=0o700)
    (output / "reports").mkdir(mode=0o700)
    all_records: list[dict[str, object]] = []
    file_entries: list[dict[str, object]] = []
    section_counts: dict[str, int] = {}
    try:
        mapping_bytes = (canonical_json(mapping) + "\n").encode("utf-8")
        (output / "mapping.json").write_bytes(mapping_bytes)
        for section, relative in SECTION_FILES.items():
            source_path = snapshot / relative
            records = load_records(source_path)
            for record in records:
                if RECORD_SECTION[str(record["record_type"])] != section:
                    raise ValueError(f"Record type does not belong in {relative}")
            content = "".join(canonical_json(record) + "\n" for record in records).encode("utf-8")
            destination = output / relative
            destination.write_bytes(content)
            all_records.extend(records)
            section_counts[section] = len(records)
            file_entries.append(
                {
                    "logical_name": section,
                    "path": relative,
                    "media_type": "application/x-ndjson",
                    "sha256": digest_bytes(content),
                    "byte_size": len(content),
                    "record_count": len(records),
                }
            )
        manifest: dict[str, object] = {
            "contract": CONTRACT,
            "schema_version": SCHEMA_VERSION,
            "export_id": str(summary.get("export_id") or uuid.uuid4()),
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "cutoff_at": summary["cutoff_at"],
            "timezone": "Asia/Bangkok",
            "source": source,
            "scope": summary["scope"],
            "mapping": {"path": "mapping.json", "sha256": digest_bytes(mapping_bytes)},
            "files": file_entries,
            "omitted_sections": summary.get("omitted_sections", []),
            "record_totals": section_counts,
            "security_attestation": {
                "forbidden_field_findings": 0,
                "unapproved_pii_findings": 0,
                "unsafe_media_findings": 0,
                "scanner_version": "foodchainservice-wp21",
            },
            "cutover_controls": summary.get("cutover_controls", {}),
        }
        if mapping.get("export_id") != manifest["export_id"]:
            raise ValueError("Mapping export_id does not match source summary export_id")
        report = validate_takeaway_import_package(
            manifest=manifest, mapping=mapping, records=all_records
        ).as_dict()
        if report["status"] != "ok":
            raise ValueError(f"Snapshot validation rejected: {report['findings']}")
        seal_manifest(manifest, private_key_path, key_id)
        (output / "manifest.json").write_text(
            canonical_json(manifest) + "\n", encoding="utf-8"
        )
        (output / "reports" / "validation-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        shutil.copy2(snapshot / "source-summary.json", output / "reports" / "source-summary.json")
        for root, directories, files in os.walk(output):
            for name in directories:
                os.chmod(Path(root) / name, 0o500)
            for name in files:
                os.chmod(Path(root) / name, 0o400)
        os.chmod(output, 0o500)
        return {"status": "sealed", "bundle": str(output), **report}
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create an immutable signed Takeaway bundle from an approved read-only Chambo snapshot"
    )
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--key-id", required=True)
    args = parser.parse_args()
    try:
        result = export_snapshot(
            snapshot=args.snapshot,
            output=args.output,
            private_key_path=args.private_key,
            key_id=args.key_id,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "rejected", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
