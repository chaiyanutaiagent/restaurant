from __future__ import annotations

from datetime import date, datetime, time, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import TokenData
from app.models.branch import Branch
from app.models.payable import SupplierInvoice
from app.models.purchase import PurchaseOrder
from app.models.stock_count import StockCountSession
from app.models.tax_operations import TaxLedgerEntry, TaxPeriod, TaxReconciliationIssue
from app.models.transfer import TransferOrder
from app.schemas.company_foundation import (
    CompanyErpControlRead,
    CompanyErpExceptionRead,
    CompanyErpFinanceReadinessRead,
    CompanyErpReadinessAreaRead,
    CompanyErpReadinessRead,
)
from app.services.company_context_service import CompanyContextService, scoped_branch_ids


ERP_READ_PERMISSIONS = {
    "system.company.edit",
    "inventory.purchase.view",
    "inventory.purchase.approve",
    "inventory.transfer.view",
    "inventory.transfer.approve",
    "inventory.stock.view",
    "inventory.stock.adjust",
    "accounting.report.view",
    "accounting.tax.view",
    "accounting.payment.view",
    "accounting.invoice.view",
}


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _age_hours(created_at: datetime, now: datetime) -> int:
    return max(0, int((now - _as_aware(created_at)).total_seconds() // 3600))


def _due_datetime(value: date | None) -> datetime | None:
    return datetime.combine(value, time.min, tzinfo=timezone.utc) if value is not None else None


class CompanyErpMaturityService:
    def __init__(self, identity_db: AsyncSession, operational_db: AsyncSession):
        self.identity_db = identity_db
        self.operational_db = operational_db

    @staticmethod
    def _has(permissions: set[str], *codes: str) -> bool:
        return "*" in permissions or bool(permissions.intersection(codes))

    async def read(self, current: TokenData) -> CompanyErpReadinessRead:
        permissions = set(current.permissions)
        if not self._has(permissions, *ERP_READ_PERMISSIONS):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

        now = datetime.now(timezone.utc)
        context = await CompanyContextService(self.identity_db, self.operational_db).read_context(current)
        branch_ids = await scoped_branch_ids(current, self.operational_db)
        exceptions: list[CompanyErpExceptionRead] = []
        area_counts = {"purchasing": 0, "inventory": 0, "finance_tax": 0, "reporting": 0}
        updated_at: list[datetime] = [context.updated_at]

        purchase_allowed = self._has(permissions, "inventory.purchase.view", "inventory.purchase.approve")
        transfer_allowed = self._has(permissions, "inventory.transfer.view", "inventory.transfer.approve")
        stock_allowed = self._has(permissions, "inventory.stock.view", "inventory.stock.adjust")
        finance_allowed = self._has(
            permissions,
            "accounting.report.view",
            "accounting.tax.view",
            "accounting.payment.view",
            "accounting.invoice.view",
        )
        report_allowed = self._has(permissions, "accounting.report.view", "system.company.edit")

        if purchase_allowed:
            filters = [
                PurchaseOrder.company_id == current.company_id,
                PurchaseOrder.status == "pending_approval",
                PurchaseOrder.deleted_at.is_(None),
            ]
            if branch_ids is not None:
                filters.append(PurchaseOrder.branch_id.in_(branch_ids))
            rows = (
                await self.operational_db.scalars(
                    select(PurchaseOrder).where(*filters).order_by(PurchaseOrder.created_at.asc()).limit(100)
                )
            ).all()
            for row in rows:
                updated_at.append(row.updated_at)
                exceptions.append(CompanyErpExceptionRead(
                    id=f"purchase:{row.id}", source="purchase", title="ใบสั่งซื้อรอผู้ตรวจอนุมัติ",
                    reference=row.po_number, severity="warning", branch_id=row.branch_id,
                    owner_id=row.created_by, age_hours=_age_hours(row.created_at, now),
                    due_at=_due_datetime(row.expected_date), deep_link=f"/purchase/orders/{row.id}",
                    permission_required="inventory.purchase.view", evidence_reference=f"PurchaseOrder:{row.id}",
                    created_at=row.created_at,
                ))
            area_counts["purchasing"] += len(rows)

        if transfer_allowed:
            filters = [
                TransferOrder.company_id == current.company_id,
                or_(
                    TransferOrder.status == "pending_approval",
                    TransferOrder.has_discrepancy.is_(True),
                ),
            ]
            if branch_ids is not None:
                filters.append(or_(TransferOrder.from_branch_id.in_(branch_ids), TransferOrder.to_branch_id.in_(branch_ids)))
            rows = (
                await self.operational_db.scalars(
                    select(TransferOrder).where(*filters).order_by(TransferOrder.created_at.asc()).limit(100)
                )
            ).all()
            for row in rows:
                updated_at.append(row.updated_at)
                discrepancy = bool(row.has_discrepancy)
                exceptions.append(CompanyErpExceptionRead(
                    id=f"transfer:{row.id}", source="transfer",
                    title="ผลต่างการโอนสินค้าต้องตรวจ" if discrepancy else "ใบโอนสินค้ารอผู้ตรวจอนุมัติ",
                    reference=row.to_number, severity="error" if discrepancy else "warning",
                    branch_id=row.from_branch_id, owner_id=row.requested_by,
                    age_hours=_age_hours(row.created_at, now), due_at=_due_datetime(row.expected_date),
                    deep_link=f"/transfer/orders/{row.id}", permission_required="inventory.transfer.view",
                    evidence_reference=f"TransferOrder:{row.id}", created_at=row.created_at,
                ))
            area_counts["inventory"] += len(rows)

        if stock_allowed:
            filters = [
                StockCountSession.company_id == current.company_id,
                StockCountSession.status.in_(["draft", "in_progress"]),
            ]
            if branch_ids is not None:
                filters.append(StockCountSession.branch_id.in_(branch_ids))
            rows = (
                await self.operational_db.scalars(
                    select(StockCountSession).where(*filters).order_by(StockCountSession.created_at.asc()).limit(100)
                )
            ).all()
            for row in rows:
                updated_at.append(row.updated_at)
                exceptions.append(CompanyErpExceptionRead(
                    id=f"stock_count:{row.id}", source="stock_count", title="รอบตรวจนับสต็อกยังไม่เสร็จ",
                    reference=row.session_number, severity="warning", branch_id=row.branch_id,
                    owner_id=row.created_by, age_hours=_age_hours(row.created_at, now), due_at=None,
                    deep_link=f"/stock-count/{row.id}", permission_required="inventory.stock.view",
                    evidence_reference=f"StockCountSession:{row.id}", created_at=row.created_at,
                ))
            area_counts["inventory"] += len(rows)

        if finance_allowed and self._has(permissions, "accounting.payment.view", "accounting.invoice.view", "accounting.report.view"):
            invoice_filters = [
                SupplierInvoice.company_id == current.company_id,
                SupplierInvoice.status.notin_(["paid", "cancelled"]),
                SupplierInvoice.due_date < now.date(),
                SupplierInvoice.deleted_at.is_(None),
            ]
            if branch_ids is not None:
                invoice_filters.append(SupplierInvoice.branch_id.in_(branch_ids))
            invoices = (
                await self.operational_db.scalars(
                    select(SupplierInvoice).where(*invoice_filters).order_by(SupplierInvoice.due_date.asc()).limit(100)
                )
            ).all()
            for row in invoices:
                updated_at.append(row.updated_at)
                exceptions.append(CompanyErpExceptionRead(
                    id=f"payable:{row.id}", source="payable", title="เจ้าหนี้เกินกำหนดชำระ",
                    reference=row.invoice_number, severity="error", branch_id=row.branch_id,
                    owner_id=row.created_by, age_hours=_age_hours(row.created_at, now),
                    due_at=_due_datetime(row.due_date), deep_link="/payable",
                    permission_required="accounting.payment.view", evidence_reference=f"SupplierInvoice:{row.id}",
                    created_at=row.created_at,
                ))
            area_counts["finance_tax"] += len(invoices)

        finance: CompanyErpFinanceReadinessRead | None = None
        if finance_allowed:
            tax_filters = [
                TaxReconciliationIssue.company_id == current.company_id,
                TaxReconciliationIssue.status == "open",
                TaxReconciliationIssue.period_year == now.year,
                TaxReconciliationIssue.period_month == now.month,
            ]
            if branch_ids is not None:
                tax_filters.append(TaxReconciliationIssue.branch_id.in_(branch_ids))
            issues = (
                await self.operational_db.scalars(
                    select(TaxReconciliationIssue).where(*tax_filters).order_by(TaxReconciliationIssue.created_at.asc()).limit(100)
                )
            ).all()
            for row in issues:
                updated_at.append(row.updated_at)
                exceptions.append(CompanyErpExceptionRead(
                    id=f"tax:{row.id}", source="tax", title=row.message, reference=row.issue_code,
                    severity=row.severity, branch_id=row.branch_id, owner_id=None,
                    age_hours=_age_hours(row.created_at, now), due_at=None, deep_link="/tax-center",
                    permission_required="accounting.tax.view", evidence_reference=f"TaxReconciliationIssue:{row.id}",
                    created_at=row.created_at,
                ))
            area_counts["finance_tax"] += len(issues)

            period_filters = [
                TaxPeriod.company_id == current.company_id,
                TaxPeriod.period_year == now.year,
                TaxPeriod.period_month == now.month,
            ]
            if current.branch_id is not None:
                period_filters.append(TaxPeriod.branch_id == current.branch_id)
            else:
                period_filters.append(TaxPeriod.branch_id.is_(None))
            period = await self.operational_db.scalar(select(TaxPeriod).where(*period_filters).limit(1))
            if period is not None:
                updated_at.append(period.updated_at)
            ledger_filters = [
                TaxLedgerEntry.company_id == current.company_id,
                TaxLedgerEntry.document_date >= date(now.year, now.month, 1),
                TaxLedgerEntry.reconciliation_status == "pending",
            ]
            if now.month == 12:
                next_month = date(now.year + 1, 1, 1)
            else:
                next_month = date(now.year, now.month + 1, 1)
            ledger_filters.append(TaxLedgerEntry.document_date < next_month)
            if branch_ids is not None:
                ledger_filters.append(TaxLedgerEntry.branch_id.in_(branch_ids))
            pending_reconciliation = int((await self.operational_db.scalar(
                select(func.count(TaxLedgerEntry.id)).where(*ledger_filters)
            )) or 0)
            blockers = sum(1 for row in issues if row.severity in {"error", "blocker"})
            warnings = sum(1 for row in issues if row.severity == "warning")
            period_status = period.status if period is not None else "not_started"
            signoff_recorded = bool(period and period.closed_by)
            finance = CompanyErpFinanceReadinessRead(
                period_year=now.year, period_month=now.month, period_status=period_status,
                tax_configured=context.tax.configured, open_blockers=blockers, open_warnings=warnings,
                pending_reconciliation=pending_reconciliation,
                accountant_signoff="recorded" if signoff_recorded else "pending",
                ready_to_close=(context.tax.configured and blockers == 0 and pending_reconciliation == 0 and period_status == "review"),
                deep_link="/tax-center" if self._has(permissions, "accounting.tax.view", "accounting.report.view") else None,
            )

        def area(
            key: str,
            title: str,
            allowed: bool,
            permission: str,
            deep_link: str,
            message: str,
            *,
            blocked: bool = False,
        ) -> CompanyErpReadinessAreaRead:
            count = area_counts[key]
            if not allowed:
                state = "permission_denied"
                link = None
                detail = "บทบาทปัจจุบันไม่มีสิทธิ์ดูข้อมูลส่วนนี้"
            elif blocked:
                state = "blocked"
                link = deep_link
                detail = message
            else:
                state = "attention" if count else "ready"
                link = deep_link
                detail = message if count else "ไม่พบข้อยกเว้นที่เปิดอยู่ในขอบเขตปัจจุบัน"
            return CompanyErpReadinessAreaRead(
                key=key, title=title, state=state, open_items=count,
                permission_required=permission, deep_link=link, read_only=True, message=detail,
            )

        finance_blocked = bool(finance and (not finance.tax_configured or finance.open_blockers > 0))
        areas = [
            area("purchasing", "จัดซื้อ", purchase_allowed, "inventory.purchase.view", "/purchase/orders", "มีใบสั่งซื้อรอตรวจอนุมัติ"),
            area("inventory", "คลังและโอนสินค้า", transfer_allowed or stock_allowed, "inventory.stock.view", "/stock-count", "มีงานคลังหรือผลต่างที่ต้องตรวจ"),
            area("finance_tax", "บัญชีและภาษี", finance_allowed, "accounting.report.view", "/tax-center", "มีรายการทางการเงินหรือภาษีที่ต้องจัดการ", blocked=finance_blocked),
            area("reporting", "รายงานบริหาร", report_allowed, "accounting.report.view", "/reports/company", "รายงานใช้ขอบเขต Company/Brand/Branch จาก Server"),
        ]
        exception_branch_ids = {item.branch_id for item in exceptions if item.branch_id is not None}
        branch_names = {
            row.id: row.name
            for row in (
                await self.identity_db.scalars(
                    select(Branch).where(
                        Branch.company_id == current.company_id,
                        Branch.id.in_(exception_branch_ids),
                        Branch.deleted_at.is_(None),
                    )
                )
            ).all()
        } if exception_branch_ids else {}
        exceptions = [
            item.model_copy(update={"branch_name": branch_names.get(item.branch_id)})
            for item in exceptions
        ]
        exceptions.sort(key=lambda item: ({"blocker": 0, "error": 1, "warning": 2, "info": 3}[item.severity], -item.age_hours))

        controls = [
            CompanyErpControlRead(key="purchase_maker_checker", label="ผู้สร้าง PO และผู้อนุมัติต้องเป็นคนละคน", state="enforced", detail="Server ปฏิเสธการอนุมัติรายการของตนเอง"),
            CompanyErpControlRead(key="transfer_maker_checker", label="ผู้ขอโอนและผู้อนุมัติต้องเป็นคนละคน", state="enforced", detail="Server ตรวจสอบก่อนจองสต็อก"),
            CompanyErpControlRead(key="tax_close_maker_checker", label="ผู้ส่งตรวจและผู้ปิดงวดต้องเป็นคนละคน", state="enforced", detail="Server ปฏิเสธก่อนปิดงวด"),
            CompanyErpControlRead(key="journal_reversal_maker_checker", label="ผู้ลงสมุดรายวัน manual ห้ามกลับรายการเอง", state="enforced", detail="Server ปฏิเสธก่อนสร้างรายการกลับ"),
            CompanyErpControlRead(key="real_tax_documents", label="เอกสารภาษีจริงและ e-Tax", state="hold", detail="ปิดการทำธุรกรรมจริง รออนุมัตินโยบายและผู้ให้บริการ"),
            CompanyErpControlRead(key="live_payment_provider", label="Payment/Refund provider จริง", state="hold", detail="ใช้ได้เฉพาะ sandbox/read-only ใน UAT"),
            CompanyErpControlRead(key="accountant_signoff", label="Accountant sign-off", state="hold", detail="ต้องมีผู้รับผิดชอบภายนอกยืนยันก่อน Production"),
            CompanyErpControlRead(key="retail_source_cutover", label="เปลี่ยน Retail data source", state="hold", detail="ยังไม่เปลี่ยนแหล่งข้อมูลหลัก"),
            CompanyErpControlRead(key="takeaway_central_writes", label="Takeaway/Central Kitchen transactions", state="hold", detail="ยังไม่เปิด write flags ใน Production"),
        ]
        return CompanyErpReadinessRead(
            context=context, areas=areas, exceptions=exceptions[:200], finance=finance,
            controls=controls,
            summary={
                "open_exceptions": len(exceptions),
                "blockers": sum(1 for item in exceptions if item.severity == "blocker"),
                "errors": sum(1 for item in exceptions if item.severity == "error"),
                "overdue": sum(1 for item in exceptions if item.due_at is not None and item.due_at < now),
                "holds": sum(1 for item in controls if item.state == "hold"),
            },
            source_updated_at=max((_as_aware(item) for item in updated_at), default=now),
            generated_at=now,
        )
