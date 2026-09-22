from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import uuid
from urllib.parse import urlsplit

from sqlalchemy import select, update

from app.cli.prepare_qa_access_personas import PLATFORM_PERSONAS, TENANT_PERSONAS
from app.config import settings
from app.database import PlatformSessionLocal
from app.models.audit import AuditLog
from app.models.auth import RefreshToken
from app.models.platform import PlatformOperator, PlatformOperatorRoleAssignment, PlatformSession
from app.models.staff_assignment import StaffRoleAssignment
from app.models.user import User


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Revoke bounded QA personas after signed Final QA acceptance")
    parser.add_argument("--company-id", type=uuid.UUID, required=True)
    parser.add_argument("--tenant-actor-username", required=True)
    parser.add_argument("--platform-actor-username", required=True)
    parser.add_argument("--release-commit", required=True)
    parser.add_argument("--confirm-final-signoff", action="store_true")
    parser.add_argument("--yes", action="store_true")
    return parser


def require_final_uat(args: argparse.Namespace) -> None:
    public_url = urlsplit(settings.saas_public_base_url)
    if not args.yes or not args.confirm_final_signoff:
        raise RuntimeError("Final QA sign-off and --yes are required")
    if settings.environment != "development" or public_url.hostname is None or not public_url.hostname.startswith("uat-"):
        raise RuntimeError("QA cleanup is restricted to the HTTPS uat-* development environment")
    if settings.identity_database != "platform_core" or settings.qa_access_company_id != args.company_id:
        raise RuntimeError("QA cleanup Company/identity boundary does not match the configured UAT scope")
    if args.release_commit.strip() != settings.uat_release_commit.strip():
        raise RuntimeError("Release commit does not match immutable UAT identity")


async def cleanup(args: argparse.Namespace) -> dict[str, int | str]:
    require_final_uat(args)
    now = datetime.now(timezone.utc)
    tenant_names = [persona.username for persona in TENANT_PERSONAS if persona.preset_key is not None]
    platform_names = [persona.username for persona in PLATFORM_PERSONAS]
    async with PlatformSessionLocal() as db:
        tenant_actor = await db.scalar(select(User).where(User.company_id == args.company_id, User.username == args.tenant_actor_username.strip().lower(), User.is_superuser.is_(True), User.is_active.is_(True)))
        platform_actor = await db.scalar(select(PlatformOperator).where(PlatformOperator.username == args.platform_actor_username.strip().lower(), PlatformOperator.is_superuser.is_(True), PlatformOperator.is_active.is_(True)))
        if tenant_actor is None or platform_actor is None:
            raise RuntimeError("Active tenant and Platform superuser actors are required")
        tenant_users = list((await db.scalars(select(User).where(User.company_id == args.company_id, User.username.in_(tenant_names), User.deleted_at.is_(None)))).all())
        tenant_ids = [user.id for user in tenant_users]
        if tenant_ids:
            await db.execute(update(RefreshToken).where(RefreshToken.user_id.in_(tenant_ids), RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
            await db.execute(update(StaffRoleAssignment).where(StaffRoleAssignment.company_id == args.company_id, StaffRoleAssignment.user_id.in_(tenant_ids), StaffRoleAssignment.revoked_at.is_(None)).values(revoked_at=now, revoked_by=tenant_actor.id, revocation_reason="WP65 Final QA access cleanup"))
        for user in tenant_users:
            user.is_active = False
            user.credential_version += 1
            user.deactivated_at = now
            user.deactivated_by = tenant_actor.id
            user.deactivation_reason = "WP65 Final QA access cleanup"

        operators = list((await db.scalars(select(PlatformOperator).where(PlatformOperator.username.in_(platform_names)))).all())
        operator_ids = [operator.id for operator in operators]
        if operator_ids:
            await db.execute(update(PlatformSession).where(PlatformSession.operator_id.in_(operator_ids), PlatformSession.revoked_at.is_(None)).values(revoked_at=now, revocation_reason="WP65 Final QA access cleanup"))
            await db.execute(update(PlatformOperatorRoleAssignment).where(PlatformOperatorRoleAssignment.operator_id.in_(operator_ids), PlatformOperatorRoleAssignment.environment == "uat", PlatformOperatorRoleAssignment.revoked_at.is_(None)).values(revoked_at=now, revoked_by=platform_actor.id, revocation_reason="WP65 Final QA access cleanup"))
        for operator in operators:
            operator.is_active = False
            operator.credential_version += 1
            operator.deactivated_at = now
            operator.deactivated_by = platform_actor.id
            operator.deactivation_reason = "WP65 Final QA access cleanup"

        db.add(AuditLog(company_id=args.company_id, user_id=tenant_actor.id, action="uat.qa_access.cleanup", resource="Release", resource_id=args.release_commit, new_value={"tenant_personas_revoked": len(tenant_users), "platform_personas_revoked": len(operators), "final_signoff_confirmed": True}))
        await db.commit()
    return {"release_commit": args.release_commit, "tenant_personas_revoked": len(tenant_users), "platform_personas_revoked": len(operators), "credentials_emitted": 0}


async def main() -> int:
    result = await cleanup(build_parser().parse_args())
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
