from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from getpass import getpass
import os

from sqlalchemy import select, update

from app.database import active_identity_session_factory
from app.models.audit import AuditLog
from app.models.platform import PlatformOperator, PlatformSession
from app.utils.security import hash_password


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or reactivate a separate Platform Owner identity.",
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--email")
    parser.add_argument(
        "--reason",
        default="Platform operator bootstrap or reactivation",
    )
    parser.add_argument(
        "--password-env",
        default="PLATFORM_OPERATOR_PASSWORD",
        help="Environment variable containing the password; prompts when unset.",
    )
    return parser


async def create_operator(
    *,
    username: str,
    display_name: str,
    email: str | None,
    password: str,
    reason: str = "Platform operator bootstrap or reactivation",
) -> PlatformOperator:
    normalized_username = username.strip().lower()
    normalized_name = display_name.strip()
    normalized_email = email.strip().lower() if email and email.strip() else None
    if len(password) < 12:
        raise ValueError("Platform operator password must contain at least 12 characters")
    if not normalized_username or not normalized_name:
        raise ValueError("Username and display name are required")

    session_factory = active_identity_session_factory()
    async with session_factory() as db:
        operator = await db.scalar(
            select(PlatformOperator).where(PlatformOperator.username == normalized_username)
        )
        if operator is None:
            operator = PlatformOperator(
                username=normalized_username,
                email=normalized_email,
                display_name=normalized_name,
                hashed_password=hash_password(password),
                is_active=True,
                is_superuser=True,
            )
            db.add(operator)
        else:
            operator.email = normalized_email
            operator.display_name = normalized_name
            operator.hashed_password = hash_password(password)
            operator.is_active = True
            operator.is_superuser = True
            operator.credential_version += 1
            operator.failed_login_attempts = 0
            operator.locked_until = None
            operator.password_changed_at = datetime.now(timezone.utc)
            await db.execute(
                update(PlatformSession)
                .where(
                    PlatformSession.operator_id == operator.id,
                    PlatformSession.revoked_at.is_(None),
                )
                .values(
                    revoked_at=datetime.now(timezone.utc),
                    revocation_reason="operator-bootstrap-reset",
                )
            )
        await db.flush()
        db.add(
            AuditLog(
                company_id=None,
                branch_id=None,
                user_id=operator.id,
                action="platform.operator.bootstrap",
                resource="PlatformOperator",
                resource_id=str(operator.id),
                new_value={"reason": reason.strip(), "sessions_revoked": True},
            )
        )
        await db.commit()
        await db.refresh(operator)
        return operator


async def main() -> None:
    args = _parser().parse_args()
    password = os.environ.get(args.password_env)
    if password is None:
        password = getpass("Platform Owner password: ")
        confirmation = getpass("Confirm password: ")
        if password != confirmation:
            raise ValueError("Passwords do not match")
    operator = await create_operator(
        username=args.username,
        display_name=args.display_name,
        email=args.email,
        password=password,
        reason=args.reason,
    )
    print(f"Platform Owner ready: {operator.username} ({operator.id})")


if __name__ == "__main__":
    asyncio.run(main())
