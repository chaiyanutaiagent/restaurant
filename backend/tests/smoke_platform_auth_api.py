from __future__ import annotations

import os

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.main import app
from app.models.audit import AuditLog
from app.models.platform import PlatformOperator, PlatformSession
from app.utils.platform_security import totp_code
from app.utils.security import hash_password


DATABASE_PREFIX = "restaurant_saas_auth_"
PLATFORM_USERNAME = "saas.auth.owner"
PLATFORM_PASSWORD = "SaaS-Auth-Owner-Password!"
NEXT_PASSWORD = "SaaS-Auth-Owner-Password-Next!"


def expect(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    if expected == 204:
        return None
    if expected >= 400:
        return response.json()
    return response.json()["data"]


async def prepare_operator() -> None:
    configured_database = os.environ.get("SAAS_AUTH_DATABASE_NAME", "")
    if not configured_database.startswith(DATABASE_PREFIX):
        raise RuntimeError("SaaS auth smoke refuses to write a non-isolated database")
    async with AsyncSessionLocal() as db:
        actual_database = await db.scalar(func.current_database())
        if actual_database != configured_database:
            raise RuntimeError(
                f"SaaS auth database mismatch: {actual_database} != {configured_database}"
            )
        db.add(
            PlatformOperator(
                username=PLATFORM_USERNAME,
                display_name="SaaS Auth Platform Owner",
                hashed_password=hash_password(PLATFORM_PASSWORD),
                is_active=True,
                is_superuser=True,
            )
        )
        await db.commit()


async def verify_evidence() -> None:
    async with AsyncSessionLocal() as db:
        operator = await db.scalar(
            select(PlatformOperator).where(PlatformOperator.username == PLATFORM_USERNAME)
        )
        if operator is None:
            raise RuntimeError("Platform operator MFA/password evidence is missing")
        sessions = list(
            await db.scalars(
                select(PlatformSession).where(PlatformSession.operator_id == operator.id)
            )
        )
        actions = set(
            await db.scalars(
                select(AuditLog.action).where(AuditLog.user_id == operator.id)
            )
        )
        if not operator.mfa_enabled or operator.credential_version != 2:
            raise RuntimeError("Platform operator MFA/password evidence is incomplete")
        if not sessions or any(not row.refresh_token_hash or len(row.refresh_token_hash) != 64 for row in sessions):
            raise RuntimeError("Platform session hash evidence is incomplete")
        required_actions = {
            "platform.operator.login",
            "platform.operator.mfa.enable",
            "platform.operator.password.change",
        }
        if not required_actions.issubset(actions):
            raise RuntimeError(f"Platform auth audit evidence is incomplete: {actions}")


def main() -> None:
    with TestClient(app) as client:
        client.portal.call(prepare_operator)
        login_response = client.post(
            "/api/v1/platform/auth/login",
            json={"username": PLATFORM_USERNAME, "password": PLATFORM_PASSWORD},
        )
        session = expect(login_response, 200, "Initial Platform login")
        cookie = login_response.headers.get("set-cookie", "")
        if "HttpOnly" not in cookie or "SameSite=strict" not in cookie:
            raise RuntimeError(f"Platform refresh cookie flags are incomplete: {cookie}")
        headers = {"Authorization": f"Bearer {session['access_token']}"}

        sessions = expect(
            client.get("/api/v1/platform/auth/sessions", headers=headers),
            200,
            "List Platform sessions",
        )
        if len(sessions) != 1 or not sessions[0]["current"]:
            raise RuntimeError("Current Platform session was not listed")

        refreshed = expect(
            client.post(
                "/api/v1/platform/auth/refresh",
                headers={"X-Platform-CSRF": session["csrf_token"]},
            ),
            200,
            "Rotate Platform refresh credential",
        )
        headers = {"Authorization": f"Bearer {refreshed['access_token']}"}
        expect(
            client.post(
                "/api/v1/platform/auth/refresh",
                headers={"X-Platform-CSRF": session["csrf_token"]},
            ),
            403,
            "Reject stale Platform CSRF credential",
        )

        setup = expect(
            client.post("/api/v1/platform/auth/mfa/setup", headers=headers),
            200,
            "Start Platform MFA setup",
        )
        confirmed = expect(
            client.post(
                "/api/v1/platform/auth/mfa/confirm",
                headers=headers,
                json={"code": totp_code(setup["secret"])},
            ),
            200,
            "Confirm Platform MFA",
        )
        recovery_code = confirmed["recovery_codes"][0]
        password_change_code = confirmed["recovery_codes"][1]
        next_login_code = confirmed["recovery_codes"][2]

        expect(
            client.post("/api/v1/platform/auth/logout", headers=headers),
            204,
            "Logout Platform session",
        )
        expect(
            client.get("/api/v1/platform/dashboard", headers=headers),
            401,
            "Reject logged-out Platform access token",
        )
        expect(
            client.post(
                "/api/v1/platform/auth/login",
                json={"username": PLATFORM_USERNAME, "password": PLATFORM_PASSWORD},
            ),
            428,
            "Require MFA at Platform login",
        )
        recovered = expect(
            client.post(
                "/api/v1/platform/auth/login",
                json={
                    "username": PLATFORM_USERNAME,
                    "password": PLATFORM_PASSWORD,
                    "mfa_code": recovery_code,
                },
            ),
            200,
            "Use Platform recovery code",
        )
        recovered_headers = {"Authorization": f"Bearer {recovered['access_token']}"}
        expect(
            client.post(
                "/api/v1/platform/auth/password",
                headers=recovered_headers,
                json={
                    "current_password": PLATFORM_PASSWORD,
                    "new_password": NEXT_PASSWORD,
                    "mfa_code": password_change_code,
                },
            ),
            204,
            "Change Platform password",
        )
        expect(
            client.get("/api/v1/platform/dashboard", headers=recovered_headers),
            401,
            "Reject Platform session after password change",
        )
        expect(
            client.post(
                "/api/v1/platform/auth/login",
                json={
                    "username": PLATFORM_USERNAME,
                    "password": NEXT_PASSWORD,
                    "mfa_code": recovery_code,
                },
            ),
            401,
            "Reject consumed Platform recovery code",
        )
        expect(
            client.post(
                "/api/v1/platform/auth/login",
                json={
                    "username": PLATFORM_USERNAME,
                    "password": NEXT_PASSWORD,
                    "mfa_code": next_login_code,
                },
            ),
            200,
            "Login after Platform password change",
        )
        client.portal.call(verify_evidence)

    print("SaaS Platform auth API smoke passed")


if __name__ == "__main__":
    main()
