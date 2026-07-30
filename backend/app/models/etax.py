from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.company import Company
    from app.models.user import User


class TaxDocument(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tax_documents"
    __table_args__ = (
        Index("ix_tax_documents_company_document_number", "company_id", "document_number"),
        Index("ix_tax_documents_reference_type_reference_id", "reference_type", "reference_id"),
        Index("ix_tax_documents_issue_date", "issue_date"),
        Index("ix_tax_documents_document_type", "document_type"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    document_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    # FIX S4-B-verify: Thai e-tax document type values exceed 20 chars (e.g. abbreviated_tax_invoice)
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'issued'"))
    reference_type: Mapped[str] = mapped_column(String(50), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    seller_tax_id: Mapped[str] = mapped_column(String(20), nullable=False)
    seller_name: Mapped[str] = mapped_column(String(255), nullable=False)
    seller_branch_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    seller_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    buyer_tax_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    buyer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    buyer_branch_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    buyer_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("7.00"))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    issue_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    original_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tax_documents.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    xml_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    xml_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    company: Mapped["Company"] = relationship("Company")
    branch: Mapped["Branch"] = relationship("Branch")
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    canceller: Mapped["User | None"] = relationship("User", foreign_keys=[cancelled_by])
    original_document: Mapped["TaxDocument | None"] = relationship(
        "TaxDocument",
        remote_side="TaxDocument.id",
        back_populates="amendment_documents",
    )
    amendment_documents: Mapped[list["TaxDocument"]] = relationship("TaxDocument", back_populates="original_document")
    items: Mapped[list["TaxDocumentItem"]] = relationship(
        "TaxDocumentItem",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="TaxDocumentItem.line_number.asc()",
    )


class TaxDocumentItem(UUIDMixin, Base):
    __tablename__ = "tax_document_items"

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tax_documents.id"), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    unit_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    vat_type: Mapped[str] = mapped_column(String(20), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("7.00"))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    line_total: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)

    document: Mapped["TaxDocument"] = relationship("TaxDocument", back_populates="items")
