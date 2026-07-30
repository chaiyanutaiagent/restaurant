from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.accounting import JournalEntry
from app.models.audit import AuditLog
from app.models.company import Company
from app.models.etax import TaxDocument
from app.models.payable import APPayment, APPaymentAllocation, SupplierInvoice, WHTCertificate
from app.models.purchase import PurchaseOrder, Supplier
from app.schemas.payable import CreateAPPaymentRequest, SupplierInvoiceCreate, VatReturnReport
from app.services.accounting_service import AccountingService
from app.utils.posting_rules import PostingLine
from app.utils.thai_date import MONTHS_TH

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

        invoice = SupplierInvoice(
            company_id=company_id,
            branch_id=data.branch_id,
            supplier_id=data.supplier_id,
            po_id=data.po_id,
            invoice_number=invoice_number,
            supplier_ref=data.supplier_ref,
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

    async def cancel_invoice(self, invoice_id: uuid.UUID, company_id: uuid.UUID, user_id: uuid.UUID) -> SupplierInvoice:
        invoice = await self.get_invoice(invoice_id, company_id)
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
            await AccountingService(self.db).reverse_entry(entry_id, company_id, user_id)

        invoice.status = "cancelled"
        invoice.paid_amount = Decimal("0.00")
        invoice.remaining_amount = Decimal("0.00")
        self._audit(company_id, invoice.branch_id, user_id, "accounting.invoice.cancelled", "SupplierInvoice", invoice.id)
        await self.db.commit()
        return await self.get_invoice(invoice.id, company_id)

    async def create_payment(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: CreateAPPaymentRequest,
    ) -> APPayment:
        if not data.allocations:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one allocation is required")

        invoice_ids = [item.invoice_id for item in data.allocations]
        if len(invoice_ids) != len(set(invoice_ids)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate invoice allocation is not allowed")

        invoices = (
            await self.db.scalars(
                select(SupplierInvoice)
                .where(
                    SupplierInvoice.company_id == company_id,
                    SupplierInvoice.id.in_(invoice_ids),
                    SupplierInvoice.deleted_at.is_(None),
                )
                .options(selectinload(SupplierInvoice.supplier))
            )
        ).all()
        invoice_map = {invoice.id: invoice for invoice in invoices}
        if len(invoice_map) != len(invoice_ids):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more invoices not found")

        supplier_ids = {invoice.supplier_id for invoice in invoices}
        if len(supplier_ids) > 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="All allocations must be for the same supplier")

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
            if invoice.status in {"paid", "cancelled"}:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice already paid or cancelled")
            allocated_amount = q2(item.allocated_amount)
            wht_amount = q2(item.wht_amount)
            if allocated_amount <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Allocated amount must be positive")
            if allocated_amount > q2(invoice.remaining_amount):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Allocated amount exceeds invoice remaining amount")
            if wht_amount < 0 or wht_amount > allocated_amount:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid WHT amount")
            if wht_amount > 0 and not (item.wht_type or invoice.supplier.wht_type):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="WHT type is required when WHT amount is provided")

            allocation = APPaymentAllocation(
                payment_id=payment.id,
                invoice_id=invoice.id,
                company_id=company_id,
                allocated_amount=allocated_amount,
                wht_amount=wht_amount,
                wht_rate=q2(item.wht_rate),
                wht_type=item.wht_type or invoice.supplier.wht_type,
            )
            self.db.add(allocation)
            created_allocations.append(allocation)

            invoice.paid_amount = q2(Decimal(invoice.paid_amount or 0) + allocated_amount)
            remaining = q2(Decimal(invoice.total_amount or 0) - Decimal(invoice.paid_amount or 0))
            if abs(remaining) <= TWOPLACES:
                remaining = Decimal("0.00")
            invoice.remaining_amount = remaining
            invoice.status = "paid" if remaining == 0 else "partial"

            total_allocated += allocated_amount
            total_wht += wht_amount

        payment.total_amount = q2(total_allocated - total_wht)
        await self.db.flush()

        await AccountingService(self.db)._post_entry(
            company_id=company_id,
            branch_id=data.branch_id,
            user_id=user_id,
            entry_date=data.payment_date,
            entry_type="payment",
            description=f"จ่ายเจ้าหนี้ {payment.payment_number}",
            lines=self._build_payment_posting_lines(total_allocated, total_wht, payment.total_amount, data.payment_method),
            reference_type="APPayment",
            reference_id=str(payment.id),
        )

        for allocation in created_allocations:
            if q2(allocation.wht_amount) <= 0:
                continue
            cert = WHTCertificate(
                company_id=company_id,
                branch_id=data.branch_id,
                payment_id=payment.id,
                supplier_id=invoice_map[allocation.invoice_id].supplier_id,
                certificate_number=await self._generate_running_number(
                    WHTCertificate,
                    company_id,
                    "certificate_number",
                    "WHT",
                    data.payment_date,
                ),
                issue_date=data.payment_date,
                wht_type=allocation.wht_type or "บริการ",
                wht_rate=q2(allocation.wht_rate),
                base_amount=q2(allocation.allocated_amount),
                wht_amount=q2(allocation.wht_amount),
                income_type=allocation.wht_type,
                created_by=user_id,
            )
            self.db.add(cert)

        self._audit(company_id, data.branch_id, user_id, "accounting.payment.created", "APPayment", payment.id)
        await self.db.commit()
        return await self.get_payment(payment.id, company_id)

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

        output_vat_total = q2(sum((Decimal(item.vat_amount or 0) for item in output_docs), Decimal("0")))
        input_vat_total = q2(sum((Decimal(item.vat_amount or 0) for item in input_invoices), Decimal("0")))
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
            output_doc_count=len(output_docs),
            input_invoice_count=len(input_invoices),
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
        lock_key = hash(str(company_id) + entry_date.strftime("%Y%m%d") + f"PAYABLE_{prefix}") % (2**31)
        await self.db.execute(text(f"SELECT pg_advisory_xact_lock({lock_key})"))
        count = await self.db.scalar(
            select(func.count(model.id)).where(model.company_id == company_id, field.like(f"{prefix_value}%"))
        ) or 0
        return f"{prefix_value}{int(count) + 1:04d}"

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
