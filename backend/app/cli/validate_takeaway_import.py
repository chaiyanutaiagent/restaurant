from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from app.services.takeaway_import_service import (
    validate_takeaway_import_package,
    verify_takeaway_manifest_seal,
)


def digest_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def safe_bundle_path(bundle: Path, relative: str) -> Path:
    candidate = (bundle / relative).resolve()
    try:
        candidate.relative_to(bundle)
    except ValueError as exc:
        raise ValueError(f"Bundle path escapes its root: {relative}") from exc
    return candidate


def load_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return value


def validate_bundle(
    bundle: Path, trusted_public_keys: dict[str, str] | None = None
) -> dict[str, object]:
    bundle = bundle.resolve()
    manifest_path = bundle / "manifest.json"
    mapping_path = bundle / "mapping.json"
    manifest = load_json(manifest_path)
    mapping = load_json(mapping_path)
    findings: list[dict[str, object]] = []
    if trusted_public_keys is not None:
        verified, seal_status = verify_takeaway_manifest_seal(
            manifest, trusted_public_keys
        )
        if not verified:
            findings.append({"code": seal_status, "path": "manifest.seal"})

    mapping_spec = manifest.get("mapping")
    if isinstance(mapping_spec, dict):
        if mapping_spec.get("path") != "mapping.json":
            findings.append({"code": "mapping_path_mismatch", "path": "manifest.mapping.path"})
        if mapping_spec.get("sha256") != digest_file(mapping_path):
            findings.append({"code": "mapping_hash_mismatch", "path": "manifest.mapping.sha256"})
    else:
        findings.append({"code": "mapping_manifest_entry_required", "path": "manifest.mapping"})

    records: list[dict[str, object]] = []
    files = manifest.get("files")
    if not isinstance(files, list):
        findings.append({"code": "manifest_files_required", "path": "manifest.files"})
        files = []
    for index, specification in enumerate(files):
        path_key = f"manifest.files[{index}]"
        if not isinstance(specification, dict):
            findings.append({"code": "invalid_file_entry", "path": path_key})
            continue
        relative = specification.get("path")
        if not isinstance(relative, str):
            findings.append({"code": "file_path_required", "path": f"{path_key}.path"})
            continue
        try:
            path = safe_bundle_path(bundle, relative)
        except ValueError:
            findings.append({"code": "unsafe_file_path", "path": f"{path_key}.path"})
            continue
        if not path.is_file():
            findings.append({"code": "bundle_file_missing", "path": relative})
            continue
        if path.stat().st_size != specification.get("byte_size"):
            findings.append({"code": "file_byte_size_mismatch", "path": relative})
        if digest_file(path) != specification.get("sha256"):
            findings.append({"code": "file_hash_mismatch", "path": relative})
        record_count = 0
        if specification.get("media_type") == "application/x-ndjson":
            with path.open("r", encoding="utf-8") as source:
                for line_number, line in enumerate(source, start=1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        findings.append(
                            {
                                "code": "invalid_ndjson",
                                "path": f"{relative}:{line_number}",
                            }
                        )
                        continue
                    if not isinstance(record, dict):
                        findings.append(
                            {
                                "code": "ndjson_record_must_be_object",
                                "path": f"{relative}:{line_number}",
                            }
                        )
                        continue
                    records.append(record)
                    record_count += 1
        if record_count != specification.get("record_count"):
            findings.append(
                {
                    "code": "file_record_count_mismatch",
                    "path": relative,
                    "declared": specification.get("record_count"),
                    "actual": record_count,
                }
            )

    report = validate_takeaway_import_package(
        manifest=manifest,
        mapping=mapping,
        records=records,
    ).as_dict()
    report["bundle_path"] = str(bundle)
    report["bundle_findings"] = findings
    if findings:
        report["status"] = "rejected"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a sealed Takeaway import bundle")
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--public-key", type=Path)
    parser.add_argument("--key-id")
    args = parser.parse_args()
    try:
        trusted_keys = None
        if args.public_key or args.key_id:
            if not args.public_key or not args.key_id:
                raise ValueError("--public-key and --key-id must be provided together")
            trusted_keys = {args.key_id: args.public_key.read_text(encoding="utf-8")}
        report = validate_bundle(args.bundle, trusted_keys)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "rejected", "error": type(exc).__name__}, sort_keys=True))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
