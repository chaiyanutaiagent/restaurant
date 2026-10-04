from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.main import app
from app.models.auth import RefreshToken
from app.models.platform import PlatformOperator, SaasAccountCredential, SaasTenantMembership
from app.utils.security import hash_password


DATABASE_PREFIX = "restaurant_saas_membership_"
OWNER_EMAIL = "public-owner@example.com"
OWNER_USERNAME = "public.owner"
OLD_PASSWORD = "Public-Owner-Password!"
NEW_PASSWORD = "Public-Owner-New-Password!"
PLATFORM_USERNAME = "membership.platform.owner"
PLATFORM_PASSWORD = "Membership-Platform-Password!"


def expect(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    if expected >= 400:
        return response.json()
    return response.json()["data"]


async def prepare_platform_operator() -> None:
    configured_database = os.environ.get("SAAS_MEMBERSHIP_DATABASE_NAME", "")
    if not configured_database.startswith(DATABASE_PREFIX):
        raise RuntimeError("SaaS membership smoke refuses to write a non-isolated database")
    async with AsyncSessionLocal() as db:
        actual_database = await db.scalar(func.current_database())
        if actual_database != configured_database:
            raise RuntimeError(
                f"SaaS membership database mismatch: {actual_database} != {configured_database}"
            )
        db.add(
            PlatformOperator(
                username=PLATFORM_USERNAME,
                display_name="Membership Platform Owner",
                hashed_password=hash_password(PLATFORM_PASSWORD),
                is_active=True,
                is_superuser=True,
            )
        )
        await db.commit()


async def verify_database_evidence(company_id: str, raw_tokens: list[str]) -> None:
    company_uuid = uuid.UUID(company_id)
    async with AsyncSessionLocal() as db:
        membership = await db.scalar(
            select(SaasTenantMembership).where(
                SaasTenantMembership.company_id == company_uuid
            )
        )
        credentials = list(
            await db.scalars(
                select(SaasAccountCredential).where(
                    SaasAccountCredential.company_id == company_uuid
                )
            )
        )
        refresh_tokens = list(
            await db.scalars(
                select(RefreshToken).where(RefreshToken.company_id == company_uuid)
            )
        )
        if membership is None or membership.status != "trial_active":
            raise RuntimeError("Verified membership lifecycle was not persisted")
        if membership.email_verified_at is None or membership.trial_ends_at is None:
            raise RuntimeError("Trial timestamps are incomplete")
        if len(credentials) < 2 or any(len(row.token_hash) != 64 for row in credentials):
            raise RuntimeError("Hashed account credential evidence is incomplete")
        persisted = " ".join(row.token_hash for row in credentials)
        if any(raw_token in persisted for raw_token in raw_tokens):
            raise RuntimeError("A raw account credential was persisted")
        if not refresh_tokens or not any(row.revoked_at is not None for row in refresh_tokens):
            raise RuntimeError("Password reset did not revoke prior refresh sessions")


async def expire_trial(company_id: str) -> None:
    async with AsyncSessionLocal() as db:
        membership = await db.scalar(
            select(SaasTenantMembership).where(
                SaasTenantMembership.company_id == uuid.UUID(company_id)
            )
        )
        if membership is None:
            raise RuntimeError("Membership missing while testing trial expiry")
        membership.trial_ends_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()


def main() -> None:
    delivered: list[tuple[str, str, str]] = []

    async def capture_email(*, recipient: str, purpose: str, token: str) -> bool:
        delivered.append((recipient, purpose, token))
        return True

    with (
        patch(
            "app.routers.membership.deliver_membership_email",
            new=AsyncMock(side_effect=capture_email),
        ),
        patch(
            "app.routers.membership.check_public_rate_limit",
            new=AsyncMock(return_value=True),
        ),
        TestClient(app) as client,
    ):
        client.portal.call(prepare_platform_operator)
        signup_response = client.post(
            "/api/v1/membership/signup",
            json={
                "company_name": "Public Membership Tenant",
                "owner_display_name": "Public Owner",
                "owner_email": OWNER_EMAIL,
                "username": OWNER_USERNAME,
                "password": OLD_PASSWORD,
                "terms_accepted": True,
                "privacy_accepted": True,
            },
        )
        signup = expect(signup_response, 201, "Public SaaS signup")
        company_id = signup["company_id"]
        if len(delivered) != 1 or delivered[0][1] != "verify_email":
            raise RuntimeError("Signup verification delivery was not captured")
        verification_token = delivered[0][2]
        if verification_token in signup_response.text:
            raise RuntimeError("Signup API exposed the raw verification credential")

        expect(
            client.post(
                "/api/v1/auth/login",
                headers={"X-Company-ID": company_id},
                json={"username": OWNER_USERNAME, "password": OLD_PASSWORD},
            ),
            403,
            "Pending membership login block",
        )
        verified_response = client.post(
            "/api/v1/membership/verification/confirm",
            json={"token": verification_token},
        )
        verified = expect(verified_response, 200, "Email verification")
        if verified["membership"]["status"] != "trial_active":
            raise RuntimeError("Email verification did not activate the trial")
        if verification_token in verified_response.text:
            raise RuntimeError("Verification API echoed the raw credential")
        expect(
            client.post(
                "/api/v1/membership/verification/confirm",
                json={"token": verification_token},
            ),
            400,
            "Single-use verification credential",
        )

        login = expect(
            client.post(
                "/api/v1/auth/login",
                headers={"X-Company-ID": company_id},
                json={"username": OWNER_USERNAME, "password": OLD_PASSWORD},
            ),
            200,
            "Verified trial login",
        )
        expect(
            client.get(
                "/api/v1/membership/me",
                headers={"Authorization": f"Bearer {login['access_token']}"},
            ),
            200,
            "Authenticated owner membership",
        )

        unknown = client.post(
            "/api/v1/membership/password-reset/request",
            json={"email": "unknown@example.com"},
        )
        known = client.post(
            "/api/v1/membership/password-reset/request",
            json={"email": OWNER_EMAIL},
        )
        expect(unknown, 202, "Unknown forgot-password response")
        expect(known, 202, "Known forgot-password response")
        if unknown.json()["data"]["message"] != known.json()["data"]["message"]:
            raise RuntimeError("Forgot-password endpoint allows account enumeration")
        reset_token = delivered[-1][2]
        if delivered[-1][1] != "reset_password" or reset_token in known.text:
            raise RuntimeError("Reset credential delivery/exposure gate failed")

        reset_response = client.post(
            "/api/v1/membership/password-reset/confirm",
            json={"token": reset_token, "new_password": NEW_PASSWORD},
        )
        expect(reset_response, 200, "Password reset")
        if reset_token in reset_response.text:
            raise RuntimeError("Password-reset API echoed the raw credential")
        expect(
            client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": login["refresh_token"]},
            ),
            401,
            "Prior refresh session revocation",
        )
        expect(
            client.post(
                "/api/v1/auth/login",
                headers={"X-Company-ID": company_id},
                json={"username": OWNER_USERNAME, "password": OLD_PASSWORD},
            ),
            401,
            "Old password rejection",
        )
        new_login = expect(
            client.post(
                "/api/v1/auth/login",
                headers={"X-Company-ID": company_id},
                json={"username": OWNER_USERNAME, "password": NEW_PASSWORD},
            ),
            200,
            "New password login",
        )

        client.portal.call(expire_trial, company_id)
        expect(
            client.post(
                "/api/v1/auth/login",
                headers={"X-Company-ID": company_id},
                json={"username": OWNER_USERNAME, "password": NEW_PASSWORD},
            ),
            403,
            "Expired trial login block",
        )
        expect(
            client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": new_login["refresh_token"]},
            ),
            401,
            "Expired trial refresh block",
        )

        platform_login = expect(
            client.post(
                "/api/v1/platform/auth/login",
                json={"username": PLATFORM_USERNAME, "password": PLATFORM_PASSWORD},
            ),
            200,
            "Platform login",
        )
        company_detail = expect(
            client.get(
                f"/api/v1/platform/companies/{company_id}",
                headers={"Authorization": f"Bearer {platform_login['access_token']}"},
            ),
            200,
            "Protected Platform membership summary",
        )
        if company_detail["membership"]["owner_email"] != OWNER_EMAIL:
            raise RuntimeError("Platform membership summary is missing")
        if company_detail["membership"]["status"] != "trial_expired":
            raise RuntimeError("Platform membership summary did not expose effective expiry")

        client.portal.call(
            verify_database_evidence,
            company_id,
            [verification_token, reset_token],
        )

    print("SaaS membership API smoke passed")


if __name__ == "__main__":
    main()
