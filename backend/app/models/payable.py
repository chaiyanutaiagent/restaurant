from __future__ import annotations

from datetime import date
from decimal import Decimal
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.company import Company
    from app.models.purchase import PurchaseOrder, Supplier
    from app.models.user import User


class SupplierInvoice(SoftDeleteMixin, Base):
    __tablename__ = "supplier_invoices"
    __table_args__ = (
        Index("ix_supplier_invoices_company_invoice_number", "company_id", "invoice_number"),
        Index("ix_supplier_invoices_supplier_id", "supplier_id"),
        Index("ix_supplier_invoices_status", "status"),
        Index("ix_supplier_invoices_due_date", "due_date"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False, index=True)
    po_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=True, index=True)
    invoice_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    supplier_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'unpaid'"))
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    wht_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    remaining_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    company: Mapped["Company"] = relationship("Company")
    branch: Mapped["Branch"] = relationship("Branch")
    supplier: Mapped["Supplier"] = relationship("Supplier")
    purchase_order: Mapped["PurchaseOrder | None"] = relationship("PurchaseOrder")
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    allocations: Mapped[list["APPaymentAllocation"]] = relationship(
        "APPaymentAllocation",
        back_populates="invoice",
        order_by="APPaymentAllocation.created_at.asc()",
    )

    @property
    def supplier_name(self) -> str:
        return self.supplier.name if self.supplier is not None else ""

    @property
    def is_overdue(self) -> bool:
        return self.status != "paid" and self.status != "cancelled" and self.due_date < date.today()


class APPayment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "ap_payments"
    __table_args__ = (
        Index("ix_ap_payments_company_payment_number", "company_id", "payment_number"),
        Index("ix_ap_payments_payment_date", "payment_date"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    payment_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    bank_account: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reference_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    company: Mapped["Company"] = relationship("Company")
    branch: Mapped["Branch"] = relationship("Branch")
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    allocations: Mapped[list["APPaymentAllocation"]] = relationship(
        "APPaymentAllocation",
        back_populates="payment",
        cascade="all, delete-orphan",
        order_by="APPaymentAllocation.created_at.asc()",
    )
    certificates: Mapped[list["WHTCertificate"]] = relationship(
        "WHTCertificate",
        back_populates="payment",
        order_by="WHTCertificate.created_at.asc()",
    )


class APPaymentAllocation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "ap_payment_allocations"
    __table_args__ = (
        UniqueConstraint("payment_id", "invoice_id", name="uq_ap_payment_allocations_payment_invoice"),
    )

    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ap_payments.id"), nullable=False, index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("supplier_invoices.id"), nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    wht_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    wht_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    wht_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    payment: Mapped["APPayment"] = relationship("APPayment", back_populates="allocations")
    invoice: Mapped["SupplierInvoice"] = relationship("SupplierInvoice", back_populates="allocations")
    company: Mapped["Company"] = relationship("Company")

    @property
    def invoice_number(self) -> str:
        return self.invoice.invoice_number if self.invoice is not None else ""

    @property
    def supplier_name(self) -> str:
        if self.invoice is None or self.invoice.supplier is None:
            return ""
        return self.invoice.supplier.name


class WHTCertificate(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "wht_certificates"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ap_payments.id"), nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False, index=True)
    certificate_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    wht_type: Mapped[str] = mapped_column(String(50), nullable=False)
    wht_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    base_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    wht_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    income_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    company: Mapped["Company"] = relationship("Company")
    branch: Mapped["Branch"] = relationship("Branch")
    payment: Mapped["APPayment"] = relationship("APPayment", back_populates="certificates")
    supplier: Mapped["Supplier"] = relationship("Supplier")
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])

    @property
    def supplier_name(self) -> str:
        return self.supplier.name if self.supplier is not None else ""

    @property
    def supplier_tax_id(self) -> str | None:
        return self.supplier.tax_id if self.supplier is not None else None
