from __future__ import annotations

import argparse
import asyncio
import json
from typing import Sequence
import uuid

from app.services.retail_migration_service import (
    migrate_retail_operational_data,
    reconcile_retail_operational_data,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Selectively copy and reconcile Retail-owned data from Legacy.",
    )
    parser.add_argument("--company-id", type=uuid.UUID)
    parser.add_argument("--brand-id", action="append", default=[], type=uuid.UUID)
    parser.add_argument("--all-retail", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--batch-size", type=int, default=250)
    return parser


def validate_scope_args(args: argparse.Namespace) -> None:
    if args.all_retail and (args.company_id is not None or args.brand_id):
        raise ValueError("--all-retail cannot be combined with Company or Brand filters")
    if not args.all_retail and args.company_id is None and not args.brand_id:
        raise ValueError("Select --company-id/--brand-id, or use --all-retail --yes")
    if args.all_retail and not args.yes:
        raise ValueError("--all-retail requires --yes")


def _parity_payload(reports) -> dict[str, object]:
    return {
        report.table_name: {
            "source_count": report.source_count,
            "target_count": report.target_count,
            "source_digest": report.source_digest,
            "target_digest": report.target_digest,
            "matches": report.matches,
        }
        for report in reports
    }


async def run(args: argparse.Namespace) -> int:
    validate_scope_args(args)
    brand_ids = tuple(args.brand_id)
    if args.verify_only:
        scope, parity = await reconcile_retail_operational_data(
            company_id=args.company_id,
            brand_ids=brand_ids,
        )
        output = {
            "mode": "verify_only",
            "brand_ids": [str(value) for value in scope.references.brand_ids],
            "branch_ids": [str(value) for value in scope.references.branch_ids],
            "tables": _parity_payload(parity),
        }
    else:
        result = await migrate_retail_operational_data(
            company_id=args.company_id,
            brand_ids=brand_ids,
            batch_size=args.batch_size,
        )
        output = {
            "mode": "migrate_and_verify",
            "run_id": str(result.run_id),
            "brand_ids": [str(value) for value in result.scope.references.brand_ids],
            "branch_ids": [str(value) for value in result.scope.references.branch_ids],
            "tables": _parity_payload(result.table_parity),
        }
    failed = any(not table["matches"] for table in output["tables"].values())
    print(json.dumps(output, indent=2, sort_keys=True))
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
