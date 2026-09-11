from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from unittest.mock import AsyncMock, patch
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.main import app
from app.models.audit import AuditLog
from app.models.company import Company
from app.models.platform import PlatformOperator
from app.models.saas_privacy_support import SaasPrivacyRequest, SaasRetentionDecision, SaasSupportAccessGrant
from app.models.user import User
from app.utils.security import hash_password


DATABASE_PREFIXES = ("restaurant_saas_privacy_", "restaurant_saas_beta_")
PLATFORM_USERNAME = "privacy.platform.owner"
PLATFORM_PASSWORD = "Privacy-Platform-Password!"
SECOND_OPERATOR = "privacy.second.owner"
TENANTS = [
    ("privacy-one@example.com", "privacy.owner.one", "Privacy-Owner-One!", "Privacy Tenant One"),
    ("privacy-two@example.com", "privacy.owner.two", "Privacy-Owner-Two!", "Privacy Tenant Two"),
]


def expect(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}")
    if expected >= 400:
        return response.json()
    return response.json()["data"]


async def prepare_operators() -> None:
    configured = os.environ.get("SAAS_PRIVACY_DATABASE_NAME", "")
    if not configured.startswith(DATABASE_PREFIXES):
        raise RuntimeError("Privacy/support smoke refuses to write a non-isolated database")
    async with AsyncSessionLocal() as db:
        if await db.scalar(func.current_database()) != configured:
            raise RuntimeError("Privacy/support database mismatch")
        db.add_all([
            PlatformOperator(username=PLATFORM_USERNAME, display_name="Privacy Platform Owner", hashed_password=hash_password(PLATFORM_PASSWORD), is_active=True, is_superuser=True),
            PlatformOperator(username=SECOND_OPERATOR, display_name="Second Platform Owner", hashed_password=hash_password(PLATFORM_PASSWORD), is_active=True, is_superuser=True),
        ])
        await db.commit()


async def expire_grant(grant_id: str) -> None:
    async with AsyncSessionLocal() as db:
        row = await db.get(SaasSupportAccessGrant, uuid.UUID(grant_id))
        if row is None:
            raise RuntimeError("Support grant missing during expiry test")
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()


async def database_counts() -> tuple[int, int]:
    async with AsyncSessionLocal() as db:
        return (
            int(await db.scalar(select(func.count()).select_from(Company)) or 0),
            int(await db.scalar(select(func.count()).select_from(User)) or 0),
        )


async def verify_evidence(company_id: str, request_id: str, expected_company_count: int, expected_user_count: int) -> None:
    company_uuid = uuid.UUID(company_id)
    async with AsyncSessionLocal() as db:
        privacy = await db.get(SaasPrivacyRequest, uuid.UUID(request_id))
        retention = await db.scalar(select(SaasRetentionDecision).where(SaasRetentionDecision.privacy_request_id == uuid.UUID(request_id)))
        grants = list(await db.scalars(select(SaasSupportAccessGrant).where(SaasSupportAccessGrant.company_id == company_uuid)))
        audit_count = int(await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.company_id == company_uuid, AuditLog.action.like("%support.%"))) or 0)
        company_count = int(await db.scalar(select(func.count()).select_from(Company)) or 0)
        user_count = int(await db.scalar(select(func.count()).select_from(User)) or 0)
        if privacy is None or privacy.status != "fulfilled":
            raise RuntimeError("Privacy request lifecycle evidence is incomplete")
        if retention is None or retention.status != "approved" or retention.action != "anonymize":
            raise RuntimeError("Non-executing retention decision evidence is incomplete")
        if len(grants) != 2 or {grant.status for grant in grants} != {"revoked", "approved"}:
            raise RuntimeError("Support grant revoke/expiry evidence is incomplete")
        if audit_count < 7 or not any(grant.last_accessed_at for grant in grants):
            raise RuntimeError("Audited support access evidence is incomplete")
        if company_count != expected_company_count or user_count != expected_user_count:
            raise RuntimeError("Privacy workflow unexpectedly deleted Company/User data")


def main() -> None:
    verification_tokens: dict[str, str] = {}

    async def capture_email(*, recipient: str, purpose: str, token: str) -> bool:
        if purpose == "verify_email":
            verification_tokens[recipient] = token
        return True

    with (
        patch("app.routers.membership.deliver_membership_email", new=AsyncMock(side_effect=capture_email)),
        patch("app.routers.membership.check_public_rate_limit", new=AsyncMock(return_value=True)),
        TestClient(app) as client,
    ):
        client.portal.call(prepare_operators)
        tenant_sessions: list[tuple[str, dict[str, str]]] = []
        for email, username, password, company_name in TENANTS:
            signup = expect(client.post("/api/v1/membership/signup", json={"company_name": company_name, "owner_display_name": username, "owner_email": email, "username": username, "password": password, "terms_accepted": True, "privacy_accepted": True}), 201, f"Signup {username}")
            expect(client.post("/api/v1/membership/verification/confirm", json={"token": verification_tokens[email]}), 200, f"Verify {username}")
            login = expect(client.post("/api/v1/auth/login", headers={"X-Company-ID": signup["company_id"]}, json={"username": username, "password": password}), 200, f"Login {username}")
            tenant_sessions.append((signup["company_id"], {"Authorization": f"Bearer {login['access_token']}"}))
        company_one, tenant_one = tenant_sessions[0]
        company_two, tenant_two = tenant_sessions[1]
        company_count, user_count = client.portal.call(database_counts)

        privacy = expect(client.post("/api/v1/privacy-support/privacy-requests", headers=tenant_one, json={"request_type": "deletion", "description": "Please review account-level data for anonymization"}), 201, "Tenant privacy request")
        ticket = expect(client.post("/api/v1/privacy-support/tickets", headers=tenant_one, json={"category": "technical", "priority": "high", "subject": "Account status differs from billing", "initial_message": "Please inspect account-level aggregate state only"}), 201, "Tenant support ticket")
        if len(ticket["messages"]) != 1 or ticket["messages"][0]["sender_type"] != "tenant_owner":
            raise RuntimeError("Tenant ticket conversation was not initialized")
        if expect(client.get("/api/v1/privacy-support/privacy-requests", headers=tenant_two), 200, "Second tenant privacy isolation"):
            raise RuntimeError("Second tenant can list first tenant privacy request")
        if expect(client.get("/api/v1/privacy-support/tickets", headers=tenant_two), 200, "Second tenant ticket isolation"):
            raise RuntimeError("Second tenant can list first tenant ticket")
        expect(client.post(f"/api/v1/privacy-support/tickets/{ticket['id']}/messages", headers=tenant_two, json={"body": "cross tenant"}), 404, "Cross-tenant ticket message block")

        platform_login = expect(client.post("/api/v1/platform/auth/login", json={"username": PLATFORM_USERNAME, "password": PLATFORM_PASSWORD}), 200, "Platform privacy login")
        platform = {"Authorization": f"Bearer {platform_login['access_token']}"}
        expect(client.put(f"/api/v1/platform/privacy/requests/{privacy['id']}", headers=platform, json={"status": "in_review", "response_summary": None, "reason": "Authenticated account owner request accepted for review"}), 200, "Privacy review")
        retention = expect(client.post(f"/api/v1/platform/privacy/requests/{privacy['id']}/retention", headers=platform, json={"data_category": "account_identity", "action": "anonymize", "rationale": "Proposed only; execution requires a separately approved destructive scope", "retain_until": None, "reason": "Record non-executing retention intent"}), 201, "Retention proposal")
        expect(client.put(f"/api/v1/platform/privacy/retention/{retention['id']}", headers=platform, json={"status": "approved", "reason": "Decision recorded; no data execution authorized"}), 200, "Retention approval")
        expect(client.put(f"/api/v1/platform/privacy/requests/{privacy['id']}", headers=platform, json={"status": "fulfilled", "response_summary": "Account-level review completed and retention intent recorded; no automated deletion occurred", "reason": "Close tracked request"}), 200, "Privacy fulfillment")
        expect(client.post(f"/api/v1/platform/support/tickets/{ticket['id']}/messages", headers=platform, json={"body": "Please approve time-limited aggregate context access"}), 201, "Platform support message")
        access_payload = {"requested_scopes": ["account_state", "saas_controls", "billing_state"], "purpose": "Inspect aggregate account and SaaS lifecycle only", "duration_minutes": 30, "reason": "Tenant approval required before troubleshooting"}
        grant = expect(client.post(f"/api/v1/platform/support/tickets/{ticket['id']}/access", headers=platform, json=access_payload), 201, "Support access request")
        expect(client.get(f"/api/v1/platform/support/access/{grant['id']}/context", headers=platform), 403, "Pending grant context block")
        expect(client.post(f"/api/v1/privacy-support/access/{grant['id']}/decision", headers=tenant_two, json={"decision": "approved", "reason": "wrong tenant"}), 404, "Cross-tenant grant approval block")
        approved = expect(client.post(f"/api/v1/privacy-support/access/{grant['id']}/decision", headers=tenant_one, json={"decision": "approved", "reason": "Approve named aggregate scopes for this ticket"}), 200, "Tenant grant approval")
        if approved["expires_at"] is None:
            raise RuntimeError("Approved support grant has no expiry")
        second_login = expect(client.post("/api/v1/platform/auth/login", json={"username": SECOND_OPERATOR, "password": PLATFORM_PASSWORD}), 200, "Second operator login")
        expect(client.get(f"/api/v1/platform/support/access/{grant['id']}/context", headers={"Authorization": f"Bearer {second_login['access_token']}"}), 404, "Operator-bound grant block")
        context_response = client.get(f"/api/v1/platform/support/access/{grant['id']}/context", headers=platform)
        context = expect(context_response, 200, "Approved support context")
        if set(context["context"]) != {"account_state", "saas_controls", "billing_state"}:
            raise RuntimeError("Support context exceeded or missed approved scopes")
        forbidden = ("password", "token", "customer", "order", "employee", "secret", "postgresql://")
        serialized = json.dumps(context, sort_keys=True).lower()
        if any(marker in serialized for marker in forbidden):
            raise RuntimeError("Support context exposed a forbidden data marker")
        expect(client.post(f"/api/v1/privacy-support/access/{grant['id']}/revoke", headers=tenant_one, json={"reason": "Troubleshooting view completed"}), 200, "Tenant access revoke")
        expect(client.get(f"/api/v1/platform/support/access/{grant['id']}/context", headers=platform), 403, "Revoked grant context block")

        grant_two = expect(client.post(f"/api/v1/platform/support/tickets/{ticket['id']}/access", headers=platform, json=access_payload), 201, "Second expiring access request")
        expect(client.post(f"/api/v1/privacy-support/access/{grant_two['id']}/decision", headers=tenant_one, json={"decision": "approved", "reason": "Approve expiry test"}), 200, "Second grant approval")
        client.portal.call(expire_grant, grant_two["id"])
        expect(client.get(f"/api/v1/platform/support/access/{grant_two['id']}/context", headers=platform), 403, "Expired grant context block")
        expect(client.post("/api/v1/platform/impersonate", headers=platform, json={"company_id": company_one}), 404, "No impersonation route")

        client.portal.call(verify_evidence, company_one, privacy["id"], company_count, user_count)

    print("SaaS privacy and support API smoke passed")


if __name__ == "__main__":
    main()
