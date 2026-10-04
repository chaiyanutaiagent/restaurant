from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import secrets
import uuid
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from sqlalchemy import select, update

from app.config import settings
from app.database import PlatformSessionLocal
from app.models.audit import AuditLog
from app.models.auth import RefreshToken
from app.models.company import Company
from app.models.user import User
from app.services.auth_service import AuthService
from app.utils.security import hash_password


FIXTURE_SLUG = "qa-isolation-beta-uat"
FIXTURE_USERNAME = "qa.isolation-beta"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare and verify a second synthetic UAT tenant for signed A/B isolation checks.",
    )
    parser.add_argument("--primary-company-id", type=uuid.UUID, required=True)
    parser.add_argument("--primary-username", required=True)
    parser.add_argument("--base-url", default="http://nginx")
    parser.add_argument("--host", default="uat-pos.foodchainservice.com")
    parser.add_argument("--yes", action="store_true")
    return parser


def require_bounded_qa_uat(args: argparse.Namespace) -> None:
    public_url = urlsplit(settings.saas_public_base_url)
    if not args.yes:
        raise RuntimeError("Pass --yes to prepare the persistent UAT isolation fixture")
    if (
        settings.environment != "development"
        or public_url.scheme != "https"
        or public_url.hostname is None
        or not public_url.hostname.startswith("uat-")
    ):
        raise RuntimeError("Tenant isolation fixture is restricted to HTTPS uat-* development")
    if settings.identity_database != "platform_core":
        raise RuntimeError("Tenant isolation fixture requires Platform identity")
    if not settings.qa_access_mode_enabled or settings.uat_auth_bypass_enabled:
        raise RuntimeError("Tenant isolation fixture requires QA mode with legacy auth bypass disabled")
    if settings.qa_access_company_id != args.primary_company_id:
        raise RuntimeError("Primary tenant must match QA_ACCESS_COMPANY_ID")
    if args.host.strip().lower() != public_url.hostname.lower():
        raise RuntimeError("Isolation smoke Host must match SAAS_PUBLIC_BASE_URL")
    if urlsplit(args.base_url).scheme not in {"http", "https"}:
        raise RuntimeError("Isolation smoke base URL must use HTTP or HTTPS")


def _request(
    base_url: str,
    host: str,
    path: str,
    token: str,
    *,
    company_header: uuid.UUID | None = None,
) -> tuple[int, dict[str, object]]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Host": host,
        "X-Forwarded-Proto": "https",
    }
    if company_header is not None:
        headers["X-Company-ID"] = str(company_header)
    request = Request(f"{base_url.rstrip('/')}{path}", headers=headers)
    try:
        with urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


async def prepare_and_verify(args: argparse.Namespace) -> dict[str, object]:
    require_bounded_qa_uat(args)
    async with PlatformSessionLocal() as db:
        primary_company = await db.get(Company, args.primary_company_id)
        primary_user = await db.scalar(
            select(User).where(
                User.company_id == args.primary_company_id,
                User.username == args.primary_username.strip().lower(),
                User.is_superuser.is_(True),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        if primary_company is None or not primary_company.is_active or primary_user is None:
            raise RuntimeError("Active primary QA tenant and superuser were not found")

        fixture_company = await db.scalar(
            select(Company).where(Company.business_slug == FIXTURE_SLUG)
        )
        created_company = fixture_company is None
        if fixture_company is None:
            fixture_company = Company(
                name="QA Isolation Beta UAT",
                business_slug=FIXTURE_SLUG,
                is_active=True,
            )
            db.add(fixture_company)
            await db.flush()
        else:
            fixture_company.name = "QA Isolation Beta UAT"
            fixture_company.is_active = True
        if fixture_company.id == primary_company.id:
            raise RuntimeError("Isolation fixture must be a different Company")

        fixture_user = await db.scalar(
            select(User).where(
                User.company_id == fixture_company.id,
                User.username == FIXTURE_USERNAME,
            )
        )
        now = datetime.now(timezone.utc)
        created_user = fixture_user is None
        if fixture_user is None:
            fixture_user = User(
                company_id=fixture_company.id,
                username=FIXTURE_USERNAME,
                display_name="QA Isolation Beta",
                hashed_password=hash_password(secrets.token_urlsafe(48)),
                is_active=True,
                is_superuser=True,
                password_changed_at=now,
            )
            db.add(fixture_user)
            await db.flush()
        else:
            fixture_user.display_name = "QA Isolation Beta"
            fixture_user.is_active = True
            fixture_user.is_superuser = True
            fixture_user.deleted_at = None
            fixture_user.credential_version += 1
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == fixture_user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        db.add(
            AuditLog(
                company_id=fixture_company.id,
                branch_id=None,
                user_id=fixture_user.id,
                action="uat.qa.tenant_isolation.prepare",
                resource="Company",
                resource_id=str(fixture_company.id),
                new_value={
                    "fixture": "tenant_b",
                    "created_company": created_company,
                    "created_user": created_user,
                    "primary_company_id": str(primary_company.id),
                },
            )
        )
        auth = AuthService(db, emit_reference_events=True)
        primary_token, _ = await auth.create_session(
            user=primary_user,
            branch_id=None,
            station_key=None,
            ip_address="127.0.0.1",
            user_agent="qa-tenant-isolation",
            qa_persona="tenant_a_isolation",
        )
        fixture_token, _ = await auth.create_session(
            user=fixture_user,
            branch_id=None,
            station_key=None,
            ip_address="127.0.0.1",
            user_agent="qa-tenant-isolation",
            qa_persona="tenant_b_isolation",
        )
        await db.commit()

    own_a, own_a_body = _request(
        args.base_url, args.host, f"/api/v1/system/users/{primary_user.id}", primary_token
    )
    own_b, own_b_body = _request(
        args.base_url, args.host, f"/api/v1/system/users/{fixture_user.id}", fixture_token
    )
    cross_a, _ = _request(
        args.base_url, args.host, f"/api/v1/system/users/{fixture_user.id}", primary_token
    )
    cross_b, _ = _request(
        args.base_url, args.host, f"/api/v1/system/users/{primary_user.id}", fixture_token
    )
    context_a, context_a_body = _request(
        args.base_url,
        args.host,
        "/api/v1/company/access",
        primary_token,
        company_header=fixture_company.id,
    )
    context_b, context_b_body = _request(
        args.base_url,
        args.host,
        "/api/v1/company/access",
        fixture_token,
        company_header=primary_company.id,
    )
    observed_a = (context_a_body.get("data") or {}).get("company_id")
    observed_b = (context_b_body.get("data") or {}).get("company_id")
    if (own_a, own_b, cross_a, cross_b, context_a, context_b) != (200, 200, 404, 404, 200, 200):
        raise RuntimeError(
            "Tenant isolation status mismatch: "
            f"own_a={own_a} own_b={own_b} cross_a={cross_a} cross_b={cross_b} "
            f"context_a={context_a} context_b={context_b}"
        )
    if own_a_body.get("data", {}).get("company_id") != str(primary_company.id):
        raise RuntimeError("Tenant A own-user response crossed the signed Company boundary")
    if own_b_body.get("data", {}).get("company_id") != str(fixture_company.id):
        raise RuntimeError("Tenant B own-user response crossed the signed Company boundary")
    if observed_a != str(primary_company.id) or observed_b != str(fixture_company.id):
        raise RuntimeError("Unsigned Company header overrode the signed tenant context")
    return {
        "tenant_a_company_id": str(primary_company.id),
        "tenant_b_company_id": str(fixture_company.id),
        "signed_sessions": True,
        "own_scope_status": [own_a, own_b],
        "cross_scope_status": [cross_a, cross_b],
        "spoofed_company_header_ignored": True,
        "credentials_emitted": False,
    }


async def main() -> int:
    result = await prepare_and_verify(build_parser().parse_args())
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
