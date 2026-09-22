from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import os
import uuid
from urllib.parse import urlsplit

from sqlalchemy import select, update

from app.config import settings
from app.database import PlatformSessionLocal
from app.models.audit import AuditLog
from app.models.auth import RefreshToken
from app.models.company import Company
from app.models.user import User
from app.utils.security import hash_password


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rotate one existing Tenant user password in the bounded UAT environment.",
    )
    parser.add_argument("--company-id", type=uuid.UUID, required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--password-env", default="UAT_ROTATE_PASSWORD")
    parser.add_argument("--yes", action="store_true")
    return parser


def require_bounded_uat(*, confirmed: bool, password: str) -> None:
    public_url = urlsplit(settings.saas_public_base_url)
    hostname = public_url.hostname or ""
    if not confirmed:
        raise RuntimeError("Pass --yes to rotate a persistent UAT credential")
    if (
        settings.environment != "development"
        or public_url.scheme != "https"
        or not hostname.startswith("uat-")
    ):
        raise RuntimeError("Credential rotation is restricted to the HTTPS uat-* development environment")
    if settings.identity_database != "platform_core":
        raise RuntimeError("Credential rotation requires Platform identity")
    if settings.uat_auth_bypass_enabled:
        raise RuntimeError("Disable UAT_AUTH_BYPASS_ENABLED before rotating a UAT credential")
    if len(password) < 12:
        raise RuntimeError("The replacement UAT password must contain at least 12 characters")


async def rotate_password(args: argparse.Namespace) -> User:
    password = os.environ.get(args.password_env, "")
    require_bounded_uat(confirmed=args.yes, password=password)
    username = args.username.strip().lower()
    reason = args.reason.strip()
    if not username or not reason:
        raise RuntimeError("Username and an auditable reason are required")

    async with PlatformSessionLocal() as db:
        company = await db.get(Company, args.company_id)
        if company is None or not company.is_active:
            raise RuntimeError("Active UAT Company was not found")
        user = await db.scalar(
            select(User)
            .where(
                User.company_id == company.id,
                User.username == username,
                User.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if user is None:
            raise RuntimeError("UAT user was not found")

        now = datetime.now(timezone.utc)
        user.hashed_password = hash_password(password)
        user.password_changed_at = now
        await db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        db.add(
            AuditLog(
                company_id=company.id,
                user_id=user.id,
                action="uat.user.password.rotate",
                resource="User",
                resource_id=str(user.id),
                new_value={"reason": reason, "refresh_tokens_revoked": True},
            )
        )
        await db.commit()
        await db.refresh(user)
        return user


async def main() -> None:
    args = build_parser().parse_args()
    user = await rotate_password(args)
    print(f"UAT user password rotated: {user.username} ({user.id})")


if __name__ == "__main__":
    asyncio.run(main())
