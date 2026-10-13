from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import uuid
import hashlib
import json

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.accounting import JournalEntry
from app.models.audit import AuditLog
from app.models.company import Company
from app.models.branch import Branch
from app.models.etax import TaxDocument
from app.models.payable import APPayment, APPaymentAllocation, SupplierInvoice, WHTCertificate
from app.models.purchase import PurchaseOrder, Supplier
from app.models.tax_operations import TaxLedgerEntry
from app.schemas.payable import CreateAPPaymentRequest, SupplierInvoiceCreate, VatReturnReport
from app.services.accounting_service import AccountingService
from app.utils.posting_rules import PostingLine
from app.utils.thai_date import MONTHS_TH
from app.utils.payable_tax import payment_tax
from app.services.document_snapshot_service import capture_payment_snapshots
from app.services.document_lifecycle_service import capture_invoice, append_event, require_reason

TWOPLACES = Decimal("0.01")


def q2(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


class PayableService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_invoice(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: SupplierInvoiceCreate,
    ) -> SupplierInvoice:
        await self._validate_branch(company_id, data.branch_id)
        supplier = await self._get_supplier(company_id, data.supplier_id)
        due_date = data.invoice_date + timedelta(days=int(supplier.payment_term_days or 0))
        total_amount = q2(Decimal(data.subtotal) + Decimal(data.vat_amount) - Decimal(data.wht_amount))
        remaining_amount = total_amount
        invoice_number = await self._generate_running_number(SupplierInvoice, company_id, "invoice_number", "SINV", data.invoice_date)

        po: PurchaseOrder | None = None
        if data.po_id is not None:
            po = await self.db.scalar(
                select(PurchaseOrder).where(
                    PurchaseOrder.id == data.po_id,
                    PurchaseOrder.company_id == company_id,
                    PurchaseOrder.deleted_at.is_(None),
                )
            )
            if po is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
            if po.supplier_id != data.supplier_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Purchase order supplier mismatch")
            if po.branch_id != data.branch_id:
                raise HTTPException(status_code=409, detail="Purchase order branch mismatch")

        invoice = SupplierInvoice(
            company_id=company_id,
            branch_id=data.branch_id,
            supplier_id=data.supplier_id,
            po_id=data.po_id,
            invoice_number=invoice_number,
            supplier_ref=data.supplier_ref,
            tax_invoice_number=data.tax_invoice_number,
            tax_invoice_date=data.tax_invoice_date,
            input_vat_claimable=data.input_vat_claimable,
            nonclaimable_reason=data.nonclaimable_reason,
            status="unpaid",
            invoice_date=data.invoice_date,
            due_date=due_date,
            subtotal=q2(data.subtotal),
            vat_amount=q2(data.vat_amount),
            wht_amount=q2(data.wht_amount),
            total_amount=total_amount,
            paid_amount=Decimal("0.00"),
            remaining_amount=remaining_amount,
            note=data.note,
            created_by=user_id,
        )
        self.db.add(invoice)
        await self.db.flush()

        accounting = AccountingService(self.db)
        await accounting._post_entry(
            company_id=company_id,
            branch_id=data.branch_id,
            user_id=user_id,
            entry_date=data.invoice_date,
            entry_type="purchase",
            description=f"ตั้งใบแจ้งหนี้เจ้าหนี้ {invoice.invoice_number}",
            lines=self._build_invoice_posting_lines(invoice),
            reference_type="SupplierInvoice",
            reference_id=str(invoice.id),
        )
        self._audit(company_id, data.branch_id, user_id, "accounting.invoice.created", "SupplierInvoice", invoice.id)
        await capture_invoice(self.db, invoice, supplier, user_id)
        await self.db.commit()
        return await self.get_invoice(invoice.id, company_id)

    async def list_invoices(
        self,
        company_id: uuid.UUID,
        supplier_id: uuid.UUID | None = None,
        status: str | None = None,
        overdue_only: bool = False,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[SupplierInvoice], int]:
        filters = [SupplierInvoice.company_id == company_id, SupplierInvoice.deleted_at.is_(None)]
        if supplier_id is not None:
            filters.append(SupplierInvoice.supplier_id == supplier_id)
        if status:
            filters.append(SupplierInvoice.status == status)
        if overdue_only:
            filters.extend(
                [
                    SupplierInvoice.due_date < date.today(),
                    SupplierInvoice.status.not_in(["paid", "cancelled"]),
                ]
            )
        if date_from is not None:
            filters.append(SupplierInvoice.invoice_date >= date_from)
        if date_to is not None:
            filters.append(SupplierInvoice.invoice_date <= date_to)

        total = int((await self.db.scalar(select(func.count(SupplierInvoice.id)).where(*filters))) or 0)
        rows = await self.db.scalars(
            select(SupplierInvoice)
            .where(*filters)
            .options(selectinload(SupplierInvoice.supplier), selectinload(SupplierInvoice.purchase_order))
            .order_by(SupplierInvoice.invoice_date.desc(), SupplierInvoice.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return rows.all(), total

    async def get_invoice(self, invoice_id: uuid.UUID, company_id: uuid.UUID) -> SupplierInvoice:
        invoice = await self.db.scalar(
            select(SupplierInvoice)
            .where(
                SupplierInvoice.id == invoice_id,
                SupplierInvoice.company_id == company_id,
                SupplierInvoice.deleted_at.is_(None),
            )
            .options(
                selectinload(SupplierInvoice.supplier),
                selectinload(SupplierInvoice.purchase_order),
                selectinload(SupplierInvoice.allocations),
            )
        )
        if invoice is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier invoice not found")
        return invoice

    async def cancel_invoice(self, invoice_id: uuid.UUID, company_id: uuid.UUID, user_id: uuid.UUID, reason: str = "") -> SupplierInvoice:
        reason = require_reason(reason)
        invoice = await self.db.scalar(select(SupplierInvoice).where(
            SupplierInvoice.id == invoice_id, SupplierInvoice.company_id == company_id,
            SupplierInvoice.deleted_at.is_(None),
        ).with_for_update().execution_options(populate_existing=True))
        if invoice is None:
            raise HTTPException(status_code=404, detail="Supplier invoice not found")
        if invoice.status != "unpaid":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only unpaid invoices can be cancelled")

        entry_id = await self.db.scalar(
            select(JournalEntry.id).where(
                JournalEntry.company_id == company_id,
                JournalEntry.reference_type == "SupplierInvoice",
                JournalEntry.reference_id == str(invoice.id),
                JournalEntry.is_reversed.is_(False),
            )
        )
        if entry_id is not None:
            await AccountingService(self.db).reverse_entry(entry_id, company_id, user_id, commit=False)

        invoice.status = "cancelled"
        invoice.paid_amount = Decimal("0.00")
        invoice.remaining_amount = Decimal("0.00")
        await append_event(self.db, invoice, "supplier_invoice", "cancelled", user_id, reason)
        self._audit(company_id, invoice.branch_id, user_id, "accounting.invoice.cancelled", "SupplierInvoice", invoice.id)
        await self.db.commit()
        return await self.get_invoice(invoice.id, company_id)

    async def create_payment(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: CreateAPPaymentRequest,
    ) -> APPayment:
        # Persist the request receipt in the same transaction as the payment.
        # Keep these audit receipts for at least the lifetime of the payment.
        fingerprint = hashlib.sha256(json.dumps(data.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
        lock_key = int.from_bytes(hashlib.sha256(f"AP_REQUEST:{company_id}:{data.idempotency_key}".encode()).digest()[:8], "big", signed=True)
        await self.db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
        receipt = await self.db.scalar(select(AuditLog).where(
            AuditLog.company_id == company_id, AuditLog.action == "accounting.payment.request",
            AuditLog.resource_id == str(data.idempotency_key),
        ))
        if receipt is not None:
            if receipt.new_value.get("fingerprint") != fingerprint or receipt.branch_id != data.branch_id:
                raise HTTPException(status_code=409, detail="รหัสคำขอเดิมมีข้อมูลต่างกัน กรุณาตรวจประวัติการจ่าย")
            return await self.get_payment(uuid.UUID(receipt.new_value["payment_id"]), company_id)
        invoices = await self._payment_invoices(company_id, data, lock=True)
        invoice_map = {invoice.id: invoice for invoice in invoices}
        calculations = {item.invoice_id: payment_tax(invoice_map[item.invoice_id], item) for item in data.allocations}

        total_allocated = Decimal("0.00")
        total_wht = Decimal("0.00")
        created_allocations: list[APPaymentAllocation] = []
        payment_number = await self._generate_running_number(APPayment, company_id, "payment_number", "PAY", data.payment_date)

        payment = APPayment(
            company_id=company_id,
            branch_id=data.branch_id,
            payment_number=payment_number,
            payment_date=data.payment_date,
            payment_method=data.payment_method,
            bank_account=data.bank_account,
            reference_no=data.reference_no,
            total_amount=Decimal("0.00"),
            note=data.note,
            created_by=user_id,
        )
        self.db.add(payment)
        await self.db.flush()

        for item in data.allocations:
            invoice = invoice_map[item.invoice_id]
            calculated = calculations[invoice.id]
            allocated_amount = calculated["allocated_amount"]
            wht_amount = calculated["wht_amount"]
            allocation = APPaymentAllocation(
                payment_id=payment.id,
                invoice_id=invoice.id,
                company_id=company_id,
                allocated_amount=allocated_amount,
                wht_amount=wht_amount,
                wht_rate=calculated["wht_rate"],
                wht_type=calculated["wht_type"],
            )
            self.db.add(allocation)
            created_allocations.append(allocation)

            invoice.paid_amount = q2(Decimal(invoice.paid_amount or 0) + allocated_amount)
            remaining = q2(Decimal(invoice.total_amount) - invoice.paid_amount)
            invoice.remaining_amount = remaining
            invoice.status = "paid" if remaining == 0 else "partial"
            total_allocated += allocated_amount
            total_wht += wht_amount

        payment.total_amount = q2(total_allocated - total_wht)
        await self.db.flush()
        await AccountingService(self.db)._post_entry(
            company_id=company_id, branch_id=data.branch_id, user_id=user_id,
            entry_date=data.payment_date, entry_type="payment",
            description=f"จ่ายเจ้าหนี้ {payment.payment_number}",
            lines=self._build_payment_posting_lines(total_allocated, total_wht, payment.total_amount, data.payment_method),
            reference_type="APPayment", reference_id=str(payment.id),
        )
        certificates: list[WHTCertificate] = []
        for allocation in created_allocations:
            if allocation.wht_amount <= 0:
                continue
            calculated = calculations[allocation.invoice_id]
            cert = WHTCertificate(
                company_id=company_id, branch_id=data.branch_id, payment_id=payment.id,
                supplier_id=invoice_map[allocation.invoice_id].supplier_id,
                certificate_number=await self._generate_running_number(WHTCertificate, company_id, "certificate_number", "WHT", data.payment_date),
                issue_date=data.payment_date, wht_type=allocation.wht_type,
                wht_rate=allocation.wht_rate, base_amount=calculated["wht_base_amount"],
                wht_amount=allocation.wht_amount, income_type=allocation.wht_type, created_by=user_id,
            )
            self.db.add(cert)
            await self.db.flush()
            certificates.append(cert)
        await capture_payment_snapshots(self.db, payment, created_allocations, invoice_map, certificates, user_id)
        self._audit(company_id, data.branch_id, user_id, "accounting.payment.created", "APPayment", payment.id)
        self.db.add(AuditLog(
            company_id=company_id, branch_id=data.branch_id, user_id=user_id,
            action="accounting.payment.request", resource="APPaymentRequest",
            resource_id=str(data.idempotency_key),
            new_value={"fingerprint": fingerprint, "payment_id": str(payment.id), "document_snapshot_version": 1},
        ))
        await self.db.commit()
        return await self.get_payment(payment.id, company_id)

    async def _validate_branch(self, company_id, branch_id):
        branch = await self.db.scalar(select(Branch.id).where(
            Branch.id == branch_id, Branch.company_id == company_id,
            Branch.deleted_at.is_(None), Branch.is_active.is_(True),
        ))
        if branch is None:
            raise HTTPException(status_code=404, detail="Branch not found")

    async def preview_payment(self, company_id, data):
        invoices = {invoice.id: invoice for invoice in await self._payment_invoices(company_id, data, lock=False)}
        rows = [payment_tax(invoices[item.invoice_id], item) for item in data.allocations]
        return {"allocations": rows, "total_allocated": sum(row["allocated_amount"] for row in rows),
                "total_wht": sum(row["wht_amount"] for row in rows),
                "net_amount": sum(row["net_amount"] for row in rows)}

    async def _payment_invoices(self, company_id, data, *, lock):
        await self._validate_branch(company_id, data.branch_id)
        if not data.allocations:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one allocation is required")

        invoice_ids = [item.invoice_id for item in data.allocations]
        if len(invoice_ids) != len(set(invoice_ids)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate invoice allocation is not allowed")

        query = (select(SupplierInvoice)
                .where(
                    SupplierInvoice.company_id == company_id,
                    SupplierInvoice.branch_id == data.branch_id,
                    SupplierInvoice.id.in_(invoice_ids),
                    SupplierInvoice.deleted_at.is_(None),
                )
                .options(selectinload(SupplierInvoice.supplier))
                .order_by(SupplierInvoice.id)
                .execution_options(populate_existing=True))
        if lock:
            query = query.with_for_update(of=SupplierInvoice)
        invoices = (await self.db.scalars(query)).all()
        invoice_map = {invoice.id: invoice for invoice in invoices}
        if len(invoice_map) != len(invoice_ids):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more invoices not found")

        supplier_ids = {invoice.supplier_id for invoice in invoices}
        if len(supplier_ids) > 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="All allocations must be for the same supplier")
        if any(data.payment_date < invoice.invoice_date for invoice in invoices):
            raise HTTPException(status_code=409, detail="วันที่จ่ายต้องไม่ก่อนวันที่ใบแจ้งหนี้")

        return invoices

    async def list_payments(self, company_id: uuid.UUID, page: int = 1, limit: int = 20) -> tuple[list[APPayment], int]:
        filters = [APPayment.company_id == company_id]
        total = int((await self.db.scalar(select(func.count(APPayment.id)).where(*filters))) or 0)
        rows = await self.db.scalars(
            select(APPayment)
            .where(*filters)
            .options(
                selectinload(APPayment.allocations)
                .selectinload(APPaymentAllocation.invoice)
                .selectinload(SupplierInvoice.supplier)
            )
            .order_by(APPayment.payment_date.desc(), APPayment.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return rows.unique().all(), total

    async def get_payment(self, payment_id: uuid.UUID, company_id: uuid.UUID) -> APPayment:
        payment = await self.db.scalar(
            select(APPayment)
            .where(APPayment.id == payment_id, APPayment.company_id == company_id)
            .options(
                selectinload(APPayment.allocations)
                .selectinload(APPaymentAllocation.invoice)
                .selectinload(SupplierInvoice.supplier),
                selectinload(APPayment.certificates),
            )
        )
        if payment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AP payment not found")
        return payment

    async def list_wht_certificates(
        self,
        company_id: uuid.UUID,
        supplier_id: uuid.UUID | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[WHTCertificate], int]:
        filters = [WHTCertificate.company_id == company_id]
        if supplier_id is not None:
            filters.append(WHTCertificate.supplier_id == supplier_id)
        total = int((await self.db.scalar(select(func.count(WHTCertificate.id)).where(*filters))) or 0)
        rows = await self.db.scalars(
            select(WHTCertificate)
            .where(*filters)
            .options(selectinload(WHTCertificate.supplier), selectinload(WHTCertificate.payment))
            .order_by(WHTCertificate.issue_date.desc(), WHTCertificate.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return rows.all(), total

    async def get_wht_certificate(self, cert_id: uuid.UUID, company_id: uuid.UUID) -> WHTCertificate:
        cert = await self.db.scalar(
            select(WHTCertificate)
            .where(WHTCertificate.id == cert_id, WHTCertificate.company_id == company_id)
            .options(selectinload(WHTCertificate.supplier), selectinload(WHTCertificate.payment))
        )
        if cert is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WHT certificate not found")
        return cert

    async def get_vat_return_report(self, company_id: uuid.UUID, year: int, month: int) -> VatReturnReport:
        tax_ledger = (
            await self.db.scalars(
                select(TaxLedgerEntry).where(
                    TaxLedgerEntry.company_id == company_id,
                    TaxLedgerEntry.status == "posted",
                    func.extract("year", TaxLedgerEntry.document_date) == year,
                    func.extract("month", TaxLedgerEntry.document_date) == month,
                )
            )
        ).all()
        output_docs = (
            await self.db.scalars(
                select(TaxDocument).where(
                    TaxDocument.company_id == company_id,
                    TaxDocument.status == "issued",
                    TaxDocument.document_type.in_(["full_tax_invoice", "abbreviated_tax_invoice"]),
                    func.extract("year", TaxDocument.issue_date) == year,
                    func.extract("month", TaxDocument.issue_date) == month,
                )
            )
        ).all()
        input_invoices = (
            await self.db.scalars(
                select(SupplierInvoice).where(
                    SupplierInvoice.company_id == company_id,
                    SupplierInvoice.deleted_at.is_(None),
                    SupplierInvoice.status != "cancelled",
                    func.extract("year", SupplierInvoice.invoice_date) == year,
                    func.extract("month", SupplierInvoice.invoice_date) == month,
                )
            )
        ).all()

        if tax_ledger:
            output_rows = [item for item in tax_ledger if item.tax_direction == "output"]
            input_rows = [item for item in tax_ledger if item.tax_direction == "input"]
            output_vat_total = q2(sum((Decimal(item.tax_amount or 0) for item in output_rows), Decimal("0")))
            input_vat_total = q2(sum((Decimal(item.tax_amount or 0) for item in input_rows), Decimal("0")))
            output_doc_count = len(output_rows)
            input_invoice_count = len(input_rows)
        else:
            # Compatibility before the first Tax Center sync.
            output_vat_total = q2(sum((Decimal(item.vat_amount or 0) for item in output_docs), Decimal("0")))
            input_vat_total = q2(sum((Decimal(item.vat_amount or 0) for item in input_invoices), Decimal("0")))
            output_doc_count = len(output_docs)
            input_invoice_count = len(input_invoices)
        net_vat_payable = q2(output_vat_total - input_vat_total)

        next_month_year = year + (1 if month == 12 else 0)
        next_month = 1 if month == 12 else month + 1
        filing_due_date = f"15/{next_month:02d}/{next_month_year + 543}"
        if net_vat_payable > 0:
            net_label = "ภาษีที่ต้องนำส่ง"
        elif net_vat_payable < 0:
            net_label = "ภาษีที่ขอคืน / เครดิตภาษี"
        else:
            net_label = "ไม่มีภาษีที่ต้องนำส่ง"

        return VatReturnReport(
            year=year,
            month=month,
            month_label=f"{MONTHS_TH[month]} {year + 543}",
            output_vat_sales=output_vat_total,
            output_vat_total=output_vat_total,
            input_vat_purchases=input_vat_total,
            input_vat_total=input_vat_total,
            net_vat_payable=net_vat_payable,
            net_vat_label=net_label,
            output_doc_count=output_doc_count,
            input_invoice_count=input_invoice_count,
            filing_due_date=filing_due_date,
        )

    async def _get_supplier(self, company_id: uuid.UUID, supplier_id: uuid.UUID) -> Supplier:
        supplier = await self.db.scalar(
            select(Supplier).where(
                Supplier.id == supplier_id,
                Supplier.company_id == company_id,
                Supplier.deleted_at.is_(None),
            )
        )
        if supplier is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
        return supplier

    async def _generate_running_number(
        self,
        model: type[SupplierInvoice] | type[APPayment] | type[WHTCertificate],
        company_id: uuid.UUID,
        field_name: str,
        prefix: str,
        entry_date: date,
    ) -> str:
        prefix_value = f"{prefix}{entry_date:%Y%m%d}-"
        field = getattr(model, field_name)
        # Numbers are globally unique in the existing schema. Python hash() is
        # process-randomized and cannot serialize multiple workers.
        lock_key = int.from_bytes(hashlib.sha256(f"PAYABLE:{prefix_value}".encode()).digest()[:8], "big", signed=True)
        await self.db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
        await self.db.flush()
        numbers = (await self.db.scalars(select(field).where(field.like(f"{prefix_value}%")))).all()
        sequence = max((int(number[len(prefix_value):]) for number in numbers if number[len(prefix_value):].isdigit()), default=0) + 1
        return f"{prefix_value}{sequence:04d}"

    def _build_invoice_posting_lines(self, invoice: SupplierInvoice) -> list[PostingLine]:
        lines = [
            PostingLine("1105", q2(invoice.subtotal), Decimal("0.00"), "ตั้งมูลค่าสินค้าคงเหลือ"),
            PostingLine("1104", q2(invoice.vat_amount), Decimal("0.00"), "ภาษีซื้อ"),
            PostingLine("2101", Decimal("0.00"), q2(invoice.total_amount), "เจ้าหนี้การค้า"),
        ]
        if q2(invoice.wht_amount) > 0:
            lines.append(PostingLine("2103", Decimal("0.00"), q2(invoice.wht_amount), "ภาษีหัก ณ ที่จ่ายค้างจ่าย"))
        return lines

    def _build_payment_posting_lines(
        self,
        total_allocated: Decimal,
        total_wht: Decimal,
        total_amount: Decimal,
        payment_method: str,
    ) -> list[PostingLine]:
        cash_account = "1101" if payment_method == "cash" else "1102"
        lines = [PostingLine("2101", q2(total_allocated), Decimal("0.00"), "ตัดเจ้าหนี้การค้า")]
        if q2(total_wht) > 0:
            lines.append(PostingLine("2103", Decimal("0.00"), q2(total_wht), "ภาษีหัก ณ ที่จ่ายค้างจ่าย"))
        lines.append(PostingLine(cash_account, Decimal("0.00"), q2(total_amount), "จ่ายเงินให้เจ้าหนี้"))
        return lines

    def _audit(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None,
        user_id: uuid.UUID,
        action: str,
        resource: str,
        resource_id: uuid.UUID,
    ) -> None:
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=branch_id,
                user_id=user_id,
                action=action,
                resource=resource,
                resource_id=str(resource_id),
                created_at=datetime.now(timezone.utc),
            )
        )
