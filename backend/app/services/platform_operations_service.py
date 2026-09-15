from __future__ import annotations

from datetime import datetime, timezone
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any
import uuid

import redis.asyncio as aioredis
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import (
    AsyncSessionLocal,
    PlatformSessionLocal,
    RestaurantSessionLocal,
    RetailSessionLocal,
    TakeawaySessionLocal,
)
from app.models.audit import AuditLog
from app.models.platform import PlatformOperationsSnapshot
from app.schemas.platform import (
    OPERATIONS_ALERT_CODES,
    PlatformOperationsEvidenceImport,
    PlatformOperationsSnapshotRead,
    PlatformOperationsSummaryRead,
    PlatformRuntimeRead,
)
from app.services.reference_projector_worker import reference_projector_state
from app.services.takeaway_reference_projector import takeaway_projector_state


async def _database_check(session_factory) -> str:
    try:
        async with session_factory() as db:
            await asyncio.wait_for(db.execute(select(1)), timeout=5)
        return "ok"
    except Exception:  # pragma: no cover - dependency failure path
        return "error"


async def _redis_check() -> str:
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await asyncio.wait_for(redis.ping(), timeout=5)
        return "ok"
    except Exception:  # pragma: no cover - dependency failure path
        return "error"
    finally:
        await redis.aclose()


def _uploads_check() -> str:
    try:
        upload_path = Path(settings.upload_dir)
        upload_path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=upload_path, prefix=".health-", delete=True):
            pass
        return "ok"
    except Exception:  # pragma: no cover - dependency failure path
        return "error"


def _disk_usage_percent() -> int | None:
    try:
        usage = shutil.disk_usage(Path(settings.upload_dir))
        return round((usage.used / usage.total) * 100) if usage.total else None
    except Exception:  # pragma: no cover - platform-specific failure path
        return None


async def collect_runtime_state() -> PlatformRuntimeRead:
    legacy, platform, restaurant, redis = await asyncio.gather(
        _database_check(AsyncSessionLocal),
        _database_check(PlatformSessionLocal),
        _database_check(RestaurantSessionLocal),
        _redis_check(),
    )
    checks = {
        "legacy_database": legacy,
        "platform_database": platform,
        "restaurant_database": restaurant,
        "retail_database": (
            await _database_check(RetailSessionLocal)
            if RetailSessionLocal is not None
            else "disabled"
        ),
        "takeaway_database": (
            await _database_check(TakeawaySessionLocal)
            if settings.takeaway_feature_enabled and TakeawaySessionLocal is not None
            else "error"
            if settings.takeaway_feature_enabled
            else "disabled"
        ),
        "redis": redis,
        "uploads": _uploads_check(),
        "reference_projector": (
            "ok"
            if settings.reference_projector_enabled and reference_projector_state.running
            else "error"
            if settings.reference_projector_enabled
            else "disabled"
        ),
        "takeaway_reference_projector": (
            "ok"
            if settings.takeaway_feature_enabled and takeaway_projector_state.running
            else "error"
            if settings.takeaway_feature_enabled
            else "disabled"
        ),
    }
    healthy = all(value in {"ok", "disabled"} for value in checks.values())
    return PlatformRuntimeRead(
        status="ok" if healthy else "critical",
        component_checks=checks,
        projector_failed_events=max(reference_projector_state.failed, 0),
        projector_loop_errors=max(reference_projector_state.loop_errors, 0),
        disk_usage_percent=_disk_usage_percent(),
    )


def _evidence_digest(data: PlatformOperationsEvidenceImport) -> str:
    canonical = json.dumps(
        data.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resilience_evidence_to_import(payload: dict[str, Any]) -> PlatformOperationsEvidenceImport:
    raw_alerts = [str(item).lower() for item in payload.get("alerts", [])]
    explicit_codes = [
        str(item) for item in payload.get("alert_codes", []) if str(item) in OPERATIONS_ALERT_CODES
    ]
    mappings = (
        ("readiness", "readiness_unhealthy"),
        ("failed events", "projector_failed"),
        ("loop errors", "projector_loop_errors"),
        ("disk usage", "disk_threshold"),
        ("no phase 5", "backup_missing"),
        ("backup is missing", "backup_incomplete"),
        ("old; maximum", "backup_stale"),
        ("checksum failed", "backup_checksum_failed"),
        ("restore evidence", "restore_missing"),
        ("restore drill is", "restore_stale"),
        ("restore drill failed", "restore_failed"),
        ("webhook delivery is required", "alert_not_configured"),
        ("webhook delivery failed", "alert_delivery_failed"),
    )
    alert_codes = set(explicit_codes)
    for message in raw_alerts:
        for marker, code in mappings:
            if marker in message:
                alert_codes.add(code)

    status_value = str(payload.get("status", "critical")).lower()
    health_code = str(payload.get("health_http_code", "000"))
    projector_failed = max(int(payload.get("reference_projector_failed_events", 0)), 0)
    projector_errors = max(int(payload.get("reference_projector_loop_errors", 0)), 0)
    component_checks = {
        "public_api": "ok" if health_code == "200" and status_value == "ok" else "error",
        "reference_projector": (
            "ok" if projector_failed == 0 and projector_errors == 0 else "error"
        ),
    }
    backup_age_raw = int(payload.get("backup_age_hours", -1))
    backup_age = backup_age_raw if backup_age_raw >= 0 else None
    if "backup_checksum_failed" in alert_codes:
        backup_status = "failed"
    elif "backup_stale" in alert_codes:
        backup_status = "stale"
    elif payload.get("latest_backup") and backup_age is not None:
        backup_status = "current"
    else:
        backup_status = "unknown"

    restore_status = str(payload.get("restore_status", "unknown"))
    if restore_status not in {"unknown", "passed", "stale", "failed"}:
        restore_status = "failed"
    alert_delivery_status = str(payload.get("alert_delivery_status", ""))
    if alert_delivery_status not in {"unknown", "not_configured", "healthy", "failed"}:
        if payload.get("alert_delivery_configured"):
            alert_delivery_status = "healthy" if status_value == "ok" else "unknown"
        else:
            alert_delivery_status = "not_configured"
    if "alert_delivery_failed" in alert_codes:
        alert_delivery_status = "failed"

    return PlatformOperationsEvidenceImport(
        captured_at=payload.get("timestamp") or datetime.now(timezone.utc),
        overall_status="ok" if status_value == "ok" else "critical",
        component_checks=component_checks,
        projector_failed_events=projector_failed,
        projector_loop_errors=projector_errors,
        disk_usage_percent=(
            int(payload["disk_usage_percent"])
            if payload.get("disk_usage_percent") is not None
            else None
        ),
        backup_status=backup_status,
        backup_age_hours=backup_age,
        restore_status=restore_status,
        restore_drill_at=payload.get("restore_drill_at"),
        alert_delivery_status=alert_delivery_status,
        alert_codes=sorted(alert_codes),
    )


class PlatformOperationsService:
    def __init__(self, db: AsyncSession, *, operator_id: uuid.UUID | None):
        self.db = db
        self.operator_id = operator_id

    async def capture_runtime(
        self,
        *,
        scheduled: bool = False,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PlatformOperationsSnapshotRead:
        runtime = await collect_runtime_state()
        evidence = PlatformOperationsEvidenceImport(
            captured_at=datetime.now(timezone.utc),
            overall_status="ok" if runtime.status == "ok" else "critical",
            component_checks=runtime.component_checks,
            projector_failed_events=runtime.projector_failed_events,
            projector_loop_errors=runtime.projector_loop_errors,
            disk_usage_percent=runtime.disk_usage_percent,
        )
        return await self._store(
            evidence,
            source="scheduled_runtime" if scheduled else "operator_runtime",
            action="platform.operations.snapshot.capture",
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def import_evidence(
        self,
        evidence: PlatformOperationsEvidenceImport,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PlatformOperationsSnapshotRead:
        return await self._store(
            evidence,
            source="resilience_import",
            action="platform.operations.evidence.import",
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def summary(self) -> PlatformOperationsSummaryRead:
        runtime = await collect_runtime_state()
        latest = await self._latest()
        latest_backup = await self._latest(
            PlatformOperationsSnapshot.backup_status != "unknown"
        )
        latest_restore = await self._latest(
            PlatformOperationsSnapshot.restore_status != "unknown"
        )
        latest_alert = await self._latest(
            or_(
                PlatformOperationsSnapshot.alert_delivery_status != "unknown",
                PlatformOperationsSnapshot.overall_status != "ok",
            )
        )
        return PlatformOperationsSummaryRead(
            generated_at=datetime.now(timezone.utc),
            runtime=runtime,
            latest_snapshot=self._read(latest) if latest else None,
            latest_backup=self._read(latest_backup) if latest_backup else None,
            latest_restore=self._read(latest_restore) if latest_restore else None,
            latest_alert=self._read(latest_alert) if latest_alert else None,
        )

    async def history(self, *, limit: int = 50) -> list[PlatformOperationsSnapshotRead]:
        rows = list(
            await self.db.scalars(
                select(PlatformOperationsSnapshot)
                .order_by(
                    PlatformOperationsSnapshot.captured_at.desc(),
                    PlatformOperationsSnapshot.id.desc(),
                )
                .limit(limit)
            )
        )
        return [self._read(row) for row in rows]

    async def _store(
        self,
        evidence: PlatformOperationsEvidenceImport,
        *,
        source: str,
        action: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> PlatformOperationsSnapshotRead:
        digest = _evidence_digest(evidence)
        existing = await self.db.scalar(
            select(PlatformOperationsSnapshot).where(
                PlatformOperationsSnapshot.evidence_sha256 == digest
            )
        )
        if existing is not None:
            return self._read(existing)
        row = PlatformOperationsSnapshot(
            **evidence.model_dump(),
            source=source,
            evidence_sha256=digest,
            captured_by=self.operator_id,
        )
        self.db.add(row)
        await self.db.flush()
        self.db.add(
            AuditLog(
                company_id=None,
                user_id=self.operator_id,
                action=action,
                resource="PlatformOperationsSnapshot",
                resource_id=str(row.id),
                new_value={
                    "overall_status": row.overall_status,
                    "source": source,
                    "backup_status": row.backup_status,
                    "restore_status": row.restore_status,
                    "alert_delivery_status": row.alert_delivery_status,
                    "alert_codes": row.alert_codes,
                    "evidence_sha256": digest,
                },
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        await self.db.commit()
        return self._read(row)

    async def _latest(self, *filters) -> PlatformOperationsSnapshot | None:
        return await self.db.scalar(
            select(PlatformOperationsSnapshot)
            .where(*filters)
            .order_by(
                PlatformOperationsSnapshot.captured_at.desc(),
                PlatformOperationsSnapshot.id.desc(),
            )
            .limit(1)
        )

    @staticmethod
    def _read(row: PlatformOperationsSnapshot) -> PlatformOperationsSnapshotRead:
        return PlatformOperationsSnapshotRead.model_validate(row)
