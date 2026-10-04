from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.database import active_identity_session_factory
from app.services.platform_operations_service import (
    PlatformOperationsService,
    resilience_evidence_to_import,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture sanitized Platform operations evidence for a scheduler"
    )
    parser.add_argument(
        "--evidence-file",
        help="Resilience monitor JSON to sanitize and import; omit for a runtime capture",
    )
    return parser.parse_args()


async def run(evidence_file: str | None) -> dict:
    session_factory = active_identity_session_factory()
    async with session_factory() as db:
        service = PlatformOperationsService(db, operator_id=None)
        if evidence_file:
            payload = json.loads(Path(evidence_file).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Operational evidence must be a JSON object")
            row = await service.import_evidence(resilience_evidence_to_import(payload))
        else:
            row = await service.capture_runtime(scheduled=True)
        return row.model_dump(mode="json")


def main() -> None:
    args = parse_args()
    result = asyncio.run(run(args.evidence_file))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
