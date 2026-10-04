from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import io
import json
import uuid
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.etax import TaxDocument
from app.models.integration import OperationalOutboxEvent
from app.models.payable import SupplierInvoice, WHTCertificate
from app.models.pos import SaleOrder
from app.models.purchase import Supplier
from app.models.tax_operations import TaxExportBatch, TaxLedgerEntry, TaxPeriod, TaxReconciliationIssue
from app.models.tax_settings import BranchTaxProfile, CompanyTaxProfile
from app.schemas.tax_operations import TaxExportCreate, TaxLedgerIngest, TaxPeriodAction


BANGKOK = ZoneInfo("Asia/Bangkok")
TWOPLACES = Decimal("0.01")


def q2(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class TaxOperationsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ingest(self, company_id: uuid.UUID, actor_id: uuid.UUID, data: TaxLedgerIngest) -> TaxLedgerEntry:
        await self._ensure_period_mutable(company_id, data.document_date, data.branch_id)
        if data.branch_id is not None:
            valid_branch = await self.db.scalar(
                select(BranchTaxProfile.branch_id).where(
                    BranchTaxProfile.company_id == company_id,
                    BranchTaxProfile.branch_id == data.branch_id,
                )
            )
            if valid_branch is None:
                raise HTTPException(status_code=409, detail="กรุณาตั้งค่าภาษีของสาขาก่อนรับข้อมูล")
        values = data.model_dump()
        fingerprint = payload_hash(values)
        row = await self.db.scalar(
            select(TaxLedgerEntry).where(
                TaxLedgerEntry.company_id == company_id,
                TaxLedgerEntry.source_module == data.source_module,
                TaxLedgerEntry.source_document_type == data.source_document_type,
                TaxLedgerEntry.source_document_id == data.source_document_id,
                TaxLedgerEntry.line_key == data.line_key,
                TaxLedgerEntry.tax_direction == data.tax_direction,
            ).with_for_update()
        )
        if row is None:
            row = TaxLedgerEntry(company_id=company_id, created_by=actor_id, **values)
            self.db.add(row)
        elif row.payload_sha256 == fingerprint:
            return row
        else:
            for key, value in values.items():
                setattr(row, key, value)
        row.payload_sha256 = fingerprint
        row.reconciliation_status = "pending"
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def sync_legacy(self, company_id: uuid.UUID, actor_id: uuid.UUID, year: int, month: int) -> dict[str, int]:
        start, end = month_bounds(year, month)
        await self._ensure_period_mutable(company_id, start, None)
        start_at = datetime.combine(start, datetime.min.time(), tzinfo=BANGKOK).astimezone(timezone.utc)
        end_at = datetime.combine(end, datetime.min.time(), tzinfo=BANGKOK).astimezone(timezone.utc)
        orders = (
            await self.db.scalars(
                select(SaleOrder).where(
                    SaleOrder.company_id == company_id,
                    SaleOrder.created_at >= start_at,
                    SaleOrder.created_at < end_at,
                    SaleOrder.status.in_(["completed", "partially_refunded", "refunded", "voided"]),
                )
            )
        ).all()
        events = (
            await self.db.scalars(
                select(OperationalOutboxEvent).where(
                    OperationalOutboxEvent.company_id == company_id,
                    OperationalOutboxEvent.aggregate_type == "SaleOrder",
                    OperationalOutboxEvent.aggregate_id.in_([row.id for row in orders]) if orders else False,
                ).order_by(OperationalOutboxEvent.created_at.desc())
            )
        ).all()
        event_by_order: dict[uuid.UUID, OperationalOutboxEvent] = {}
        for event in events:
            event_by_order.setdefault(event.aggregate_id, event)
        sales_count = 0
        for order in orders:
            event = event_by_order.get(order.id)
            net_total = Decimal("0") if order.status == "voided" else max(Decimal("0"), q2(order.total_amount) - q2(order.refund_amount))
            ratio = Decimal("0") if q2(order.total_amount) == 0 else net_total / q2(order.total_amount)
            net_tax = q2(q2(order.vat_amount) * ratio)
            payload = TaxLedgerIngest(
                source_module="restaurant_pos" if event and event.brand_id else "retail_pos",
                tax_direction="output",
                tax_category="standard" if q2(order.vat_amount) else "zero",
                source_document_type="sale_order",
                source_document_id=str(order.id),
                source_status=order.status,
                document_number=order.order_number,
                document_date=(order.created_at if order.created_at.tzinfo else order.created_at.replace(tzinfo=timezone.utc)).astimezone(BANGKOK).date(),
                branch_id=order.branch_id,
                brand_id=event.brand_id if event else None,
                counterparty_name=order.customer_name,
                counterparty_tax_id=order.customer_tax_id,
                base_amount=q2(net_total - net_tax),
                tax_amount=net_tax,
                total_amount=q2(net_total),
                vat_rate=q2(order.vat_rate),
                status="reversed" if order.status in {"voided", "refunded"} else "posted",
                source_event_id=str(event.id) if event else None,
                source_event_at=event.created_at if event else order.updated_at,
            )
            await self._upsert_without_commit(company_id, actor_id, payload)
            sales_count += 1

        invoices = (
            await self.db.scalars(
                select(SupplierInvoice)
                .where(
                    SupplierInvoice.company_id == company_id,
                    SupplierInvoice.invoice_date >= start,
                    SupplierInvoice.invoice_date < end,
                    SupplierInvoice.deleted_at.is_(None),
                )
                .options(selectinload(SupplierInvoice.supplier))
            )
        ).all()
        purchase_count = 0
        for invoice in invoices:
            supplier = invoice.supplier
            payload = TaxLedgerIngest(
                source_module="purchasing",
                tax_direction="input",
                tax_category="standard" if q2(invoice.vat_amount) else "zero",
                source_document_type="supplier_invoice",
                source_document_id=str(invoice.id),
                source_status=invoice.status,
                document_number=invoice.tax_invoice_number or invoice.supplier_ref or invoice.invoice_number,
                document_date=invoice.tax_invoice_date or invoice.invoice_date,
                branch_id=invoice.branch_id,
                counterparty_name=supplier.name,
                counterparty_tax_id=supplier.tax_id,
                counterparty_branch_code=supplier.branch_code,
                base_amount=q2(invoice.subtotal),
                tax_amount=q2(invoice.vat_amount),
                total_amount=q2(invoice.subtotal + invoice.vat_amount),
                vat_rate=q2((invoice.vat_amount / invoice.subtotal * 100) if invoice.subtotal else 0),
                status="reversed" if invoice.status == "cancelled" else ("posted" if invoice.input_vat_claimable else "excluded"),
                source_event_at=invoice.updated_at,
            )
            await self._upsert_without_commit(company_id, actor_id, payload)
            purchase_count += 1

        self._audit(company_id, None, actor_id, "tax.ledger.legacy_synced", "TaxLedgerEntry", None, {"year": year, "month": month, "sales": sales_count, "purchases": purchase_count})
        await self.db.commit()
        return {"sales": sales_count, "purchases": purchase_count}

    async def dashboard(self, company_id: uuid.UUID, year: int, month: int, branch_id: uuid.UUID | None) -> dict[str, object]:
        start, end = month_bounds(year, month)
        filters = [TaxLedgerEntry.company_id == company_id, TaxLedgerEntry.document_date >= start, TaxLedgerEntry.document_date < end]
        if branch_id is not None:
            filters.append(TaxLedgerEntry.branch_id == branch_id)
        ledger = (await self.db.scalars(select(TaxLedgerEntry).where(*filters).order_by(TaxLedgerEntry.document_date.desc(), TaxLedgerEntry.document_number.desc()))).all()
        issue_filters = [TaxReconciliationIssue.company_id == company_id, TaxReconciliationIssue.period_year == year, TaxReconciliationIssue.period_month == month]
        export_filters = [TaxExportBatch.company_id == company_id, TaxExportBatch.period_year == year, TaxExportBatch.period_month == month]
        if branch_id is not None:
            issue_filters.append(TaxReconciliationIssue.branch_id == branch_id)
            export_filters.append(TaxExportBatch.branch_id == branch_id)
        issues = (await self.db.scalars(select(TaxReconciliationIssue).where(*issue_filters).order_by(TaxReconciliationIssue.severity.desc(), TaxReconciliationIssue.created_at.desc()))).all()
        exports = (await self.db.scalars(select(TaxExportBatch).where(*export_filters).order_by(TaxExportBatch.generated_at.desc()))).all()
        period = await self._get_period(company_id, year, month, branch_id, create=False)
        output = [row for row in ledger if row.tax_direction == "output" and row.status == "posted"]
        input_rows = [row for row in ledger if row.tax_direction == "input" and row.status == "posted"]
        wht_filters = [WHTCertificate.company_id == company_id, WHTCertificate.issue_date >= start, WHTCertificate.issue_date < end]
        if branch_id is not None:
            wht_filters.append(WHTCertificate.branch_id == branch_id)
        wht = (await self.db.scalars(select(WHTCertificate).where(*wht_filters).options(selectinload(WHTCertificate.supplier)))).all()
        blockers = len([row for row in issues if row.status == "open" and row.severity in {"error", "blocker"}])
        pending = len([row for row in ledger if row.reconciliation_status == "pending"])
        return {
            "year": year, "month": month, "branch_id": str(branch_id) if branch_id else None,
            "summary": {
                "output_base": str(q2(sum((row.base_amount for row in output), Decimal("0")))),
                "output_tax": str(q2(sum((row.tax_amount for row in output), Decimal("0")))),
                "input_base": str(q2(sum((row.base_amount for row in input_rows), Decimal("0")))),
                "input_tax": str(q2(sum((row.tax_amount for row in input_rows), Decimal("0")))),
                "net_tax": str(q2(sum((row.tax_amount for row in output), Decimal("0")) - sum((row.tax_amount for row in input_rows), Decimal("0")))),
                "wht_amount": str(q2(sum((row.wht_amount for row in wht), Decimal("0")))),
            },
            "period": self._period_dict(period),
            "ledger": [self._ledger_dict(row) for row in ledger],
            "issues": [self._issue_dict(row) for row in issues],
            "wht": [{"id": str(row.id), "certificate_number": row.certificate_number, "issue_date": row.issue_date.isoformat(), "supplier_name": row.supplier.name, "supplier_tax_id": row.supplier.tax_id, "tax_entity_type": row.supplier.tax_entity_type, "wht_type": row.wht_type, "base_amount": str(q2(row.base_amount)), "wht_amount": str(q2(row.wht_amount))} for row in wht],
            "exports": [self._export_dict(row) for row in exports],
            "readiness": {"ready_to_close": blockers == 0 and pending == 0, "open_blockers": blockers, "open_warnings": len([row for row in issues if row.status == "open" and row.severity == "warning"]), "pending_reconciliation": pending, "configured": await self._configuration_ready(company_id, branch_id)},
        }

    async def reconcile(self, company_id: uuid.UUID, actor_id: uuid.UUID, year: int, month: int, branch_id: uuid.UUID | None) -> dict[str, int]:
        start, end = month_bounds(year, month)
        filters = [TaxLedgerEntry.company_id == company_id, TaxLedgerEntry.document_date >= start, TaxLedgerEntry.document_date < end]
        if branch_id is not None:
            filters.append(TaxLedgerEntry.branch_id == branch_id)
        ledger = (await self.db.scalars(select(TaxLedgerEntry).where(*filters))).all()
        detected: dict[str, dict[str, object]] = {}
        issue_salt = f"{year:04d}-{month:02d}|{branch_id or 'company'}"

        def detect(
            code: str,
            severity: str,
            source_type: str | None,
            source_id: str | None,
            message: str,
            expected: str | None = None,
            actual: str | None = None,
        ) -> None:
            self._detect(
                detected,
                code,
                severity,
                source_type,
                source_id,
                message,
                expected,
                actual,
                salt=issue_salt,
            )

        profile = await self.db.scalar(select(CompanyTaxProfile).where(CompanyTaxProfile.company_id == company_id))
        if profile is None or (profile.vat_registered and not profile.tax_id):
            detect("COMPANY_TAX_PROFILE", "blocker", None, None, "ข้อมูลภาษีบริษัทไม่ครบ")
        elif not profile.vat_registered and any(row.status == "posted" and row.tax_amount > 0 for row in ledger):
            detect("VAT_REGISTRATION_MISMATCH", "blocker", None, None, "พบยอด VAT แต่บริษัทถูกตั้งค่าเป็นกิจการไม่จด VAT")
        branch_ids = {row.branch_id for row in ledger if row.branch_id is not None}
        configured_branches = set((await self.db.scalars(select(BranchTaxProfile.branch_id).where(BranchTaxProfile.company_id == company_id, BranchTaxProfile.branch_id.in_(branch_ids)))).all()) if branch_ids else set()
        for missing in branch_ids - configured_branches:
            detect("BRANCH_TAX_PROFILE", "blocker", "branch", str(missing), "สาขาที่มียอดขาย/ซื้อยังไม่ได้ตั้งค่าภาษี")

        for row in ledger:
            if row.tax_direction == "output":
                docs = (
                    await self.db.scalars(
                        select(TaxDocument)
                        .where(
                            TaxDocument.company_id == company_id,
                            TaxDocument.reference_id == row.source_document_id,
                        )
                        .order_by(TaxDocument.created_at.desc())
                    )
                ).all()
                active_invoice = next(
                    (
                        doc
                        for doc in docs
                        if doc.document_type in {"full_tax_invoice", "abbreviated_tax_invoice"}
                        and doc.status == "issued"
                    ),
                    None,
                )
                cancelled_invoice = next(
                    (
                        doc
                        for doc in docs
                        if doc.document_type in {"full_tax_invoice", "abbreviated_tax_invoice"}
                        and doc.status == "cancelled"
                    ),
                    None,
                )
                credit_note = next(
                    (doc for doc in docs if doc.document_type == "credit_note" and doc.status == "issued"),
                    None,
                )
                if row.status == "reversed" and (credit_note is not None or cancelled_invoice is not None):
                    row.tax_document_id = (credit_note or cancelled_invoice).id
                    row.reconciliation_status = "matched"
                elif row.status == "reversed" and active_invoice is not None:
                    row.reconciliation_status = "mismatch"
                    detect("ETAX_REVERSAL_MISSING", "error", row.source_document_type, row.source_document_id, f"ยอดขาย {row.document_number} ถูกยกเลิก/คืนเงิน แต่เอกสารภาษียังมีผล")
                elif active_invoice is None and cancelled_invoice is None:
                    row.reconciliation_status = "warning"
                    detect("ETAX_MISSING", "warning", row.source_document_type, row.source_document_id, f"ยังไม่พบเอกสารภาษีสำหรับ {row.document_number}")
                elif active_invoice is None and cancelled_invoice is not None:
                    row.reconciliation_status = "mismatch"
                    detect("ETAX_CANCELLED", "error", row.source_document_type, row.source_document_id, f"เอกสารภาษี {cancelled_invoice.document_number} ถูกยกเลิกแต่ยอดขายยังใช้งาน")
                elif active_invoice is not None and abs(q2(active_invoice.total_amount) - q2(row.total_amount)) > Decimal("0.02"):
                    row.reconciliation_status = "mismatch"
                    detect("ETAX_AMOUNT_MISMATCH", "error", row.source_document_type, row.source_document_id, f"ยอดขายและ e-Tax ของ {row.document_number} ไม่ตรงกัน", str(q2(row.total_amount)), str(q2(active_invoice.total_amount)))
                elif active_invoice is not None:
                    row.tax_document_id = active_invoice.id
                    row.reconciliation_status = "matched"
            elif row.status == "posted" and row.tax_amount > 0:
                missing = []
                if not row.counterparty_tax_id:
                    missing.append("เลขผู้เสียภาษีผู้ขาย")
                elif len("".join(char for char in row.counterparty_tax_id if char.isdigit())) != 13:
                    missing.append("เลขผู้เสียภาษีผู้ขาย 13 หลัก")
                invoice = None
                if row.source_document_type == "supplier_invoice":
                    try:
                        invoice = await self.db.get(SupplierInvoice, uuid.UUID(row.source_document_id))
                    except ValueError:
                        invoice = None
                if invoice is not None and not invoice.tax_invoice_number:
                    missing.append("เลขใบกำกับภาษี")
                if missing:
                    row.reconciliation_status = "mismatch"
                    detect("INPUT_TAX_EVIDENCE", "error", row.source_document_type, row.source_document_id, f"หลักฐานภาษีซื้อไม่ครบ: {', '.join(missing)}")
                else:
                    row.reconciliation_status = "matched"

        wht_rows = (await self.db.execute(select(WHTCertificate, Supplier).join(Supplier, Supplier.id == WHTCertificate.supplier_id).where(WHTCertificate.company_id == company_id, WHTCertificate.issue_date >= start, WHTCertificate.issue_date < end))).all()
        for cert, supplier in wht_rows:
            if supplier.tax_entity_type == "unknown":
                detect("WHT_ENTITY_UNKNOWN", "blocker", "wht_certificate", str(cert.id), f"ยังไม่ระบุประเภทบุคคลของผู้ขาย {supplier.name} สำหรับ ภ.ง.ด.3/53")

        existing = (await self.db.scalars(select(TaxReconciliationIssue).where(TaxReconciliationIssue.company_id == company_id, TaxReconciliationIssue.period_year == year, TaxReconciliationIssue.period_month == month))).all()
        existing_map = {row.fingerprint: row for row in existing}
        now = datetime.now(timezone.utc)
        for fingerprint, item in detected.items():
            row = existing_map.get(fingerprint)
            if row is None:
                row = TaxReconciliationIssue(company_id=company_id, branch_id=branch_id, period_year=year, period_month=month, fingerprint=fingerprint, **item)
                self.db.add(row)
            else:
                self._refresh_detected_issue(row, item)
        for row in existing:
            if row.fingerprint not in detected and row.status == "open":
                row.status = "resolved"
                row.resolved_at = now
                row.resolved_by = actor_id
                row.resolution_note = "แก้ไขแล้วจากการกระทบยอดล่าสุด"
        self._audit(company_id, branch_id, actor_id, "tax.reconciliation.completed", "TaxReconciliationIssue", None, {"year": year, "month": month, "detected": len(detected)})
        await self.db.commit()
        return {"detected": len(detected), "blockers": len([item for item in detected.values() if item["severity"] in {"error", "blocker"}])}

    async def change_period(self, company_id: uuid.UUID, actor_id: uuid.UUID, action: str, data: TaxPeriodAction) -> TaxPeriod:
        period = await self._get_period(company_id, data.year, data.month, data.branch_id, create=True)
        assert period is not None
        if action == "review":
            if period.status not in {"open", "review"}:
                raise HTTPException(status_code=409, detail="งวดที่ปิดแล้วไม่สามารถส่งตรวจได้")
            await self._snapshot_period(period)
            period.status = "review"
            period.reviewed_at = datetime.now(timezone.utc)
            period.reviewed_by = actor_id
        elif action == "close":
            if period.status != "review":
                raise HTTPException(status_code=409, detail="ต้องส่งตรวจงวดก่อนปิดงวด")
            if period.reviewed_by == actor_id:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "maker_checker_conflict",
                        "message": "Tax period reviewer and closer must be different users",
                    },
                )
            blocking = await self.db.scalar(select(func.count(TaxReconciliationIssue.id)).where(TaxReconciliationIssue.company_id == company_id, TaxReconciliationIssue.period_year == data.year, TaxReconciliationIssue.period_month == data.month, TaxReconciliationIssue.status == "open", TaxReconciliationIssue.severity.in_(["error", "blocker"]), TaxReconciliationIssue.branch_id == data.branch_id if data.branch_id else True))
            if blocking:
                raise HTTPException(status_code=409, detail=f"ยังมีปัญหาภาษีที่ต้องแก้ {blocking} รายการ")
            start, end = month_bounds(data.year, data.month)
            pending_filters = [
                TaxLedgerEntry.company_id == company_id,
                TaxLedgerEntry.document_date >= start,
                TaxLedgerEntry.document_date < end,
                TaxLedgerEntry.reconciliation_status == "pending",
            ]
            if data.branch_id is not None:
                pending_filters.append(TaxLedgerEntry.branch_id == data.branch_id)
            pending = await self.db.scalar(select(func.count(TaxLedgerEntry.id)).where(*pending_filters))
            if pending:
                raise HTTPException(status_code=409, detail=f"ยังมีรายการรอกระทบยอด {pending} รายการ")
            if not await self._configuration_ready(company_id, data.branch_id):
                raise HTTPException(status_code=409, detail="ข้อมูลภาษีบริษัทหรือสาขายังไม่ครบ")
            await self._snapshot_period(period)
            period.status = "closed"
            period.closed_at = datetime.now(timezone.utc)
            period.closed_by = actor_id
        elif action == "reopen":
            if period.status not in {"closed", "locked"}:
                raise HTTPException(status_code=409, detail="งวดนี้ยังไม่ได้ปิด")
            if not (data.reason or "").strip():
                raise HTTPException(status_code=422, detail="กรุณาระบุเหตุผลการเปิดงวดใหม่")
            period.status = "open"
            period.reopened_at = datetime.now(timezone.utc)
            period.reopened_by = actor_id
            period.reopen_reason = data.reason
        else:
            raise HTTPException(status_code=400, detail="Unsupported period action")
        self._audit(company_id, data.branch_id, actor_id, f"tax.period.{action}", "TaxPeriod", period.id, {"year": data.year, "month": data.month, "reason": data.reason})
        await self.db.commit()
        await self.db.refresh(period)
        return period

    async def resolve_issue(self, company_id: uuid.UUID, actor_id: uuid.UUID, issue_id: uuid.UUID, issue_status: str, note: str) -> TaxReconciliationIssue:
        row = await self.db.scalar(select(TaxReconciliationIssue).where(TaxReconciliationIssue.id == issue_id, TaxReconciliationIssue.company_id == company_id).with_for_update())
        if row is None:
            raise HTTPException(status_code=404, detail="ไม่พบรายการตรวจสอบ")
        if row.severity in {"error", "blocker"}:
            raise HTTPException(status_code=409, detail="รายการระดับ error/blocker ต้องแก้ข้อมูลต้นทางแล้วกระทบยอดใหม่")
        row.status = issue_status
        row.resolved_at = datetime.now(timezone.utc)
        row.resolved_by = actor_id
        row.resolution_note = note
        self._audit(company_id, row.branch_id, actor_id, "tax.issue.resolved", "TaxReconciliationIssue", row.id, {"status": issue_status, "note": note})
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def create_export(self, company_id: uuid.UUID, actor_id: uuid.UUID, data: TaxExportCreate) -> TaxExportBatch:
        start, end = month_bounds(data.year, data.month)
        ledger_filters = [TaxLedgerEntry.company_id == company_id, TaxLedgerEntry.document_date >= start, TaxLedgerEntry.document_date < end]
        if data.branch_id is not None:
            ledger_filters.append(TaxLedgerEntry.branch_id == data.branch_id)
        ledger = (await self.db.scalars(select(TaxLedgerEntry).where(*ledger_filters).order_by(TaxLedgerEntry.document_date, TaxLedgerEntry.document_number))).all()
        content, row_count, base_amount, tax_amount, content_type = await self._render_export(company_id, data, ledger)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        ext = "json" if content_type == "application/json" else "csv"
        filename = f"{data.export_type}_{data.year}_{data.month:02d}.{ext}"
        old = (await self.db.scalars(select(TaxExportBatch).where(TaxExportBatch.company_id == company_id, TaxExportBatch.period_year == data.year, TaxExportBatch.period_month == data.month, TaxExportBatch.branch_id == data.branch_id, TaxExportBatch.export_type == data.export_type, TaxExportBatch.status == "generated"))).all()
        for row in old:
            row.status = "superseded"
        batch = TaxExportBatch(company_id=company_id, branch_id=data.branch_id, period_year=data.year, period_month=data.month, export_type=data.export_type, filename=filename, row_count=row_count, base_amount=base_amount, tax_amount=tax_amount, content_sha256=digest, content_type=content_type, payload={"content": content}, generated_by=actor_id, generated_at=datetime.now(timezone.utc), reason=data.reason)
        self.db.add(batch)
        await self.db.flush()
        self._audit(company_id, data.branch_id, actor_id, "tax.export.generated", "TaxExportBatch", batch.id, {"type": data.export_type, "sha256": digest, "rows": row_count})
        await self.db.commit()
        await self.db.refresh(batch)
        return batch

    async def get_export(self, company_id: uuid.UUID, export_id: uuid.UUID) -> TaxExportBatch:
        row = await self.db.scalar(select(TaxExportBatch).where(TaxExportBatch.id == export_id, TaxExportBatch.company_id == company_id))
        if row is None:
            raise HTTPException(status_code=404, detail="ไม่พบไฟล์ภาษี")
        return row

    async def _upsert_without_commit(self, company_id: uuid.UUID, actor_id: uuid.UUID, data: TaxLedgerIngest) -> TaxLedgerEntry:
        row = await self.db.scalar(select(TaxLedgerEntry).where(TaxLedgerEntry.company_id == company_id, TaxLedgerEntry.source_module == data.source_module, TaxLedgerEntry.source_document_type == data.source_document_type, TaxLedgerEntry.source_document_id == data.source_document_id, TaxLedgerEntry.line_key == data.line_key, TaxLedgerEntry.tax_direction == data.tax_direction))
        values = data.model_dump()
        digest = payload_hash(values)
        if row is None:
            row = TaxLedgerEntry(company_id=company_id, created_by=actor_id, **values)
            self.db.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        row.payload_sha256 = digest
        row.reconciliation_status = "pending"
        return row

    async def _ensure_period_mutable(self, company_id: uuid.UUID, document_date: date, branch_id: uuid.UUID | None) -> None:
        conditions = [TaxPeriod.company_id == company_id, TaxPeriod.period_year == document_date.year, TaxPeriod.period_month == document_date.month, TaxPeriod.status.in_(["closed", "locked"])]
        if branch_id is not None:
            conditions.append(or_(TaxPeriod.branch_id == branch_id, TaxPeriod.branch_id.is_(None)))
        row = await self.db.scalar(select(TaxPeriod.id).where(*conditions))
        if row is not None:
            raise HTTPException(status_code=409, detail="งวดภาษีนี้ปิดแล้ว กรุณาเปิดงวดใหม่ก่อนแก้ข้อมูล")

    async def _get_period(self, company_id: uuid.UUID, year: int, month: int, branch_id: uuid.UUID | None, *, create: bool) -> TaxPeriod | None:
        scope_key = str(branch_id) if branch_id else "company"
        row = await self.db.scalar(select(TaxPeriod).where(TaxPeriod.company_id == company_id, TaxPeriod.scope_key == scope_key, TaxPeriod.period_year == year, TaxPeriod.period_month == month).with_for_update())
        if row is None and create:
            row = TaxPeriod(company_id=company_id, branch_id=branch_id, filing_scope="branch" if branch_id else "company", scope_key=scope_key, period_year=year, period_month=month, status="open")
            self.db.add(row)
            await self.db.flush()
        return row

    async def _snapshot_period(self, period: TaxPeriod) -> None:
        start, end = month_bounds(period.period_year, period.period_month)
        filters = [TaxLedgerEntry.company_id == period.company_id, TaxLedgerEntry.document_date >= start, TaxLedgerEntry.document_date < end, TaxLedgerEntry.status == "posted"]
        if period.branch_id is not None:
            filters.append(TaxLedgerEntry.branch_id == period.branch_id)
        rows = (await self.db.scalars(select(TaxLedgerEntry).where(*filters).order_by(TaxLedgerEntry.id))).all()
        output = [row for row in rows if row.tax_direction == "output"]
        input_rows = [row for row in rows if row.tax_direction == "input"]
        period.output_base_amount = q2(sum((row.base_amount for row in output), Decimal("0")))
        period.output_tax_amount = q2(sum((row.tax_amount for row in output), Decimal("0")))
        period.input_base_amount = q2(sum((row.base_amount for row in input_rows), Decimal("0")))
        period.input_tax_amount = q2(sum((row.tax_amount for row in input_rows), Decimal("0")))
        period.net_tax_amount = q2(period.output_tax_amount - period.input_tax_amount)
        period.ledger_sha256 = payload_hash([{"id": str(row.id), "hash": row.payload_sha256, "status": row.status} for row in rows])

    async def _configuration_ready(self, company_id: uuid.UUID, branch_id: uuid.UUID | None) -> bool:
        company = await self.db.scalar(select(CompanyTaxProfile).where(CompanyTaxProfile.company_id == company_id))
        if company is None:
            return False
        if branch_id is None:
            return True
        branch = await self.db.scalar(select(BranchTaxProfile.id).where(BranchTaxProfile.company_id == company_id, BranchTaxProfile.branch_id == branch_id))
        return branch is not None

    def _detect(self, result: dict[str, dict[str, object]], code: str, severity: str, source_type: str | None, source_id: str | None, message: str, expected: str | None = None, actual: str | None = None, *, salt: str = "") -> None:
        fingerprint = hashlib.sha256(f"{salt}|{code}|{source_type}|{source_id}".encode()).hexdigest()
        result[fingerprint] = {"issue_code": code, "severity": severity, "status": "open", "source_document_type": source_type, "source_document_id": source_id, "message": message, "expected_value": expected, "actual_value": actual}

    @staticmethod
    def _refresh_detected_issue(row: TaxReconciliationIssue, item: dict[str, object]) -> None:
        ignored = row.status == "ignored"
        for key, value in item.items():
            if ignored and key == "status":
                continue
            setattr(row, key, value)
        if not ignored:
            row.status = "open"
            row.resolved_at = None
            row.resolved_by = None
            row.resolution_note = None

    async def _render_export(self, company_id: uuid.UUID, data: TaxExportCreate, ledger: list[TaxLedgerEntry]) -> tuple[str, int, Decimal, Decimal, str]:
        if data.export_type in {"vat_sales", "vat_purchases"}:
            direction = "output" if data.export_type == "vat_sales" else "input"
            rows = [row for row in ledger if row.tax_direction == direction and row.status == "posted"]
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["date", "document_no", "counterparty", "tax_id", "branch", "base_amount", "vat_rate", "vat_amount", "total_amount", "source_module"])
            for row in rows:
                writer.writerow([row.document_date.isoformat(), row.document_number, row.counterparty_name or "", row.counterparty_tax_id or "", row.counterparty_branch_code or "", q2(row.base_amount), q2(row.vat_rate), q2(row.tax_amount), q2(row.total_amount), row.source_module])
            return "\ufeff" + buffer.getvalue(), len(rows), q2(sum((row.base_amount for row in rows), Decimal("0"))), q2(sum((row.tax_amount for row in rows), Decimal("0"))), "text/csv"
        if data.export_type == "pp30_summary":
            output = [row for row in ledger if row.tax_direction == "output" and row.status == "posted"]
            input_rows = [row for row in ledger if row.tax_direction == "input" and row.status == "posted"]
            values = [["period", f"{data.year}-{data.month:02d}"], ["output_base", q2(sum((row.base_amount for row in output), Decimal("0")))], ["output_vat", q2(sum((row.tax_amount for row in output), Decimal("0")))], ["input_base", q2(sum((row.base_amount for row in input_rows), Decimal("0")))], ["input_vat", q2(sum((row.tax_amount for row in input_rows), Decimal("0")))]]
            buffer = io.StringIO(); writer = csv.writer(buffer); writer.writerows(values)
            return "\ufeff" + buffer.getvalue(), len(values), q2(sum((row.base_amount for row in output), Decimal("0"))), q2(sum((row.tax_amount for row in output), Decimal("0")) - sum((row.tax_amount for row in input_rows), Decimal("0"))), "text/csv"
        if data.export_type in {"wht_pnd3", "wht_pnd53"}:
            start, end = month_bounds(data.year, data.month)
            entity = "individual" if data.export_type == "wht_pnd3" else "juristic"
            query = select(WHTCertificate, Supplier).join(Supplier, Supplier.id == WHTCertificate.supplier_id).where(WHTCertificate.company_id == company_id, WHTCertificate.issue_date >= start, WHTCertificate.issue_date < end, Supplier.tax_entity_type == entity)
            if data.branch_id is not None:
                query = query.where(WHTCertificate.branch_id == data.branch_id)
            rows = (await self.db.execute(query.order_by(WHTCertificate.issue_date, WHTCertificate.certificate_number))).all()
            buffer = io.StringIO(); writer = csv.writer(buffer); writer.writerow(["issue_date", "certificate_no", "supplier", "tax_id", "income_type", "rate", "base_amount", "wht_amount"])
            for cert, supplier in rows:
                writer.writerow([cert.issue_date.isoformat(), cert.certificate_number, supplier.name, supplier.tax_id or "", cert.income_type or cert.wht_type, q2(cert.wht_rate), q2(cert.base_amount), q2(cert.wht_amount)])
            return "\ufeff" + buffer.getvalue(), len(rows), q2(sum((cert.base_amount for cert, _ in rows), Decimal("0"))), q2(sum((cert.wht_amount for cert, _ in rows), Decimal("0"))), "text/csv"
        if data.export_type == "etax_manifest":
            docs = (await self.db.scalars(select(TaxDocument).where(TaxDocument.company_id == company_id, TaxDocument.issue_date >= month_bounds(data.year, data.month)[0], TaxDocument.issue_date < month_bounds(data.year, data.month)[1]).order_by(TaxDocument.issue_date, TaxDocument.document_number))).all()
            manifest = [{"document_number": row.document_number, "document_type": row.document_type, "status": row.status, "issue_date": row.issue_date.isoformat(), "total_amount": str(q2(row.total_amount)), "xml_sha256": row.xml_hash} for row in docs]
            content = json.dumps(manifest, ensure_ascii=False, indent=2)
            return content, len(docs), q2(sum((row.subtotal for row in docs), Decimal("0"))), q2(sum((row.vat_amount for row in docs), Decimal("0"))), "application/json"
        archive = {"period": f"{data.year}-{data.month:02d}", "branch_id": str(data.branch_id) if data.branch_id else None, "ledger_sha256": payload_hash([self._ledger_dict(row) for row in ledger]), "ledger_rows": len(ledger), "generated_at": datetime.now(timezone.utc).isoformat(), "note": "Archive manifest only; official submission is outside this system."}
        content = json.dumps(archive, ensure_ascii=False, indent=2)
        return content, len(ledger), q2(sum((row.base_amount for row in ledger if row.status == "posted"), Decimal("0"))), q2(sum((row.tax_amount for row in ledger if row.status == "posted"), Decimal("0"))), "application/json"

    def _audit(self, company_id: uuid.UUID, branch_id: uuid.UUID | None, actor_id: uuid.UUID, action: str, resource: str, resource_id: uuid.UUID | None, value: dict[str, object]) -> None:
        self.db.add(AuditLog(company_id=company_id, branch_id=branch_id, user_id=actor_id, action=action, resource=resource, resource_id=str(resource_id) if resource_id else None, new_value=value))

    @staticmethod
    def _ledger_dict(row: TaxLedgerEntry) -> dict[str, object]:
        return {"id": str(row.id), "branch_id": str(row.branch_id) if row.branch_id else None, "brand_id": str(row.brand_id) if row.brand_id else None, "source_module": row.source_module, "tax_direction": row.tax_direction, "tax_category": row.tax_category, "document_number": row.document_number, "document_date": row.document_date.isoformat(), "counterparty_name": row.counterparty_name, "counterparty_tax_id": row.counterparty_tax_id, "base_amount": str(q2(row.base_amount)), "tax_amount": str(q2(row.tax_amount)), "total_amount": str(q2(row.total_amount)), "vat_rate": str(q2(row.vat_rate)), "status": row.status, "reconciliation_status": row.reconciliation_status, "source_document_type": row.source_document_type, "source_document_id": row.source_document_id}

    @staticmethod
    def _period_dict(row: TaxPeriod | None) -> dict[str, object]:
        if row is None:
            return {"id": None, "status": "open", "ledger_sha256": None}
        return {"id": str(row.id), "status": row.status, "ledger_sha256": row.ledger_sha256, "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None, "closed_at": row.closed_at.isoformat() if row.closed_at else None, "reopened_at": row.reopened_at.isoformat() if row.reopened_at else None, "reopen_reason": row.reopen_reason}

    @staticmethod
    def _issue_dict(row: TaxReconciliationIssue) -> dict[str, object]:
        return {"id": str(row.id), "issue_code": row.issue_code, "severity": row.severity, "status": row.status, "message": row.message, "source_document_type": row.source_document_type, "source_document_id": row.source_document_id, "expected_value": row.expected_value, "actual_value": row.actual_value, "resolution_note": row.resolution_note}

    @staticmethod
    def _export_dict(row: TaxExportBatch) -> dict[str, object]:
        return {"id": str(row.id), "export_type": row.export_type, "status": row.status, "filename": row.filename, "row_count": row.row_count, "base_amount": str(q2(row.base_amount)), "tax_amount": str(q2(row.tax_amount)), "content_sha256": row.content_sha256, "generated_at": row.generated_at.isoformat()}
