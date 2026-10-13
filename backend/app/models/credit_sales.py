"""Separate customer receivables, never the central-kitchen branch credit wallet."""
from datetime import date
from decimal import Decimal
import uuid
from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, JSON, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import UUIDMixin, TimestampMixin

KINDS = ("sales_quotation", "sales_delivery", "customer_invoice", "billing_notice", "customer_receipt")


class CreditSale(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "credit_sales"
    __table_args__ = (
        UniqueConstraint("company_id", "request_key", name="uq_credit_sale_request"),
        CheckConstraint("status IN ('draft','approved','invoiced','partial','paid','cancelled')", name="credit_sale_status"),
        CheckConstraint("total_amount > 0 AND paid_amount >= 0 AND paid_amount <= total_amount", name="credit_sale_amounts"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"))
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    description: Mapped[str] = mapped_column(String(500))
    due_date: Mapped[date] = mapped_column(Date)
    transaction_type: Mapped[str] = mapped_column(String(30))
    seller: Mapped[dict] = mapped_column(JSON)
    buyer: Mapped[dict] = mapped_column(JSON)
    items: Mapped[list] = mapped_column(JSON)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))


class CreditSaleDocument(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "credit_sale_documents"
    __table_args__ = (
        UniqueConstraint("company_id", "request_key", name="uq_credit_document_request"),
        Index("uq_credit_document_once", "sale_id", "kind", unique=True,
              postgresql_where=text("kind <> 'customer_receipt'")),
        CheckConstraint("kind IN ('sales_quotation','sales_delivery','customer_invoice','billing_notice','customer_receipt')", name="credit_document_kind"),
        CheckConstraint("total_amount >= 0", name="credit_document_amount"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), index=True)
    sale_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("credit_sales.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    number: Mapped[str] = mapped_column(String(100), unique=True)
    document_date: Mapped[date] = mapped_column(Date)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    status: Mapped[str] = mapped_column(String(20), default="issued")
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    request_hash: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
