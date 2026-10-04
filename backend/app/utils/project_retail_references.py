from __future__ import annotations

import argparse
import asyncio
import json
from typing import Sequence
import uuid

from app.services.retail_reference_projector import (
    project_retail_reference_snapshot,
    verify_retail_reference_parity,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Project Platform-owned references into the Retail database.",
    )
    parser.add_argument("--company-id", type=uuid.UUID)
    parser.add_argument("--brand-id", action="append", default=[], type=uuid.UUID)
    parser.add_argument("--project", action="store_true")
    parser.add_argument("--verify", action="store_true")
    return parser


async def run(args: argparse.Namespace) -> int:
    should_project = args.project or not args.verify
    brand_ids = tuple(args.brand_id)
    output: dict[str, object] = {}
    if should_project:
        projection = await project_retail_reference_snapshot(
            company_id=args.company_id,
            brand_ids=brand_ids,
        )
        output["projection"] = {
            "scanned": projection.scanned,
            "applied": projection.applied,
            "unchanged": projection.unchanged,
        }
    parity_failed = False
    if args.verify:
        parity = await verify_retail_reference_parity(
            company_id=args.company_id,
            brand_ids=brand_ids,
        )
        output["parity"] = {
            aggregate_type: {
                "source_count": report[0],
                "target_count": report[1],
                "mismatch_count": len(report[2]),
                "matches": report[0] == report[1] and not report[2],
            }
            for aggregate_type, report in parity.items()
        }
        parity_failed = any(
            report[0] != report[1] or bool(report[2]) for report in parity.values()
        )
    print(json.dumps(output, indent=2, sort_keys=True))
    return 1 if parity_failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
