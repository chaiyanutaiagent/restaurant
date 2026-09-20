from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import TokenData
from app.models.device import DeviceRegistration
from app.models.offline_sync import OfflinePosOperation, PhysicalUATAudit, PhysicalUATCheck, PhysicalUATSession
from app.models.pos import CashierShift
from app.schemas.physical_uat import PhysicalUATCheckUpdate, PhysicalUATSessionCreate


AUTO_CHECKS = (
    ("counter_pairing", "system", "Counter จับคู่ถูก Company/Branch", True),
    ("release_identity", "system", "Release ตรงกับ UAT candidate", True),
    ("network_api", "system", "Network/API ตอบสนอง", True),
    ("open_shift", "system", "มีกะเปิดสำหรับสาขา", True),
    ("sync_queue_zero", "system", "Server queue ไม่มี pending/unknown/review", True),
)

MANUAL_CHECKS = (
    ("tablet_interaction", "hardware", "Tablet orientation/touch/keyboard/kiosk/restart/cache", True),
    ("product_barcode", "hardware", "สแกน Product barcode จริง", True),
    ("table_qr", "hardware", "สแกน Table QR จริง", True),
    ("customer_receipt", "hardware", "ใบเสร็จลูกค้า: ไทย/ยอด/รหัส/ความกว้าง/feed/cut", True),
    ("kitchen_slip", "hardware", "Kitchen slip และการอ่านจากจอครัว", True),
    ("printer_recovery", "hardware", "Paper-out/disconnect/reconnect/reprint ไม่สร้างบิลซ้ำ", True),
    ("cash_drawer", "hardware", "Cash drawer หรือ N/A ที่ Manager อนุมัติ", True),
    ("promptpay_sandbox", "payment", "PromptPay Sandbox/UAT reference และ reconciliation", True),
    ("dine_in_e2e", "flow", "Table QR → KDS → Serve → Payment → Receipt", True),
    ("takeaway_e2e", "flow", "Takeaway → Queue → KDS → Pickup", True),
    ("offline_cash_reconnect", "network", "Offline cash → reconnect → exactly one transaction", True),
    ("lost_ack", "network", "Lost acknowledgement inquiry/replay", True),
    ("network_toggle", "network", "Wi-Fi/Airplane/latency/packet loss/restart/multi-device", True),
    ("row_parity", "reconciliation", "Sale/Payment/Stock/Journal/Event/Tax/Loyalty parity", True),
    ("rollback_recovery", "recovery", "Kill switch/export/rollback/recovery evidence", True),
)
NA_ALLOWED_CHECKS = {"cash_drawer"}

SECRET_PATTERN = re.compile(
    r"(?i)(password|passwd|secret|access[_ -]?token|refresh[_ -]?token|pairing[_ -]?pin|wifi[_ -]?password|authorization\s*:|bearer\s+[a-z0-9._-]+)"
)


def assert_physical_uat_enabled() -> None:
    if not settings.physical_uat_evidence_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Physical UAT evidence is disabled")


def _contains_secret(value: object) -> bool:
    if isinstance(value, str):
        return SECRET_PATTERN.search(value) is not None
    if isinstance(value, dict):
        return any(_contains_secret(key) or _contains_secret(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_secret(item) for item in value)
    return False


class PhysicalUATService:
    def __init__(self, db: AsyncSession, identity_db: AsyncSession):
        self.db = db
        self.identity_db = identity_db

    async def create(self, current: TokenData, payload: PhysicalUATSessionCreate) -> PhysicalUATSession:
        assert_physical_uat_enabled()
        if current.branch_id is None:
            raise HTTPException(status_code=409, detail="Branch context required")
        device = await self.identity_db.get(DeviceRegistration, payload.device_id)
        if (
            device is None
            or device.company_id != current.company_id
            or device.branch_id != current.branch_id
            or device.device_type != "counter"
            or device.paired_at is None
            or device.revoked_at is not None
        ):
            raise HTTPException(status_code=409, detail="Active paired Counter in current Branch is required")
        session = PhysicalUATSession(
            company_id=current.company_id,
            branch_id=current.branch_id,
            device_id=device.id,
            release_commit=payload.release_commit.lower(),
            environment="uat",
            status="in_progress",
            created_by=current.user_id,
            device_snapshot={
                "device_code": device.device_code,
                "name": device.name,
                "type": device.device_type,
                "paired_at": device.paired_at.isoformat(),
                "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
                "device_model": payload.device_model,
                "os_version": payload.os_version,
                "browser_version": payload.browser_version,
                "printer_model_connection": payload.printer_model_connection,
            },
            environment_snapshot={
                "base_url": settings.saas_public_base_url,
                "app_version": settings.app_version,
                "configured_release_commit": settings.uat_release_commit,
                "network_profile": payload.network_profile,
                "offline_mode_enabled": settings.pos_offline_mode_enabled,
            },
        )
        self.db.add(session)
        await self.db.flush()
        for key, category, label, required in (*AUTO_CHECKS, *MANUAL_CHECKS):
            self.db.add(PhysicalUATCheck(
                session_id=session.id,
                check_key=key,
                category=category,
                label=label,
                source="automatic" if (key, category, label, required) in AUTO_CHECKS else "manual",
                required=required,
                result="pending",
                evidence_snapshot={},
            ))
        await self._audit(session, current.user_id, "session_created", {"release_commit": session.release_commit})
        await self.db.commit()
        await self.refresh_automatic(session, device=device)
        return session

    async def refresh_automatic(
        self,
        session: PhysicalUATSession,
        *,
        device: DeviceRegistration | None = None,
    ) -> None:
        assert_physical_uat_enabled()
        if device is None:
            device = await self.identity_db.get(DeviceRegistration, session.device_id)
        active_queue_count = int(await self.db.scalar(
            select(func.count()).select_from(OfflinePosOperation).where(
                OfflinePosOperation.company_id == session.company_id,
                OfflinePosOperation.branch_id == session.branch_id,
                OfflinePosOperation.status.in_((
                    "pending_sync", "syncing", "server_acknowledged", "unknown", "needs_review", "quarantined"
                )),
            )
        ) or 0)
        open_shift_count = int(await self.db.scalar(
            select(func.count()).select_from(CashierShift).where(
                CashierShift.company_id == session.company_id,
                CashierShift.branch_id == session.branch_id,
                CashierShift.closed_at.is_(None),
            )
        ) or 0)
        configured_release = settings.uat_release_commit.strip().lower()
        release_match = configured_release not in {"", "unreleased"} and (
            configured_release.startswith(session.release_commit)
            or session.release_commit.startswith(configured_release)
        )
        values = {
            "counter_pairing": (
                "pass" if device and device.paired_at and device.revoked_at is None else "fail",
                {"device_id": str(session.device_id), "last_seen_at": device.last_seen_at.isoformat() if device and device.last_seen_at else None},
            ),
            "release_identity": (
                "pass" if release_match else "fail",
                {"expected": session.release_commit, "configured": configured_release},
            ),
            "network_api": ("pass", {"checked_at": datetime.now(timezone.utc).isoformat()}),
            "open_shift": ("pass" if open_shift_count > 0 else "fail", {"open_shift_count": open_shift_count}),
            "sync_queue_zero": ("pass" if active_queue_count == 0 else "fail", {"active_queue_count": active_queue_count}),
        }
        rows = list((await self.db.scalars(
            select(PhysicalUATCheck).where(
                PhysicalUATCheck.session_id == session.id,
                PhysicalUATCheck.source == "automatic",
            )
        )).all())
        now = datetime.now(timezone.utc)
        for row in rows:
            result, evidence = values[row.check_key]
            row.result = result
            row.reason = None if result == "pass" else "ระบบตรวจพบว่ายังไม่ผ่านเงื่อนไข"
            row.evidence_snapshot = evidence
            row.tested_at = now
        if any(row.result == "fail" for row in rows) and session.status in {"ready_for_signoff", "uat_approved"}:
            session.status = "not_ready"
            session.submitted_by = None
            session.submitted_at = None
            session.technical_approved_by = None
            session.technical_approved_at = None
            session.business_approved_by = None
            session.business_approved_at = None
        await self.db.commit()

    async def update_check(
        self,
        current: TokenData,
        session_id: uuid.UUID,
        check_key: str,
        payload: PhysicalUATCheckUpdate,
    ) -> PhysicalUATSession:
        session = await self._session(current, session_id)
        check = await self.db.scalar(select(PhysicalUATCheck).where(
            PhysicalUATCheck.session_id == session.id,
            PhysicalUATCheck.check_key == check_key,
        ))
        if check is None:
            raise HTTPException(status_code=404, detail="UAT check not found")
        if check.source != "manual":
            raise HTTPException(status_code=409, detail="Automatic checks cannot be manually overridden")
        if session.status == "uat_approved":
            raise HTTPException(status_code=409, detail="Approved evidence is immutable; create a new UAT session")
        if payload.result == "na" and check.check_key not in NA_ALLOWED_CHECKS:
            raise HTTPException(status_code=409, detail="This required physical test cannot be marked N/A")
        if payload.result == "na" and "*" not in current.permissions and "system.device.manage" not in current.permissions:
            raise HTTPException(status_code=403, detail="Manager permission required for N/A")
        safe_values = [payload.reason, payload.evidence_reference, payload.defect_id, payload.evidence]
        if any(_contains_secret(value) for value in safe_values if value is not None):
            raise HTTPException(status_code=400, detail="Evidence contains a forbidden secret or credential")
        check.result = payload.result
        check.reason = payload.reason
        check.evidence_reference = payload.evidence_reference
        check.defect_id = payload.defect_id
        check.defect_severity = payload.defect_severity
        check.tested_by = current.user_id
        check.tested_at = datetime.now(timezone.utc)
        check.evidence_snapshot = payload.evidence
        session.status = "in_progress"
        session.submitted_by = None
        session.submitted_at = None
        session.technical_approved_by = None
        session.technical_approved_at = None
        session.business_approved_by = None
        session.business_approved_at = None
        await self._audit(
            session,
            current.user_id,
            "check_recorded",
            {"check_key": check_key, "result": payload.result, "defect_id": payload.defect_id},
        )
        await self.db.commit()
        return session

    async def submit(self, current: TokenData, session_id: uuid.UUID) -> PhysicalUATSession:
        session = await self._session(current, session_id)
        await self.refresh_automatic(session)
        checks = await self._checks(session.id)
        blockers = [row.check_key for row in checks if row.required and row.result not in {"pass", "na"}]
        critical_defects = [row.defect_id for row in checks if row.defect_severity in {"P0", "P1"}]
        if blockers or critical_defects:
            session.status = "not_ready"
            await self._audit(
                session,
                current.user_id,
                "submission_blocked",
                {"blockers": blockers, "critical_defects": critical_defects},
            )
            await self.db.commit()
            raise HTTPException(
                status_code=409,
                detail={"code": "uat_not_ready", "blockers": blockers, "critical_defects": critical_defects},
            )
        session.status = "ready_for_signoff"
        session.submitted_by = current.user_id
        session.submitted_at = datetime.now(timezone.utc)
        await self._audit(session, current.user_id, "ready_for_signoff", {"check_count": len(checks)})
        await self.db.commit()
        return session

    async def signoff(
        self,
        current: TokenData,
        session_id: uuid.UUID,
        *,
        role: str,
        note: str,
    ) -> PhysicalUATSession:
        session = await self._session(current, session_id)
        if session.status not in {"ready_for_signoff", "uat_approved"}:
            raise HTTPException(status_code=409, detail="Session is not ready for sign-off")
        if session.submitted_by == current.user_id:
            raise HTTPException(status_code=409, detail="Maker and checker must be different users")
        if role == "technical":
            if session.business_approved_by == current.user_id:
                raise HTTPException(status_code=409, detail="Technical and Business signers must be different users")
            session.technical_approved_by = current.user_id
            session.technical_approved_at = datetime.now(timezone.utc)
        else:
            if session.technical_approved_by == current.user_id:
                raise HTTPException(status_code=409, detail="Technical and Business signers must be different users")
            session.business_approved_by = current.user_id
            session.business_approved_at = datetime.now(timezone.utc)
        if session.technical_approved_by and session.business_approved_by:
            session.status = "uat_approved"
        await self._audit(session, current.user_id, f"{role}_signoff", {"note": note})
        await self.db.commit()
        return session

    async def get(self, current: TokenData, session_id: uuid.UUID) -> PhysicalUATSession:
        session = await self._session(current, session_id)
        await self.refresh_automatic(session)
        return session

    async def list(self, current: TokenData) -> list[PhysicalUATSession]:
        assert_physical_uat_enabled()
        if current.branch_id is None:
            return []
        return list((await self.db.scalars(
            select(PhysicalUATSession).where(
                PhysicalUATSession.company_id == current.company_id,
                PhysicalUATSession.branch_id == current.branch_id,
            ).order_by(PhysicalUATSession.created_at.desc())
        )).all())

    async def serialize(self, session: PhysicalUATSession) -> dict:
        checks = await self._checks(session.id)
        summary = {
            "passed": sum(row.result == "pass" for row in checks),
            "pending": sum(row.result == "pending" for row in checks),
            "failed": sum(row.result == "fail" for row in checks),
            "not_applicable": sum(row.result == "na" for row in checks),
            "required_incomplete": sum(row.required and row.result not in {"pass", "na"} for row in checks),
            "critical_defects": sum(row.defect_severity in {"P0", "P1"} for row in checks),
        }
        return {
            "id": session.id,
            "company_id": session.company_id,
            "branch_id": session.branch_id,
            "device_id": session.device_id,
            "release_commit": session.release_commit,
            "environment": session.environment,
            "status": session.status,
            "created_by": session.created_by,
            "submitted_by": session.submitted_by,
            "submitted_at": session.submitted_at,
            "technical_approved_by": session.technical_approved_by,
            "technical_approved_at": session.technical_approved_at,
            "business_approved_by": session.business_approved_by,
            "business_approved_at": session.business_approved_at,
            "device_snapshot": session.device_snapshot,
            "environment_snapshot": session.environment_snapshot,
            "summary": summary,
            "checks": [
                {
                    "id": row.id,
                    "check_key": row.check_key,
                    "category": row.category,
                    "label": row.label,
                    "source": row.source,
                    "required": row.required,
                    "result": row.result,
                    "reason": row.reason,
                    "evidence_reference": row.evidence_reference,
                    "defect_id": row.defect_id,
                    "defect_severity": row.defect_severity,
                    "tested_by": row.tested_by,
                    "tested_at": row.tested_at,
                    "evidence": row.evidence_snapshot,
                }
                for row in checks
            ],
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }

    async def _session(self, current: TokenData, session_id: uuid.UUID) -> PhysicalUATSession:
        assert_physical_uat_enabled()
        session = await self.db.get(PhysicalUATSession, session_id)
        if (
            session is None
            or session.company_id != current.company_id
            or session.branch_id != current.branch_id
        ):
            raise HTTPException(status_code=404, detail="Physical UAT session not found")
        return session

    async def _checks(self, session_id: uuid.UUID) -> list[PhysicalUATCheck]:
        return list((await self.db.scalars(
            select(PhysicalUATCheck)
            .where(PhysicalUATCheck.session_id == session_id)
            .order_by(PhysicalUATCheck.category, PhysicalUATCheck.created_at)
        )).all())

    async def _audit(
        self,
        session: PhysicalUATSession,
        actor_user_id: uuid.UUID,
        action: str,
        evidence: dict,
    ) -> None:
        self.db.add(PhysicalUATAudit(
            session_id=session.id,
            company_id=session.company_id,
            branch_id=session.branch_id,
            actor_user_id=actor_user_id,
            event_key=f"{action}:{uuid.uuid4()}",
            action=action,
            evidence=evidence,
        ))
