from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.main import app
from app.models.audit import AuditLog
from app.models.platform import PlatformOperator
from app.models.saas_billing import SaasBillingEvent, SaasInvoice, SaasSubscription
from app.utils.security import hash_password


DATABASE_PREFIX = "restaurant_saas_billing_"
OWNER_EMAIL = "billing-owner@example.com"
OWNER_USERNAME = "billing.owner"
OWNER_PASSWORD = "Billing-Owner-Password!"
PLATFORM_USERNAME = "billing.platform.owner"
PLATFORM_PASSWORD = "Billing-Platform-Password!"


def expect(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    if expected >= 400:
        return response.json()
    return response.json()["data"]


async def prepare_platform_operator() -> None:
    configured_database = os.environ.get("SAAS_BILLING_DATABASE_NAME", "")
    if not configured_database.startswith(DATABASE_PREFIX):
        raise RuntimeError("SaaS billing smoke refuses to write a non-isolated database")
    async with AsyncSessionLocal() as db:
        actual_database = await db.scalar(func.current_database())
        if actual_database != configured_database:
            raise RuntimeError(f"Billing database mismatch: {actual_database} != {configured_database}")
        db.add(
            PlatformOperator(
                username=PLATFORM_USERNAME,
                display_name="Billing Platform Owner",
                hashed_password=hash_password(PLATFORM_PASSWORD),
                is_active=True,
                is_superuser=True,
            )
        )
        await db.commit()


async def verify_database_evidence(company_id: str, invoice_id: str) -> None:
    company_uuid = uuid.UUID(company_id)
    async with AsyncSessionLocal() as db:
        subscription = await db.scalar(
            select(SaasSubscription).where(SaasSubscription.company_id == company_uuid)
        )
        invoice = await db.get(SaasInvoice, uuid.UUID(invoice_id))
        events = list(
            await db.scalars(
                select(SaasBillingEvent).where(SaasBillingEvent.company_id == company_uuid)
            )
        )
        company_audit_count = int(
            await db.scalar(
                select(func.count()).select_from(AuditLog).where(
                    AuditLog.company_id == company_uuid,
                    AuditLog.action.like("platform.billing.%"),
                )
            )
            or 0
        )
        total_audit_count = int(
            await db.scalar(
                select(func.count()).select_from(AuditLog).where(
                    AuditLog.action.like("platform.billing.%")
                )
            )
            or 0
        )
        if subscription is None or subscription.status != "active":
            raise RuntimeError("Active SaaS subscription evidence is missing")
        if invoice is None or invoice.status != "paid" or invoice.paid_satang != 10700:
            raise RuntimeError("Paid integer-satang invoice evidence is missing")
        if len(events) != 2 or any(len(row.payload_sha256) != 64 for row in events):
            raise RuntimeError("Normalized billing event idempotency evidence is incomplete")
        if company_audit_count < 4 or total_audit_count < 5:
            raise RuntimeError("Billing mutation audit evidence is incomplete")
        serialized = json.dumps(
            [{"key": row.event_key, "digest": row.payload_sha256} for row in events],
            sort_keys=True,
        )
        if "raw_payload" in serialized or "card" in serialized:
            raise RuntimeError("Raw provider payload was persisted")


def main() -> None:
    delivered: list[str] = []

    async def capture_email(*, recipient: str, purpose: str, token: str) -> bool:
        if recipient == OWNER_EMAIL and purpose == "verify_email":
            delivered.append(token)
        return True

    with (
        patch("app.routers.membership.deliver_membership_email", new=AsyncMock(side_effect=capture_email)),
        patch("app.routers.membership.check_public_rate_limit", new=AsyncMock(return_value=True)),
        TestClient(app) as client,
    ):
        client.portal.call(prepare_platform_operator)
        signup = expect(
            client.post(
                "/api/v1/membership/signup",
                json={
                    "company_name": "Billing Isolated Tenant",
                    "owner_display_name": "Billing Owner",
                    "owner_email": OWNER_EMAIL,
                    "username": OWNER_USERNAME,
                    "password": OWNER_PASSWORD,
                    "terms_accepted": True,
                    "privacy_accepted": True,
                },
            ),
            201,
            "Billing tenant signup",
        )
        company_id = signup["company_id"]
        if len(delivered) != 1:
            raise RuntimeError("Verification credential was not captured")
        expect(
            client.post("/api/v1/membership/verification/confirm", json={"token": delivered[0]}),
            200,
            "Billing tenant verification",
        )
        tenant_login = expect(
            client.post(
                "/api/v1/auth/login",
                headers={"X-Company-ID": company_id},
                json={"username": OWNER_USERNAME, "password": OWNER_PASSWORD},
            ),
            200,
            "Billing tenant login",
        )
        tenant_headers = {"Authorization": f"Bearer {tenant_login['access_token']}"}
        tenant_billing = expect(
            client.get("/api/v1/membership/billing", headers=tenant_headers),
            200,
            "Read-only tenant billing",
        )
        if tenant_billing["subscription"]["status"] != "trialing":
            raise RuntimeError("Verified tenant subscription is not trialing")
        if tenant_billing["provider"] != "unconfigured" or tenant_billing["collection_available"]:
            raise RuntimeError("Provider decision boundary is not closed")
        expect(
            client.get("/api/v1/platform/billing/overview", headers=tenant_headers),
            401,
            "Tenant token cannot enter Platform billing",
        )

        platform_login = expect(
            client.post(
                "/api/v1/platform/auth/login",
                json={"username": PLATFORM_USERNAME, "password": PLATFORM_PASSWORD},
            ),
            200,
            "Platform billing login",
        )
        headers = {"Authorization": f"Bearer {platform_login['access_token']}"}
        overview = expect(
            client.get("/api/v1/platform/billing/overview", headers=headers),
            200,
            "Platform billing overview",
        )
        if overview["provider"] != "unconfigured" or overview["live_charging_enabled"]:
            raise RuntimeError("Live collection unexpectedly enabled")
        starter = next(plan for plan in overview["plans"] if plan["code"] == "starter")
        starter["unit_amount_satang"] = 99000
        starter["is_public"] = True
        starter["reason"] = "Approve beta catalog price only"
        for key in ("id", "created_at", "updated_at"):
            starter.pop(key)
        expect(
            client.post("/api/v1/platform/billing/plans", headers=headers, json=starter),
            200,
            "Plan price update",
        )
        summary = expect(
            client.put(
                f"/api/v1/platform/companies/{company_id}/billing/subscription",
                headers=headers,
                json={
                    "plan_code": "starter",
                    "status": "active",
                    "current_period_start": "2026-08-03T00:00:00Z",
                    "current_period_end": "2026-09-03T00:00:00Z",
                    "cancel_at_period_end": False,
                    "reason": "Activate isolated beta subscription",
                },
            ),
            200,
            "Manual subscription activation",
        )
        if summary["subscription"]["status"] != "active":
            raise RuntimeError("Manual subscription state was not applied")
        invoice = expect(
            client.post(
                f"/api/v1/platform/companies/{company_id}/billing/invoices",
                headers=headers,
                json={
                    "invoice_number": "SINV-BILLING-GATE-001",
                    "status": "draft",
                    "currency": "THB",
                    "subtotal_satang": 10000,
                    "tax_satang": 700,
                    "memo": "Integer satang gate",
                    "reason": "Create isolated invoice",
                },
            ),
            201,
            "Invoice creation",
        )
        base_event = {
            "source": "manual.import",
            "company_id": company_id,
            "invoice_id": invoice["id"],
            "currency": "THB",
            "occurred_at": "2026-08-03T09:00:00Z",
            "reason": "Apply normalized billing event",
        }
        expect(
            client.post(
                "/api/v1/platform/billing/events",
                headers=headers,
                json={**base_event, "event_key": "gate-invoice-open", "event_type": "invoice.opened"},
            ),
            200,
            "Open invoice event",
        )
        paid_payload = {
            **base_event,
            "event_key": "gate-invoice-paid",
            "event_type": "invoice.paid",
            "amount_satang": 10700,
        }
        first_paid = expect(
            client.post("/api/v1/platform/billing/events", headers=headers, json=paid_payload),
            200,
            "Paid invoice event",
        )
        replay = expect(
            client.post(
                "/api/v1/platform/billing/events",
                headers=headers,
                json={**paid_payload, "reason": "Safe retry with a different operator note"},
            ),
            200,
            "Idempotent paid event replay",
        )
        if first_paid["id"] != replay["id"]:
            raise RuntimeError("Billing event retry was not idempotent")
        expect(
            client.post(
                "/api/v1/platform/billing/events",
                headers=headers,
                json={**paid_payload, "amount_satang": 10699},
            ),
            409,
            "Conflicting billing event key",
        )
        expect(
            client.post(
                "/api/v1/platform/billing/events",
                headers=headers,
                json={**paid_payload, "event_key": "raw-rejected", "raw_payload": {"card": "secret"}},
            ),
            422,
            "Raw provider payload rejection",
        )
        tenant_after = expect(
            client.get("/api/v1/membership/billing", headers=tenant_headers),
            200,
            "Tenant paid invoice summary",
        )
        if tenant_after["invoices"][0]["status"] != "paid":
            raise RuntimeError("Tenant billing summary did not reflect the paid invoice")
        client.portal.call(verify_database_evidence, company_id, invoice["id"])

    print("SaaS billing API smoke passed")


if __name__ == "__main__":
    main()
