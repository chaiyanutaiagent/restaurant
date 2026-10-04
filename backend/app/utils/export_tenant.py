from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import uuid

from app.database import AsyncSessionLocal, PlatformSessionLocal, RestaurantSessionLocal
from app.services.tenant_export_service import TenantExportBoundary, build_tenant_export


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export one Company across configured database boundaries without credentials"
    )
    parser.add_argument("--company-id", required=True, type=uuid.UUID)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--output", help="Write JSON to this path instead of stdout")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> dict:
    async with (
        AsyncSessionLocal() as legacy_db,
        PlatformSessionLocal() as platform_db,
        RestaurantSessionLocal() as restaurant_db,
    ):
        return await build_tenant_export(
            args.company_id,
            [
                TenantExportBoundary("legacy", legacy_db),
                TenantExportBoundary("platform_core", platform_db),
                TenantExportBoundary("restaurant", restaurant_db),
            ],
            reason=args.reason,
            requested_by="operator-cli:all-configured-boundaries",
        )


def main() -> None:
    args = parse_args()
    artifact = asyncio.run(run(args))
    rendered = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(output)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
