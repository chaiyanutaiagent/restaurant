from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.api_integration import WebhookEndpoint
from app.utils.integration_security import INTEGRATION_SECRET_PREFIX, encrypt_integration_secret


async def run(*, apply: bool) -> None:
    if settings.environment == "production":
        raise RuntimeError("This bounded migration is disabled in Production")
    encrypted = 0
    disabled = 0
    already_safe = 0
    async with AsyncSessionLocal() as db:
        endpoints = list((await db.scalars(select(WebhookEndpoint))).all())
        for endpoint in endpoints:
            value = endpoint.secret_ciphertext
            if not value or value.startswith(INTEGRATION_SECRET_PREFIX):
                already_safe += 1
                continue
            if len(value.strip()) < 32:
                disabled += 1
                if apply:
                    endpoint.is_active = False
                continue
            encrypted += 1
            if apply:
                endpoint.secret_ciphertext = encrypt_integration_secret(value)
        if apply:
            await db.commit()
        else:
            await db.rollback()
    print({"mode": "apply" if apply else "dry_run", "encrypt": encrypted, "disable_short_secret": disabled, "already_safe": already_safe})


def main() -> None:
    parser = argparse.ArgumentParser(description="Encrypt legacy webhook secrets without printing secret material")
    parser.add_argument("--apply", action="store_true", help="Persist changes; default is dry-run")
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    main()
