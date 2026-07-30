from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.company import Company
from app.models.etax import TaxDocument, TaxDocumentItem
from app.models.pos import SaleOrder
from app.schemas.etax import CancelDocumentRequest, IssueCreditNoteRequest, IssueTaxInvoiceRequest
from app.services.payable_service import PayableService
from app.utils.etax_xml import compute_xml_hash, generate_credit_note_xml, generate_tax_invoice_xml

TWOPLACES = Decimal("0.01")


def q2(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


class ETaxService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def issue_tax_invoice(
        self, company_id: uuid.UUID, branch_id: uuid.UUID, user_id: uuid.UUID, data: IssueTaxInvoiceRequest
    ) -> TaxDocument:
        sale = await self.db.scalar(
            select(SaleOrder)
            .where(SaleOrder.id == data.sale_order_id, SaleOrder.company_id == company_id, SaleOrder.status == "completed")
            .options(selectinload(SaleOrder.items), selectinload(SaleOrder.payments))
        )
        if sale is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale order not found")

        existing = await self.db.scalar(
            select(TaxDocument.id).where(
                TaxDocument.company_id == company_id,
                TaxDocument.reference_type == "SaleOrder",
                TaxDocument.reference_id == str(sale.id),
                TaxDocument.status != "cancelled",
                TaxDocument.document_type.in_(["full_tax_invoice", "abbreviated_tax_invoice"]),
            )
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tax invoice already issued")

        company = await self.db.get(Company, company_id)
        if company is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

        if data.document_type == "full_tax_invoice" and not (data.buyer_tax_id or sale.customer_tax_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="buyer_tax_id required for full tax invoice",
            )

        document = TaxDocument(
            company_id=company_id,
            branch_id=branch_id,
            document_number=await self._generate_document_number(company_id, "TINV"),
            document_type=data.document_type,
            status="issued",
            reference_type="SaleOrder",
            reference_id=str(sale.id),
            seller_tax_id=company.tax_id or "-",
            seller_name=company.name,
            seller_branch_code="00000",
            seller_address=company.address,
            buyer_tax_id=data.buyer_tax_id or sale.customer_tax_id,
            buyer_name=data.buyer_name or sale.customer_name,
            buyer_branch_code=data.buyer_branch_code,
            buyer_address=data.buyer_address,
            subtotal=q2(Decimal(sale.total_amount or 0) - Decimal(sale.vat_amount or 0)),
            discount_amount=q2(sale.discount_amount),
            vat_rate=q2(sale.vat_rate),
            vat_amount=q2(sale.vat_amount),
            total_amount=q2(sale.total_amount),
            issue_date=sale.created_at.date(),
            issue_datetime=datetime.now(timezone.utc),
            created_by=user_id,
        )
        self.db.add(document)
        await self.db.flush()

        for index, item in enumerate(sale.items, start=1):
            description = item.product_name + (f" - {item.variant_name}" if item.variant_name else "")
            self.db.add(
                TaxDocumentItem(
                    document_id=document.id,
                    line_number=index,
                    description=description,
                    unit_code=item.unit_code,
                    qty=item.qty,
                    unit_price=item.unit_price,
                    discount_amount=item.discount_amount,
                    vat_type=item.vat_type,
                    vat_rate=item.vat_rate,
                    vat_amount=item.vat_amount,
                    line_total=item.subtotal,
                )
            )
        await self.db.flush()
        await self.db.refresh(document, attribute_names=["items"])
        xml_content = generate_tax_invoice_xml(document, document.items)
        xml_hash = compute_xml_hash(xml_content)
        # FIX S4-B-verify: persist a final XML hash placeholder so stored XML and hash are never null after issuing
        document.xml_content = xml_content.replace("<DocumentHash algorithm=\"SHA256\">PENDING</DocumentHash>", f"<DocumentHash algorithm=\"SHA256\">{xml_hash}</DocumentHash>")
        document.xml_hash = xml_hash
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=branch_id,
                user_id=user_id,
                action="accounting.etax.issued",
                resource="TaxDocument",
                resource_id=str(document.id),
            )
        )
        await self.db.commit()
        return await self.get_document(document.id, company_id)

    async def issue_credit_note(
        self, company_id: uuid.UUID, branch_id: uuid.UUID, user_id: uuid.UUID, data: IssueCreditNoteRequest
    ) -> TaxDocument:
        original = await self.get_document(data.original_document_id, company_id)
        if original.status != "issued":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Original document is not issued")

        document = TaxDocument(
            company_id=company_id,
            branch_id=branch_id,
            document_number=await self._generate_document_number(company_id, "CN"),
            document_type="credit_note",
            status="issued",
            reference_type=original.reference_type,
            reference_id=original.reference_id,
            seller_tax_id=original.seller_tax_id,
            seller_name=original.seller_name,
            seller_branch_code=original.seller_branch_code,
            seller_address=original.seller_address,
            buyer_tax_id=original.buyer_tax_id,
            buyer_name=original.buyer_name,
            buyer_branch_code=original.buyer_branch_code,
            buyer_address=original.buyer_address,
            subtotal=q2(original.subtotal),
            discount_amount=q2(original.discount_amount),
            vat_rate=q2(original.vat_rate),
            vat_amount=q2(original.vat_amount),
            total_amount=q2(original.total_amount),
            issue_date=date.today(),
            issue_datetime=datetime.now(timezone.utc),
            original_document_id=original.id,
            reason=data.reason,
            created_by=user_id,
        )
        self.db.add(document)
        await self.db.flush()

        for item in original.items:
            self.db.add(
                TaxDocumentItem(
                    document_id=document.id,
                    line_number=item.line_number,
                    description=item.description,
                    unit_code=item.unit_code,
                    qty=Decimal(item.qty) * Decimal("-1"),
                    unit_price=item.unit_price,
                    discount_amount=item.discount_amount,
                    vat_type=item.vat_type,
                    vat_rate=item.vat_rate,
                    vat_amount=Decimal(item.vat_amount) * Decimal("-1"),
                    line_total=Decimal(item.line_total) * Decimal("-1"),
                )
            )
        await self.db.flush()
        await self.db.refresh(document, attribute_names=["items"])
        xml_content = generate_credit_note_xml(document, document.items, original)
        xml_hash = compute_xml_hash(xml_content)
        document.xml_content = xml_content.replace("<DocumentHash algorithm=\"SHA256\">PENDING</DocumentHash>", f"<DocumentHash algorithm=\"SHA256\">{xml_hash}</DocumentHash>")
        document.xml_hash = xml_hash
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=branch_id,
                user_id=user_id,
                action="accounting.etax.credit_note_issued",
                resource="TaxDocument",
                resource_id=str(document.id),
            )
        )
        await self.db.commit()
        return await self.get_document(document.id, company_id)

    async def cancel_document(
        self, document_id: uuid.UUID, company_id: uuid.UUID, user_id: uuid.UUID, data: CancelDocumentRequest
    ) -> TaxDocument:
        document = await self.get_document(document_id, company_id)
        if document.status == "cancelled":
            return document
        document.status = "cancelled"
        document.cancelled_at = datetime.now(timezone.utc)
        document.cancelled_by = user_id
        document.cancel_reason = data.cancel_reason
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=document.branch_id,
                user_id=user_id,
                action="accounting.etax.cancelled",
                resource="TaxDocument",
                resource_id=str(document.id),
            )
        )
        await self.db.commit()
        return await self.get_document(document.id, company_id)

    async def get_document(self, document_id: uuid.UUID, company_id: uuid.UUID) -> TaxDocument:
        document = await self.db.scalar(
            select(TaxDocument)
            .where(TaxDocument.id == document_id, TaxDocument.company_id == company_id)
            .options(selectinload(TaxDocument.items), selectinload(TaxDocument.original_document))
        )
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tax document not found")
        return document

    async def list_documents(
        self,
        company_id: uuid.UUID,
        document_type: str | None = None,
        status_value: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[TaxDocument], int]:
        filters = [TaxDocument.company_id == company_id]
        if document_type:
            filters.append(TaxDocument.document_type == document_type)
        if status_value:
            filters.append(TaxDocument.status == status_value)
        if date_from:
            filters.append(TaxDocument.issue_date >= date_from)
        if date_to:
            filters.append(TaxDocument.issue_date <= date_to)
        total = int((await self.db.scalar(select(func.count(TaxDocument.id)).where(*filters))) or 0)
        rows = await self.db.scalars(
            select(TaxDocument)
            .where(*filters)
            .order_by(TaxDocument.issue_date.desc(), TaxDocument.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return rows.all(), total

    async def get_xml(self, document_id: uuid.UUID, company_id: uuid.UUID) -> str:
        document = await self.get_document(document_id, company_id)
        if document.xml_content:
            return document.xml_content
        if document.document_type == "credit_note":
            if document.original_document is None:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Original document missing")
            xml_content = generate_credit_note_xml(document, document.items, document.original_document)
        else:
            xml_content = generate_tax_invoice_xml(document, document.items)
        xml_hash = compute_xml_hash(xml_content)
        document.xml_content = xml_content.replace("<DocumentHash algorithm=\"SHA256\">PENDING</DocumentHash>", f"<DocumentHash algorithm=\"SHA256\">{xml_hash}</DocumentHash>")
        document.xml_hash = xml_hash
        await self.db.commit()
        return document.xml_content

    async def get_monthly_vat_summary(self, company_id: uuid.UUID, year: int, month: int) -> dict[str, object]:
        report = await PayableService(self.db).get_vat_return_report(company_id, year, month)
        return {
            "year": year,
            "month": month,
            "output_vat": q2(report.output_vat_total),
            "input_vat": q2(report.input_vat_total),
            "net_vat_payable": q2(report.net_vat_payable),
            "document_count": report.output_doc_count,
            "total_sales": q2(report.output_vat_sales),
        }

    async def _generate_document_number(self, company_id: uuid.UUID, prefix: str) -> str:
        today = datetime.now(timezone.utc).date()
        prefix_value = f"{prefix}{today:%Y%m%d}-"
        lock_key = hash(str(company_id) + today.strftime("%Y%m%d") + f"ETAX_{prefix}") % (2**31)
        await self.db.execute(text(f"SELECT pg_advisory_xact_lock({lock_key})"))
        count = await self.db.scalar(
            select(func.count(TaxDocument.id)).where(
                TaxDocument.company_id == company_id,
                TaxDocument.document_number.like(f"{prefix_value}%"),
            )
        ) or 0
        return f"{prefix_value}{int(count) + 1:04d}"

    @staticmethod
    def serialize_item(item: TaxDocumentItem) -> dict[str, object]:
        return {
            "id": item.id,
            "document_id": item.document_id,
            "line_number": item.line_number,
            "description": item.description,
            "unit_code": item.unit_code,
            "qty": q2(item.qty),
            "unit_price": q2(item.unit_price),
            "discount_amount": q2(item.discount_amount),
            "vat_type": item.vat_type,
            "vat_rate": q2(item.vat_rate),
            "vat_amount": q2(item.vat_amount),
            "line_total": q2(item.line_total),
        }

    @staticmethod
    def serialize_document(document: TaxDocument) -> dict[str, object]:
        return {
            "id": document.id,
            "document_number": document.document_number,
            "document_type": document.document_type,
            "status": document.status,
            "branch_id": document.branch_id,
            "reference_type": document.reference_type,
            "reference_id": document.reference_id,
            "seller_tax_id": document.seller_tax_id,
            "seller_name": document.seller_name,
            "seller_branch_code": document.seller_branch_code,
            "seller_address": document.seller_address,
            "buyer_tax_id": document.buyer_tax_id,
            "buyer_name": document.buyer_name,
            "buyer_branch_code": document.buyer_branch_code,
            "buyer_address": document.buyer_address,
            "subtotal": q2(document.subtotal),
            "discount_amount": q2(document.discount_amount),
            "vat_rate": q2(document.vat_rate),
            "vat_amount": q2(document.vat_amount),
            "total_amount": q2(document.total_amount),
            "issue_date": document.issue_date,
            "issue_datetime": document.issue_datetime,
            "original_document_id": document.original_document_id,
            "reason": document.reason,
            "xml_hash": document.xml_hash,
            "cancelled_at": document.cancelled_at,
            "cancel_reason": document.cancel_reason,
            "created_by": document.created_by,
            "created_at": document.created_at,
            "items": [ETaxService.serialize_item(item) for item in document.items],
        }

    @staticmethod
    def serialize_list_item(document: TaxDocument) -> dict[str, object]:
        return {
            "id": document.id,
            "document_number": document.document_number,
            "document_type": document.document_type,
            "status": document.status,
            "buyer_name": document.buyer_name,
            "buyer_tax_id": document.buyer_tax_id,
            "total_amount": q2(document.total_amount),
            "vat_amount": q2(document.vat_amount),
            "issue_date": document.issue_date,
            "created_at": document.created_at,
        }
