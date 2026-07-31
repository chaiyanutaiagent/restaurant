from __future__ import annotations

import argparse
import asyncio
import json
from typing import Sequence

from app.database import PlatformSessionLocal
from app.services.platform_reference_projection import (
    ProjectionBatchResult,
    process_projection_batch,
    seed_snapshot_events,
    verify_projection_parity,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Project Platform ownership references into the Restaurant database.",
    )
    parser.add_argument(
        "--seed-snapshot",
        action="store_true",
        help="enqueue deterministic events for the current Platform reference snapshot",
    )
    process_group = parser.add_mutually_exclusive_group()
    process_group.add_argument(
        "--once",
        action="store_true",
        help="process at most one batch (the default when no action is selected)",
    )
    process_group.add_argument(
        "--drain",
        action="store_true",
        help="process batches until no currently available event remains",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="verify Platform-authoritative fields after processing",
    )
    parser.add_argument("--batch-size", type=int, default=100)
    return parser


async def run(args: argparse.Namespace) -> int:
    if args.batch_size < 1 or args.batch_size > 1000:
        raise ValueError("--batch-size must be between 1 and 1000")

    output: dict[str, object] = {}
    if args.seed_snapshot:
        async with PlatformSessionLocal() as session:
            output["seeded_events"] = await seed_snapshot_events(session)
            await session.commit()

    should_process = args.once or args.drain or not (args.seed_snapshot or args.verify)
    totals = ProjectionBatchResult()
    if should_process:
        while True:
            batch = await process_projection_batch(limit=args.batch_size)
            totals = ProjectionBatchResult(
                claimed=totals.claimed + batch.claimed,
                applied=totals.applied + batch.applied,
                replayed=totals.replayed + batch.replayed,
                failed=totals.failed + batch.failed,
            )
            if not args.drain or batch.claimed == 0 or batch.failed > 0:
                break
        output["projection"] = {
            "claimed": totals.claimed,
            "applied": totals.applied,
            "replayed": totals.replayed,
            "failed": totals.failed,
        }

    parity_failed = False
    if args.verify:
        parity = await verify_projection_parity()
        output["parity"] = [
            {
                "aggregate_type": report.aggregate_type,
                "source_count": report.source_count,
                "target_count": report.target_count,
                "mismatch_count": len(report.mismatched_ids),
                "matches": report.matches,
            }
            for report in parity
        ]
        parity_failed = any(not report.matches for report in parity)

    print(json.dumps(output, indent=2, sort_keys=True))
    return 1 if totals.failed or parity_failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())

