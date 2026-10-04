from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class TaxLedgerEntry(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tax_ledger_entries"
    __table_args__ = (
        CheckConstraint("source_module IN ('restaurant_pos', 'retail_pos', 'takeaway_pos', 'purchasing', 'manual')", name="source_module"),
        CheckConstraint("tax_direction IN ('output', 'input')", name="direction"),
        CheckConstraint("tax_category IN ('standard', 'zero', 'exempt')", name="category"),
        CheckConstraint("status IN ('posted', 'reversed', 'excluded')", name="status"),
        CheckConstraint("reconciliation_status IN ('pending', 'matched', 'not_required', 'warning', 'mismatch')", name="reconciliation_status"),
        UniqueConstraint(
            "company_id", "source_module", "source_document_type", "source_document_id", "line_key", "tax_direction",
            name="uq_tax_ledger_source_line",
        ),
        Index("ix_tax_ledger_company_period", "company_id", "document_date"),
        Index("ix_tax_ledger_company_branch_period", "company_id", "branch_id", "document_date"),
        Index("ix_tax_ledger_reconciliation", "company_id", "reconciliation_status"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True, index=True)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id"), nullable=True, index=True)
    source_module: Mapped[str] = mapped_column(String(30), nullable=False)
    tax_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    tax_category: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'standard'"))
    source_document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_document_id: Mapped[str] = mapped_column(String(100), nullable=False)
    line_key: Mapped[str] = mapped_column(String(100), nullable=False, server_default=text("'summary'"))
    source_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    document_number: Mapped[str] = mapped_column(String(100), nullable=False)
    document_date: Mapped[date] = mapped_column(Date, nullable=False)
    counterparty_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    counterparty_tax_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    counterparty_branch_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    base_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'posted'"))
    reconciliation_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    tax_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tax_documents.id"), nullable=True, index=True)
    source_event_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class TaxPeriod(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tax_periods"
    __table_args__ = (
        CheckConstraint("filing_scope IN ('company', 'branch')", name="filing_scope"),
        CheckConstraint("status IN ('open', 'review', 'closed', 'locked')", name="status"),
        CheckConstraint("period_month >= 1 AND period_month <= 12", name="month"),
        UniqueConstraint("company_id", "scope_key", "period_year", "period_month", name="uq_tax_period_scope_month"),
        Index("ix_tax_period_company_period", "company_id", "period_year", "period_month"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True, index=True)
    filing_scope: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(40), nullable=False)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'open'"))
    output_base_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    output_tax_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    input_base_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    input_tax_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    net_tax_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    ledger_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopened_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reopen_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class TaxReconciliationIssue(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tax_reconciliation_issues"
    __table_args__ = (
        CheckConstraint("severity IN ('warning', 'error', 'blocker')", name="severity"),
        CheckConstraint("status IN ('open', 'resolved', 'ignored')", name="status"),
        CheckConstraint("period_month >= 1 AND period_month <= 12", name="month"),
        UniqueConstraint("company_id", "fingerprint", name="uq_tax_reconciliation_fingerprint"),
        Index("ix_tax_reconciliation_company_period", "company_id", "period_year", "period_month", "status"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True, index=True)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_code: Mapped[str] = mapped_column(String(50), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'open'"))
    source_document_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_document_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    expected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class TaxExportBatch(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tax_export_batches"
    __table_args__ = (
        CheckConstraint("export_type IN ('vat_sales', 'vat_purchases', 'pp30_summary', 'wht_pnd3', 'wht_pnd53', 'etax_manifest', 'tax_archive')", name="export_type"),
        CheckConstraint("status IN ('generated', 'superseded')", name="status"),
        CheckConstraint("period_month >= 1 AND period_month <= 12", name="month"),
        Index("ix_tax_export_company_period", "company_id", "period_year", "period_month"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True, index=True)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    export_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'generated'"))
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    base_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False, server_default=text("'text/csv'"))
    payload: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    generated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
