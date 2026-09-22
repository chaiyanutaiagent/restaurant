from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import TokenData
from app.models.api_integration import APIKey, ExternalOrder, WebhookDelivery, WebhookEndpoint
from app.models.audit import AuditLog
from app.models.integration import OperationalOutboxEvent
from app.models.offline_sync import PhysicalUATCheck, PhysicalUATSession
from app.models.platform import (
    CompanyReportingEventReceipt,
    CompanyReportingFact,
    CompanyReportingSourceState,
)
from app.models.tax_operations import TaxLedgerEntry, TaxReconciliationIssue
from app.schemas.company_foundation import (
    CompanyCoverageAreaRead,
    CompanyGovernanceAreaRead,
    CompanyGovernanceMetricRead,
    CompanyGovernanceRead,
    CompanyReleaseGateRead,
)


GOVERNANCE_PERMISSIONS = {
    "system.company.view",
    "system.company.edit",
    "accounting.report.view",
}
STALE_AFTER = timedelta(minutes=5)


def _has_governance_access(current: TokenData) -> bool:
    return "*" in current.permissions or bool(GOVERNANCE_PERMISSIONS.intersection(current.permissions))


def _metric(
    key: str,
    label: str,
    value: int | float | str,
    severity: str = "info",
) -> CompanyGovernanceMetricRead:
    return CompanyGovernanceMetricRead(
        key=key,
        label=label,
        value=value,
        severity=severity,  # type: ignore[arg-type]
    )


def coverage_matrix() -> list[CompanyCoverageAreaRead]:
    """Describe shipped surfaces without claiming physical or Production acceptance."""
    return [
        CompanyCoverageAreaRead(key="platform", title="Platform Console", state="available", entry_route="/platform", release_boundary="Software UAT passed; Production unchanged"),
        CompanyCoverageAreaRead(key="company", title="Company Admin", state="available", entry_route="/company", release_boundary="Tenant context and RBAC are Server-authoritative"),
        CompanyCoverageAreaRead(key="erp", title="Shared ERP", state="read_only", entry_route="/company/erp", release_boundary="Real provider, tax filing and accountant sign-off remain HOLD"),
        CompanyCoverageAreaRead(key="restaurant", title="Restaurant POS", state="available", entry_route="/restaurant", release_boundary="Software UAT passed; physical acceptance remains HOLD"),
        CompanyCoverageAreaRead(key="retail", title="Retail POS", state="hold", entry_route="/pos", release_boundary="Cash Pilot only; source cutover and physical acceptance remain HOLD"),
        CompanyCoverageAreaRead(key="takeaway", title="Takeaway POS", state="hold", entry_route="/takeaway", release_boundary="Dark Launch; transaction writes remain Server-blocked"),
        CompanyCoverageAreaRead(key="kitchen", title="Central Kitchen", state="read_only", entry_route="/company-kitchen", release_boundary="Read-only; production and stock/QC writes remain HOLD"),
        CompanyCoverageAreaRead(key="supply_chain", title="Supply Chain", state="read_only", entry_route="/company-distribution", release_boundary="Read-only; distribution writes remain HOLD"),
        CompanyCoverageAreaRead(key="public", title="Public Experience", state="read_only", entry_route="/test-company", release_boundary="Catalog/Locator only; Ecommerce remains disabled"),
        CompanyCoverageAreaRead(key="integration_reporting", title="Integration & Reporting", state="read_only", entry_route="/company/governance", release_boundary="Server evidence is read-only; Incident/retention execution remains planned"),
    ]


class CompanyGovernanceService:
    def __init__(self, identity_db: AsyncSession, legacy_db: AsyncSession):
        self.identity_db = identity_db
        self.legacy_db = legacy_db

    async def read(self, current: TokenData) -> CompanyGovernanceRead:
        if not _has_governance_access(current):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        company_scope = "*" in current.permissions or "company" in current.scope_types
        if not company_scope and current.branch_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Branch context required")

        now = datetime.now(timezone.utc)
        integration_areas = await self._integration_areas(current, company_scope, now)
        reporting_area = await self._reporting_area(current, company_scope, now)
        reconciliation_areas = await self._reconciliation_areas(current, now)
        evidence_areas, physical_approved = await self._evidence_areas(current, now)
        areas = [*integration_areas, reporting_area, *reconciliation_areas, *evidence_areas]
        tax_blockers = next(
            (int(metric.value) for area in reconciliation_areas if area.key == "tax_reconciliation" for metric in area.metrics if metric.key == "blockers"),
            0,
        )
        release_gates = self._release_gates(physical_approved=physical_approved, tax_blockers=tax_blockers)
        summary = {
            "ready": sum(area.state == "ready" for area in areas),
            "attention": sum(area.state == "attention" for area in areas) + sum(gate.state == "attention" for gate in release_gates),
            "blocked": sum(area.state == "blocked" for area in areas) + sum(gate.state == "blocked" for gate in release_gates),
            "hold": sum(area.state == "hold" for area in areas) + sum(gate.state == "hold" for gate in release_gates),
            "planned": sum(area.state == "planned" for area in areas) + sum(gate.state == "planned" for gate in release_gates),
        }
        return CompanyGovernanceRead(
            company_id=current.company_id,
            branch_id=None if company_scope else current.branch_id,
            scope="company" if company_scope else "branch",
            environment="production" if settings.environment == "production" else "uat",
            release_commit=settings.uat_release_commit,
            areas=areas,
            release_gates=release_gates,
            coverage=coverage_matrix(),
            summary=summary,
            generated_at=now,
        )

    async def _integration_areas(
        self,
        current: TokenData,
        company_scope: bool,
        now: datetime,
    ) -> list[CompanyGovernanceAreaRead]:
        if not company_scope:
            return [
                CompanyGovernanceAreaRead(
                    key="api_webhook_governance",
                    title="API Key และ Webhook",
                    state="permission_denied",
                    mode="read_only",
                    source_system="legacy.integration",
                    reason="ข้อมูลระดับบริษัทถูกปิดในบริบทสาขา",
                    deep_link="/integrations",
                ),
                CompanyGovernanceAreaRead(
                    key="external_orders",
                    title="External Orders",
                    state="permission_denied",
                    mode="read_only",
                    source_system="legacy.external_orders",
                    reason="External order ไม่มี Branch authority จนกว่า Server mapping จะยืนยัน",
                ),
            ]

        keys = list((await self.legacy_db.scalars(select(APIKey).where(APIKey.company_id == current.company_id))).all())
        hooks = list((await self.legacy_db.scalars(select(WebhookEndpoint).where(WebhookEndpoint.company_id == current.company_id))).all())
        lifecycle_active = [row for row in keys if row.is_active and row.revoked_at is None]
        expired_active = [row for row in lifecycle_active if row.expires_at is not None and row.expires_at <= now]
        missing_governance = [
            row for row in lifecycle_active
            if row.expires_at is None or row.owner_contact.strip().lower() == "unassigned"
        ]
        wildcard_active = [row for row in lifecycle_active if "*" in (row.scopes or [])]
        active_keys = [
            row for row in lifecycle_active
            if row.expires_at is not None
            and row.expires_at > now
            and row.owner_contact.strip().lower() != "unassigned"
            and bool(row.scopes)
            and "*" not in row.scopes
        ]
        failed_deliveries = int((await self.legacy_db.scalar(select(func.count(WebhookDelivery.id)).where(WebhookDelivery.company_id == current.company_id, WebhookDelivery.failed_at.is_not(None), WebhookDelivery.delivered_at.is_(None)))) or 0)
        retry_pending = int((await self.legacy_db.scalar(select(func.count(WebhookDelivery.id)).where(WebhookDelivery.company_id == current.company_id, WebhookDelivery.next_retry_at.is_not(None), WebhookDelivery.delivered_at.is_(None)))) or 0)
        active_hooks = [row for row in hooks if row.is_active]
        integration_state = "attention" if expired_active or missing_governance or wildcard_active or failed_deliveries else "ready" if active_keys or active_hooks else "disabled"
        latest_hook = max((row.updated_at for row in hooks), default=None)

        order_rows = list((await self.legacy_db.execute(select(ExternalOrder.status, func.count(ExternalOrder.id)).where(ExternalOrder.company_id == current.company_id).group_by(ExternalOrder.status))).all())
        order_counts = {str(state): int(total) for state, total in order_rows}
        pending_orders = sum(total for state, total in order_counts.items() if state not in {"fulfilled", "cancelled", "rejected"})
        latest_order = await self.legacy_db.scalar(select(func.max(ExternalOrder.received_at)).where(ExternalOrder.company_id == current.company_id))
        return [
            CompanyGovernanceAreaRead(
                key="api_webhook_governance",
                title="API Key และ Webhook",
                state=integration_state,
                mode="read_only",
                source_system="legacy.integration",
                reason=("พบ key ที่ขาด owner/expiry, เป็น wildcard, หมดอายุ หรือมี delivery ล้มเหลว" if integration_state == "attention" else "แสดงสถานะจริงจาก key, endpoint และ delivery; ไม่มีการเปิดเผย secret"),
                deep_link="/integrations",
                metrics=[
                    _metric("active_keys", "API key ใช้งาน", len(active_keys)),
                    _metric("expired_keys", "Key หมดอายุ", len(expired_active), "warning" if expired_active else "info"),
                    _metric("missing_governance", "Key ต้อง Rotate", len(missing_governance), "warning" if missing_governance else "info"),
                    _metric("wildcard_keys", "Wildcard key", len(wildcard_active), "warning" if wildcard_active else "info"),
                    _metric("active_webhooks", "Webhook เปิดใช้", len(active_hooks)),
                    _metric("failed_deliveries", "Delivery ล้มเหลว", failed_deliveries, "error" if failed_deliveries else "info"),
                    _metric("retry_pending", "รอลองใหม่", retry_pending, "warning" if retry_pending else "info"),
                ],
                updated_at=latest_hook,
                stale=bool(latest_hook and now - latest_hook > STALE_AFTER and active_hooks),
            ),
            CompanyGovernanceAreaRead(
                key="external_orders",
                title="External Orders",
                state="attention" if pending_orders else "ready" if order_counts else "disabled",
                mode="read_only",
                source_system="legacy.external_orders",
                reason=("มีรายการที่ยังต้องตรวจ mapping/payment ก่อน fulfill" if pending_orders else "ไม่มีรายการค้าง; fulfillment ยังใช้ Server authority"),
                deep_link="/integrations",
                metrics=[
                    _metric("total", "ทั้งหมด", sum(order_counts.values())),
                    _metric("pending", "รอตรวจ", pending_orders, "warning" if pending_orders else "info"),
                    _metric("fulfilled", "สำเร็จ", order_counts.get("fulfilled", 0)),
                ],
                updated_at=latest_order,
            ),
        ]

    async def _reporting_area(
        self,
        current: TokenData,
        company_scope: bool,
        now: datetime,
    ) -> CompanyGovernanceAreaRead:
        fact_filters = [CompanyReportingFact.company_id == current.company_id]
        if not company_scope and current.branch_id is not None:
            fact_filters.append(CompanyReportingFact.branch_id == current.branch_id)
        fact_count = int((await self.identity_db.scalar(select(func.count(CompanyReportingFact.id)).where(*fact_filters))) or 0)
        last_projected = await self.identity_db.scalar(select(func.max(CompanyReportingFact.last_projected_at)).where(*fact_filters))
        dead_letters = 0
        source_states: list[CompanyReportingSourceState] = []
        if company_scope:
            dead_letters = int((await self.identity_db.scalar(select(func.count(CompanyReportingEventReceipt.id)).where(CompanyReportingEventReceipt.company_id == current.company_id, CompanyReportingEventReceipt.status == "dead_letter"))) or 0)
            source_states = list((await self.identity_db.scalars(select(CompanyReportingSourceState))).all())
        failed_sources = sum(row.status in {"failed", "degraded"} for row in source_states)
        last_polled = max((row.last_polled_at for row in source_states if row.last_polled_at), default=None)
        stale = bool(settings.shared_reporting_projector_enabled and last_polled and now - last_polled > STALE_AFTER)
        if not settings.shared_reporting_projector_enabled:
            state = "disabled"
        elif dead_letters or failed_sources:
            state = "blocked"
        elif stale or fact_count == 0:
            state = "attention"
        else:
            state = "ready"
        return CompanyGovernanceAreaRead(
            key="shared_reporting",
            title="Shared Reporting Projection",
            state=state,
            mode="shadow",
            source_system="platform.reporting_projection",
            reason="Projection เป็นข้อมูลอนุพันธ์และไม่ใช่ operational authority",
            deep_link="/reports/company",
            metrics=[
                _metric("facts", "เอกสารใน Projection", fact_count),
                _metric("dead_letters", "Dead letter", dead_letters, "blocker" if dead_letters else "info"),
                _metric("failed_sources", "Source ผิดปกติ", failed_sources, "error" if failed_sources else "info"),
            ],
            updated_at=last_projected or last_polled,
            stale=stale,
        )

    async def _reconciliation_areas(
        self,
        current: TokenData,
        now: datetime,
    ) -> list[CompanyGovernanceAreaRead]:
        branch_filters = [] if "company" in current.scope_types or "*" in current.permissions else [OperationalOutboxEvent.branch_id == current.branch_id]
        outbox_rows = list((await self.legacy_db.execute(select(OperationalOutboxEvent.status, func.count(OperationalOutboxEvent.id)).where(OperationalOutboxEvent.company_id == current.company_id, *branch_filters).group_by(OperationalOutboxEvent.status))).all())
        outbox = {str(state): int(total) for state, total in outbox_rows}
        outbox_failed = sum(total for state, total in outbox.items() if state in {"failed", "dead_letter"})
        outbox_pending = sum(total for state, total in outbox.items() if state in {"pending", "processing"})
        latest_outbox = await self.legacy_db.scalar(select(func.max(OperationalOutboxEvent.created_at)).where(OperationalOutboxEvent.company_id == current.company_id, *branch_filters))

        tax_filters = [TaxReconciliationIssue.company_id == current.company_id, TaxReconciliationIssue.status == "open"]
        ledger_filters = [TaxLedgerEntry.company_id == current.company_id]
        if "company" not in current.scope_types and "*" not in current.permissions and current.branch_id is not None:
            tax_filters.append(TaxReconciliationIssue.branch_id == current.branch_id)
            ledger_filters.append(TaxLedgerEntry.branch_id == current.branch_id)
        tax_rows = list((await self.legacy_db.execute(select(TaxReconciliationIssue.severity, func.count(TaxReconciliationIssue.id)).where(*tax_filters).group_by(TaxReconciliationIssue.severity))).all())
        tax = {str(severity): int(total) for severity, total in tax_rows}
        pending_tax = int((await self.legacy_db.scalar(select(func.count(TaxLedgerEntry.id)).where(*ledger_filters, TaxLedgerEntry.reconciliation_status.in_(["pending", "warning", "mismatch"])))) or 0)
        tax_blockers = tax.get("blocker", 0) + tax.get("error", 0)
        latest_tax = await self.legacy_db.scalar(select(func.max(TaxLedgerEntry.updated_at)).where(*ledger_filters))
        return [
            CompanyGovernanceAreaRead(
                key="operational_outbox",
                title="Event / Outbox Reconciliation",
                state="blocked" if outbox_failed else "attention" if outbox_pending else "ready",
                mode="read_only",
                source_system="legacy.operational_outbox",
                reason="Source transaction และ projection แยกกัน; หน้านี้ไม่แก้ source document",
                metrics=[
                    _metric("pending", "รอประมวลผล", outbox_pending, "warning" if outbox_pending else "info"),
                    _metric("failed", "ล้มเหลว", outbox_failed, "blocker" if outbox_failed else "info"),
                    _metric("processed", "ประมวลผลแล้ว", outbox.get("processed", 0)),
                ],
                updated_at=latest_outbox,
                stale=bool(outbox_pending and latest_outbox and now - latest_outbox > STALE_AFTER),
            ),
            CompanyGovernanceAreaRead(
                key="tax_reconciliation",
                title="Tax Reconciliation",
                state="blocked" if tax_blockers else "attention" if pending_tax or tax.get("warning", 0) else "ready",
                mode="read_only",
                source_system="legacy.tax_ledger",
                reason="เป็นหลักฐานตรวจเทียบเท่านั้น; เอกสารภาษีจริงและการยื่นแบบยัง HOLD",
                deep_link="/tax-center",
                metrics=[
                    _metric("blockers", "Error/Blocker", tax_blockers, "blocker" if tax_blockers else "info"),
                    _metric("warnings", "Warning", tax.get("warning", 0), "warning" if tax.get("warning", 0) else "info"),
                    _metric("pending", "Ledger รอตรวจ", pending_tax, "warning" if pending_tax else "info"),
                ],
                updated_at=latest_tax,
            ),
        ]

    async def _evidence_areas(
        self,
        current: TokenData,
        now: datetime,
    ) -> tuple[list[CompanyGovernanceAreaRead], bool]:
        session_filters = [PhysicalUATSession.company_id == current.company_id, PhysicalUATSession.release_commit == settings.uat_release_commit]
        audit_filters = [AuditLog.company_id == current.company_id]
        if "company" not in current.scope_types and "*" not in current.permissions and current.branch_id is not None:
            session_filters.append(PhysicalUATSession.branch_id == current.branch_id)
            audit_filters.append(AuditLog.branch_id == current.branch_id)
        physical_rows = list((await self.legacy_db.execute(select(PhysicalUATSession.status, func.count(PhysicalUATSession.id)).where(*session_filters).group_by(PhysicalUATSession.status))).all())
        physical = {str(state): int(total) for state, total in physical_rows}
        session_ids = select(PhysicalUATSession.id).where(*session_filters)
        failed_checks = int((await self.legacy_db.scalar(select(func.count(PhysicalUATCheck.id)).where(PhysicalUATCheck.session_id.in_(session_ids), PhysicalUATCheck.result == "fail"))) or 0)
        physical_approved = physical.get("uat_approved", 0) > 0 and failed_checks == 0
        latest_physical = await self.legacy_db.scalar(select(func.max(PhysicalUATSession.updated_at)).where(*session_filters))

        identity_audit_count = int((await self.identity_db.scalar(select(func.count(AuditLog.id)).where(*audit_filters))) or 0)
        identity_audit_latest = await self.identity_db.scalar(select(func.max(AuditLog.created_at)).where(*audit_filters))
        legacy_audit_count = 0
        legacy_audit_latest = None
        if self.identity_db.bind is not self.legacy_db.bind:
            legacy_audit_count = int((await self.legacy_db.scalar(select(func.count(AuditLog.id)).where(*audit_filters))) or 0)
            legacy_audit_latest = await self.legacy_db.scalar(select(func.max(AuditLog.created_at)).where(*audit_filters))
        latest_audit = max((value for value in (identity_audit_latest, legacy_audit_latest) if value is not None), default=None)
        return [
            CompanyGovernanceAreaRead(
                key="physical_uat",
                title="Physical UAT Evidence",
                state="ready" if physical_approved else "hold",
                mode="read_only",
                source_system="legacy.physical_uat",
                reason=("Release นี้มี Technical และ Business sign-off" if physical_approved else "เครื่องพิมพ์ เงินสด PromptPay Tablet และเน็ตหลุดยังต้องทดสอบกับอุปกรณ์จริง"),
                deep_link="/devices/uat-readiness",
                metrics=[
                    _metric("approved", "UAT approved", physical.get("uat_approved", 0)),
                    _metric("in_progress", "กำลังทดสอบ", physical.get("in_progress", 0)),
                    _metric("failed_checks", "Check ไม่ผ่าน", failed_checks, "blocker" if failed_checks else "info"),
                ],
                updated_at=latest_physical,
            ),
            CompanyGovernanceAreaRead(
                key="audit_evidence",
                title="Audit & Evidence",
                state="ready" if identity_audit_count + legacy_audit_count else "attention",
                mode="read_only",
                source_system="platform+operational.audit",
                reason="หลักฐานรวมสอง boundary และปิดบัง password/token/secret/PIN/OTP",
                deep_link="/company/audit",
                metrics=[_metric("events", "Audit events", identity_audit_count + legacy_audit_count)],
                updated_at=latest_audit,
                stale=bool(latest_audit and now - latest_audit > timedelta(days=7)),
            ),
            CompanyGovernanceAreaRead(
                key="incident_management",
                title="Incident Management",
                state="planned",
                mode="planned",
                source_system="no_tenant_incident_contract",
                reason="ยังไม่มี Tenant Incident lifecycle ที่บันทึก owner/timeline/postmortem อย่างปลอดภัย จึงไม่มีปุ่มสร้างหรือปิด Incident",
            ),
            CompanyGovernanceAreaRead(
                key="retention_legal_hold",
                title="Retention & Legal Hold",
                state="planned",
                mode="planned",
                source_system="owner_policy_required",
                reason="มีเพียง non-executing privacy retention intent; การลบ/เก็บจริงรอ Owner policy และ destructive scope แยกต่างหาก",
            ),
        ], physical_approved

    @staticmethod
    def _release_gates(*, physical_approved: bool, tax_blockers: int) -> list[CompanyReleaseGateRead]:
        return [
            CompanyReleaseGateRead(key="software_uat", title="Software UAT", state="pass", reason="Batch A–C software gates and rollback evidence are recorded", evidence_reference="docs/scopes/BATCH-C-PHASE-GATE-03.md"),
            CompanyReleaseGateRead(key="qa_access", title="QA Access Mode", state="attention" if settings.qa_access_mode_enabled else "pass", reason=("เปิดเฉพาะ Local/UAT และต้อง revoke/delete หลัง Final QA sign-off" if settings.qa_access_mode_enabled else "QA Access Mode ปิดอยู่")),
            CompanyReleaseGateRead(key="physical_devices", title="Physical devices & network", state="pass" if physical_approved else "hold", reason=("มี approved evidence สำหรับ release ปัจจุบัน" if physical_approved else "ยังไม่มี approved physical evidence สำหรับ release ปัจจุบัน"), evidence_reference="/devices/uat-readiness"),
            CompanyReleaseGateRead(key="tax_provider", title="Payment / Refund / Tax provider", state="blocked" if tax_blockers else "hold", reason="Real provider, real tax/e-Tax และ fiscal document ยังไม่อนุมัติ"),
            CompanyReleaseGateRead(key="retail_cutover", title="Retail data-source cutover", state="hold", reason=f"UAT source={settings.retail_service_database}; Production cutover ไม่ได้รับอนุมัติ"),
            CompanyReleaseGateRead(key="takeaway_writes", title="Takeaway transactions", state="hold" if not settings.takeaway_uat_transaction_writes_enabled else "attention", reason="Server write flag ต้องคงปิดจนกว่า real-data canary/Owner gate จะผ่าน"),
            CompanyReleaseGateRead(key="kitchen_writes", title="Central Kitchen transactions", state="hold" if not settings.company_kitchen_writes_enabled else "attention", reason="Stock/QC/recall writes ยังไม่อนุมัติ"),
            CompanyReleaseGateRead(key="distribution_writes", title="Distribution transactions", state="hold" if not settings.company_distribution_writes_enabled else "attention", reason="Dispatch/receive/reject/return writes ยังไม่อนุมัติ"),
            CompanyReleaseGateRead(key="chambo_data", title="Chambo real data", state="hold", reason="รอ approved dry run, reconciliation และ cutover evidence"),
            CompanyReleaseGateRead(key="retention_policy", title="Retention / Legal Hold policy", state="planned", reason="รอ Product Owner ตัดสินใจ policy; ไม่มี destructive execution"),
            CompanyReleaseGateRead(key="production", title="Production activation", state="hold", reason="WP65 อนุญาตเฉพาะ Local/UAT; ไม่มี endpoint หรือปุ่มเปิด Production"),
        ]
