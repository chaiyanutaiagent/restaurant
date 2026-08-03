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
        description="Break-glass reset for an existing Platform Owner password.",
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument(
        "--disable-mfa",
        action="store_true",
        help="Also clear MFA when all authenticators and recovery codes are lost.",
    )
    parser.add_argument(
        "--password-env",
        default="PLATFORM_OPERATOR_PASSWORD",
        help="Environment variable containing the new password; prompts when unset.",
    )
    return parser


async def reset_password(
    *,
    username: str,
    password: str,
    reason: str,
    disable_mfa: bool = False,
) -> PlatformOperator:
    normalized_username = username.strip().lower()
    normalized_reason = reason.strip()
    if len(password) < 12:
        raise ValueError("Platform operator password must contain at least 12 characters")
    if not normalized_username or not normalized_reason:
        raise ValueError("Username and an auditable reason are required")

    session_factory = active_identity_session_factory()
    async with session_factory() as db:
        operator = await db.scalar(
            select(PlatformOperator)
            .where(PlatformOperator.username == normalized_username)
            .with_for_update()
        )
        if operator is None:
            raise ValueError("Platform operator was not found")
        now = datetime.now(timezone.utc)
        operator.hashed_password = hash_password(password)
        operator.password_changed_at = now
        operator.credential_version += 1
        operator.failed_login_attempts = 0
        operator.locked_until = None
        if disable_mfa:
            operator.mfa_secret_ciphertext = None
            operator.mfa_enabled_at = None
            operator.mfa_last_verified_step = None
            operator.mfa_recovery_code_hashes = []
        await db.execute(
            update(PlatformSession)
            .where(
                PlatformSession.operator_id == operator.id,
                PlatformSession.revoked_at.is_(None),
            )
            .values(revoked_at=now, revocation_reason="break-glass-password-reset")
        )
        db.add(
            AuditLog(
                company_id=None,
                branch_id=None,
                user_id=operator.id,
                action="platform.operator.password.break_glass_reset",
                resource="PlatformOperator",
                resource_id=str(operator.id),
                new_value={
                    "reason": normalized_reason,
                    "sessions_revoked": True,
                    "mfa_disabled": disable_mfa,
                },
            )
        )
        await db.commit()
        await db.refresh(operator)
        return operator


async def main() -> None:
    args = _parser().parse_args()
    password = os.environ.get(args.password_env)
    if password is None:
        password = getpass("New Platform Owner password: ")
        confirmation = getpass("Confirm password: ")
        if password != confirmation:
            raise ValueError("Passwords do not match")
    operator = await reset_password(
        username=args.username,
        password=password,
        reason=args.reason,
        disable_mfa=args.disable_mfa,
    )
    print(f"Platform Owner password reset: {operator.username} ({operator.id})")


if __name__ == "__main__":
    asyncio.run(main())
