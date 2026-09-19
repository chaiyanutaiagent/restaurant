"""Ephemeral role/permission smoke checks executed inside the UAT backend.

This script signs short-lived access tokens for the configured UAT superuser
with deliberately restricted claims. It does not create users, roles, sessions,
or operational documents, and it never prints a token or secret.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import json
import sys
import urllib.error
import urllib.request
import uuid
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.business_context import target_database_for
from app.database import active_identity_session_factory
from app.models.branch import Branch
from app.models.company import Company
from app.models.restaurant import Brand, BrandBranch
from app.models.user import User
from app.utils.security import create_access_token


API_BASE_URL = "http://127.0.0.1:8000"


class SmokeFailure(RuntimeError):
    pass


def request_json(
    path: str,
    token: str,
    *,
    expected_status: int = 200,
) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{API_BASE_URL}{path}",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "foodchainservice-uat-role-smoke/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = response.status
            raw = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        raw = error.read()
    if status != expected_status:
        raise SmokeFailure(f"{path} returned HTTP {status}, expected {expected_status}")
    return json.loads(raw.decode("utf-8")) if raw else {}


async def load_identity() -> tuple[User, Company, Branch, Brand]:
    if settings.uat_auth_bypass_company_id is None or settings.uat_auth_bypass_username is None:
        raise SmokeFailure("guarded UAT identity is not configured")
    session_factory = active_identity_session_factory()
    async with session_factory() as db:
        user = await db.scalar(
            select(User).where(
                User.company_id == settings.uat_auth_bypass_company_id,
                User.username == settings.uat_auth_bypass_username,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        company = await db.get(Company, settings.uat_auth_bypass_company_id)
        row = (
            await db.execute(
                select(Branch, Brand)
                .join(BrandBranch, BrandBranch.branch_id == Branch.id)
                .join(Brand, Brand.id == BrandBranch.brand_id)
                .where(
                    Branch.company_id == settings.uat_auth_bypass_company_id,
                    Branch.is_active.is_(True),
                    Branch.deleted_at.is_(None),
                    BrandBranch.is_active.is_(True),
                    Brand.is_active.is_(True),
                )
                .order_by(Branch.created_at.asc())
                .limit(1)
            )
        ).one_or_none()
        if user is None or company is None or row is None:
            raise SmokeFailure("UAT Company, user, or mapped branch is unavailable")
        branch, brand = row
        # Detach simple model state before closing the read-only session.
        for model in (user, company, branch, brand):
            db.expunge(model)
        return user, company, branch, brand


def token_for(
    user: User,
    company: Company,
    branch: Branch,
    brand: Brand,
    *,
    permissions: list[str],
    scope_types: list[str],
) -> str:
    return create_access_token(
        subject=str(user.id),
        company_id=str(company.id),
        branch_id=str(branch.id),
        permissions=permissions,
        expires_delta=timedelta(minutes=2),
        brand_id=str(brand.id),
        business_type=brand.business_type,
        target_database=target_database_for(brand.business_type),
        scope_types=scope_types,
        company_credential_version=company.credential_version,
    )


async def main() -> int:
    user, company, branch, brand = await load_identity()
    cases = (
        ("Company Owner", ["system.company.view"], ["company"], "/company"),
        ("Restaurant Service", ["fb.menu.view"], ["branch"], "/restaurant"),
        ("Retail Cashier", ["pos.sale.view"], ["branch"], "/pos"),
        ("Back Office", ["inventory.stock.view"], ["branch"], "/admin"),
        ("No Access", [], ["branch"], "/403"),
    )
    for label, permissions, scopes, expected_route in cases:
        token = token_for(
            user,
            company,
            branch,
            brand,
            permissions=permissions,
            scope_types=scopes,
        )
        access = request_json("/api/v1/company/access", token).get("data", {})
        actual_route = access.get("default_route")
        if actual_route != expected_route:
            raise SmokeFailure(
                f"{label} landed on {actual_route!r}, expected {expected_route!r}"
            )

    denied_token = token_for(
        user,
        company,
        branch,
        brand,
        permissions=["inventory.stock.view"],
        scope_types=["branch"],
    )
    request_json("/api/v1/company/operational-status", denied_token, expected_status=403)

    allowed_token = token_for(
        user,
        company,
        branch,
        brand,
        permissions=["system.device.view"],
        scope_types=["branch"],
    )
    request_json("/api/v1/company/operational-status", allowed_token)

    print("PASS: 5 role-based landing cases")
    print("PASS: permission denied and permission allowed boundaries")
    print(f"Context: {company.name} / {brand.name} / {branch.name}")
    print("Mutation count: 0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except SmokeFailure as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
