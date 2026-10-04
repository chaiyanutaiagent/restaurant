from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Sequence
import uuid
from urllib.parse import urlsplit

from app.config import resolve_takeaway_write_mode, settings
from app.database import active_takeaway_service_session_factory
from app.dependencies import TokenData
from app.services.takeaway_import_service import (
    TakeawayImportService,
    build_takeaway_cutover_preview,
)
from app.cli.validate_takeaway_import import load_json, safe_bundle_path, validate_bundle


COMPANY_ID = uuid.UUID("1b8a1818-44d6-4d5f-9d22-e5e17b23c081")
BRAND_ID = uuid.UUID("d6391cbe-ee53-4873-b95b-219c9bc23e7c")
BRANCH_ID = uuid.UUID("1f397253-0479-4970-8288-f72d6cde6d7e")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute the approved Ozone One Chambo import on UAT")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--user-id", type=uuid.UUID, required=True)
    parser.add_argument("--execution-key", required=True)
    parser.add_argument("--approval-reference", required=True)
    parser.add_argument("--backup-reference", required=True)
    parser.add_argument("--rollback-reference", required=True)
    parser.add_argument("--yes", action="store_true")
    return parser


def require_uat(args: argparse.Namespace) -> None:
    hostname = urlsplit(settings.saas_public_base_url).hostname or ""
    if not args.yes:
        raise RuntimeError("Pass --yes to execute the approved Chambo UAT import")
    if settings.environment != "development" or not hostname.startswith("uat-"):
        raise RuntimeError("This import is restricted to the uat-* development environment")
    if not settings.takeaway_feature_enabled or settings.takeaway_service_database != "takeaway":
        raise RuntimeError("The dedicated Takeaway UAT database is required")
    if resolve_takeaway_write_mode(
        legacy_uat_enabled=settings.takeaway_uat_transaction_writes_enabled,
        configured_mode=settings.takeaway_transaction_write_mode,
    ) != "hold":
        raise RuntimeError("Takeaway transaction writes must remain disabled during import")


def load_bundle(bundle: Path) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
    bundle = bundle.resolve()
    manifest = load_json(bundle / "manifest.json")
    mapping = load_json(bundle / "mapping.json")
    records: list[dict[str, object]] = []
    for entry in manifest.get("files", []):
        if not isinstance(entry, dict) or entry.get("media_type") != "application/x-ndjson":
            continue
        relative = entry.get("path")
        if not isinstance(relative, str):
            raise RuntimeError("Manifest file path is missing")
        with safe_bundle_path(bundle, relative).open(encoding="utf-8") as source:
            records.extend(json.loads(line) for line in source if line.strip())
    return manifest, mapping, records


def require_ozone_one_mapping(mapping: dict[str, object]) -> None:
    if mapping.get("company", {}).get("target_id") != str(COMPANY_ID):
        raise RuntimeError("Unexpected target Company")
    if mapping.get("brand", {}).get("target_id") != str(BRAND_ID):
        raise RuntimeError("Unexpected target Brand")
    branches = mapping.get("branches")
    if not isinstance(branches, list) or len(branches) != 1 or not isinstance(branches[0], dict):
        raise RuntimeError("Exactly one Ozone One branch mapping is required")
    if branches[0].get("target_id") != str(BRANCH_ID) or branches[0].get("target_code") != "BKK-01":
        raise RuntimeError("The target must be Chambo BKK-01 / Ozone One")


async def run(args: argparse.Namespace) -> dict[str, Any]:
    require_uat(args)
    trusted_keys = {args.key_id: args.public_key.read_text(encoding="utf-8")}
    validation = validate_bundle(args.bundle, trusted_keys)
    if validation["status"] != "ok":
        raise RuntimeError("Signed bundle validation failed")
    manifest, mapping, records = load_bundle(args.bundle)
    require_ozone_one_mapping(mapping)
    preview = build_takeaway_cutover_preview(
        manifest=manifest,
        mapping=mapping,
        records=records,
        expected_company_id=COMPANY_ID,
        expected_brand_id=BRAND_ID,
        trusted_public_keys=trusted_keys,
    )
    if not preview["ready"]:
        raise RuntimeError(f"Cutover preview has blockers: {preview['blockers']}")
    current = TokenData(
        user_id=args.user_id,
        company_id=COMPANY_ID,
        branch_id=BRANCH_ID,
        brand_id=BRAND_ID,
        business_type="takeaway",
        target_database="takeaway",
        permissions=["takeaway.import.dry_run", "takeaway.import.apply"],
    )
    async with active_takeaway_service_session_factory()() as db:
        service = TakeawayImportService(db, current)
        cutover, first_replayed = await service.execute_approved_cutover(
            manifest=manifest,
            mapping=mapping,
            records=records,
            trusted_public_keys=trusted_keys,
            preview_digest=str(preview["preview_digest"]),
            execution_key=args.execution_key,
            approval_reference=args.approval_reference,
            backup_reference=args.backup_reference,
            rollback_reference=args.rollback_reference,
        )
        replay, second_replayed = await service.execute_approved_cutover(
            manifest=manifest,
            mapping=mapping,
            records=records,
            trusted_public_keys=trusted_keys,
            preview_digest=str(preview["preview_digest"]),
            execution_key=args.execution_key,
            approval_reference=args.approval_reference,
            backup_reference=args.backup_reference,
            rollback_reference=args.rollback_reference,
        )
    reconciliation = cutover.reconciliation
    if reconciliation.get("status") != "matched" or first_replayed or not second_replayed:
        raise RuntimeError("Import reconciliation or idempotent replay failed")
    return {
        "status": "completed",
        "cutover_run_id": str(cutover.id),
        "batch_id": str(cutover.batch_id),
        "source_snapshot": cutover.source_snapshot,
        "preview_digest": cutover.preview_digest,
        "reconciliation": reconciliation,
        "idempotent_replay": second_replayed,
        "replay_run_id": str(replay.id),
        "takeaway_transactions": "hold",
        "production_activated": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = asyncio.run(run(args))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
