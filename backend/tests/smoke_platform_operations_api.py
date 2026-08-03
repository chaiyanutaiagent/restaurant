from __future__ import annotations

import json
import os

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.main import app
from app.models.audit import AuditLog
from app.models.platform import PlatformOperationsSnapshot, PlatformOperator
from app.utils.security import hash_password


DATABASE_PREFIX = "restaurant_saas_operations_"
PLATFORM_USERNAME = "operations.platform.owner"
PLATFORM_PASSWORD = "Operations-Platform-Password!"
PRIVATE_MARKERS = ("/secure/private", "postgresql://", "password=private")


def expect(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    if expected >= 400:
        return response.json()
    return response.json()["data"]


async def prepare_operator() -> None:
    configured_database = os.environ.get("SAAS_OPERATIONS_DATABASE_NAME", "")
    if not configured_database.startswith(DATABASE_PREFIX):
        raise RuntimeError("Operations smoke refuses to write a non-isolated database")
    async with AsyncSessionLocal() as db:
        actual_database = await db.scalar(func.current_database())
        if actual_database != configured_database:
            raise RuntimeError(
                f"Operations database mismatch: {actual_database} != {configured_database}"
            )
        db.add(
            PlatformOperator(
                username=PLATFORM_USERNAME,
                display_name="Operations Platform Owner",
                hashed_password=hash_password(PLATFORM_PASSWORD),
                is_active=True,
                is_superuser=True,
            )
        )
        await db.commit()


async def verify_database_evidence() -> None:
    async with AsyncSessionLocal() as db:
        rows = list(
            await db.scalars(
                select(PlatformOperationsSnapshot).order_by(
                    PlatformOperationsSnapshot.created_at
                )
            )
        )
        audit_count = int(
            await db.scalar(
                select(func.count()).select_from(AuditLog).where(
                    AuditLog.action.in_(
                        [
                            "platform.operations.snapshot.capture",
                            "platform.operations.evidence.import",
                        ]
                    )
                )
            )
            or 0
        )
        if len(rows) != 2 or audit_count != 2:
            raise RuntimeError("Operations idempotency/audit evidence is incomplete")
        serialized = json.dumps(
            [
                {
                    "checks": row.component_checks,
                    "alerts": row.alert_codes,
                    "digest": row.evidence_sha256,
                }
                for row in rows
            ],
            sort_keys=True,
        )
        if any(marker in serialized for marker in PRIVATE_MARKERS):
            raise RuntimeError("Operational snapshot persisted sensitive evidence")


def main() -> None:
    with TestClient(app) as client:
        client.portal.call(prepare_operator)
        health = client.get("/health/ready")
        if health.status_code != 200 or set(health.json()) != {"status", "version"}:
            raise RuntimeError(f"Public readiness is not sanitized: {health.text}")
        expect(
            client.get("/api/v1/platform/operations/summary"),
            401,
            "Anonymous operations block",
        )
        login = expect(
            client.post(
                "/api/v1/platform/auth/login",
                json={"username": PLATFORM_USERNAME, "password": PLATFORM_PASSWORD},
            ),
            200,
            "Platform operations login",
        )
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        empty_summary = expect(
            client.get("/api/v1/platform/operations/summary", headers=headers),
            200,
            "Empty operations summary",
        )
        if empty_summary["latest_snapshot"] is not None:
            raise RuntimeError("Operations summary was not initially empty")
        captured = expect(
            client.post("/api/v1/platform/operations/capture", headers=headers),
            200,
            "Runtime capture",
        )
        if captured["source"] != "operator_runtime":
            raise RuntimeError("Runtime capture source is incorrect")

        rejected = client.post(
            "/api/v1/platform/operations/evidence",
            headers=headers,
            json={
                "captured_at": "2026-08-03T08:00:00Z",
                "overall_status": "ok",
                "component_checks": {"public_api": "ok"},
                "backup_path": "/secure/private/tenant.dump",
                "raw_error": "password=private",
            },
        )
        expect(rejected, 422, "Sensitive evidence rejection")

        evidence = {
            "captured_at": "2026-08-03T08:00:00Z",
            "overall_status": "ok",
            "component_checks": {"public_api": "ok", "reference_projector": "ok"},
            "projector_failed_events": 0,
            "projector_loop_errors": 0,
            "disk_usage_percent": 35,
            "backup_status": "current",
            "backup_age_hours": 2,
            "restore_status": "passed",
            "restore_drill_at": "2026-08-03T07:00:00Z",
            "alert_delivery_status": "not_configured",
            "alert_codes": [],
        }
        first = expect(
            client.post(
                "/api/v1/platform/operations/evidence",
                headers=headers,
                json=evidence,
            ),
            200,
            "First operational evidence import",
        )
        second = expect(
            client.post(
                "/api/v1/platform/operations/evidence",
                headers=headers,
                json=evidence,
            ),
            200,
            "Idempotent operational evidence import",
        )
        if first["id"] != second["id"]:
            raise RuntimeError("Operational evidence import was not idempotent")
        summary = expect(
            client.get("/api/v1/platform/operations/summary", headers=headers),
            200,
            "Populated operations summary",
        )
        if summary["latest_backup"]["backup_status"] != "current":
            raise RuntimeError("Protected backup state is missing")
        if summary["latest_restore"]["restore_status"] != "passed":
            raise RuntimeError("Protected restore state is missing")
        history = expect(
            client.get("/api/v1/platform/operations/history", headers=headers),
            200,
            "Operations history",
        )
        if len(history) != 2:
            raise RuntimeError("Operations history count is incorrect")
        serialized_responses = json.dumps([captured, first, summary, history], sort_keys=True)
        if any(marker in serialized_responses for marker in PRIVATE_MARKERS):
            raise RuntimeError("Protected Operations API exposed sensitive evidence")
        client.portal.call(verify_database_evidence)

    print("Platform operations API smoke passed")


if __name__ == "__main__":
    main()
