"""add shared ERP tax operations

Revision ID: p16taxops0018
Revises: p15taxset0017
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p16taxops0018"
down_revision: Union[str, None] = "p15taxset0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _id() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("tax_entity_type", sa.String(20), nullable=False, server_default=sa.text("'unknown'")))
    op.create_check_constraint("tax_entity_type", "suppliers", "tax_entity_type IN ('individual', 'juristic', 'unknown')")
    op.add_column("supplier_invoices", sa.Column("tax_invoice_number", sa.String(100), nullable=True))
    op.add_column("supplier_invoices", sa.Column("tax_invoice_date", sa.Date(), nullable=True))
    op.add_column("supplier_invoices", sa.Column("input_vat_claimable", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("supplier_invoices", sa.Column("nonclaimable_reason", sa.Text(), nullable=True))
    op.create_check_constraint("claimable_reason", "supplier_invoices", "input_vat_claimable OR nonclaimable_reason IS NOT NULL")

    op.create_table(
        "tax_ledger_entries",
        _id(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_module", sa.String(30), nullable=False),
        sa.Column("tax_direction", sa.String(10), nullable=False),
        sa.Column("tax_category", sa.String(20), nullable=False, server_default=sa.text("'standard'")),
        sa.Column("source_document_type", sa.String(40), nullable=False),
        sa.Column("source_document_id", sa.String(100), nullable=False),
        sa.Column("line_key", sa.String(100), nullable=False, server_default=sa.text("'summary'")),
        sa.Column("source_status", sa.String(30), nullable=True),
        sa.Column("document_number", sa.String(100), nullable=False),
        sa.Column("document_date", sa.Date(), nullable=False),
        sa.Column("counterparty_name", sa.String(255), nullable=True),
        sa.Column("counterparty_tax_id", sa.String(20), nullable=True),
        sa.Column("counterparty_branch_code", sa.String(10), nullable=True),
        sa.Column("base_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("tax_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("total_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'posted'")),
        sa.Column("reconciliation_status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("tax_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_event_id", sa.String(100), nullable=True),
        sa.Column("source_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_sha256", sa.String(64), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("source_module IN ('restaurant_pos', 'retail_pos', 'takeaway_pos', 'purchasing', 'manual')", name="source_module"),
        sa.CheckConstraint("tax_direction IN ('output', 'input')", name="direction"),
        sa.CheckConstraint("tax_category IN ('standard', 'zero', 'exempt')", name="category"),
        sa.CheckConstraint("status IN ('posted', 'reversed', 'excluded')", name="status"),
        sa.CheckConstraint("reconciliation_status IN ('pending', 'matched', 'not_required', 'warning', 'mismatch')", name="reconciliation_status"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["tax_document_id"], ["tax_documents.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint("company_id", "source_module", "source_document_type", "source_document_id", "line_key", "tax_direction", name="uq_tax_ledger_source_line"),
    )
    op.create_index("ix_tax_ledger_entries_company_id", "tax_ledger_entries", ["company_id"])
    op.create_index("ix_tax_ledger_entries_branch_id", "tax_ledger_entries", ["branch_id"])
    op.create_index("ix_tax_ledger_entries_brand_id", "tax_ledger_entries", ["brand_id"])
    op.create_index("ix_tax_ledger_entries_tax_document_id", "tax_ledger_entries", ["tax_document_id"])
    op.create_index("ix_tax_ledger_company_period", "tax_ledger_entries", ["company_id", "document_date"])
    op.create_index("ix_tax_ledger_company_branch_period", "tax_ledger_entries", ["company_id", "branch_id", "document_date"])
    op.create_index("ix_tax_ledger_reconciliation", "tax_ledger_entries", ["company_id", "reconciliation_status"])

    op.create_table(
        "tax_periods",
        _id(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("filing_scope", sa.String(20), nullable=False),
        sa.Column("scope_key", sa.String(40), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'open'")),
        sa.Column("output_base_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tax_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("input_base_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("input_tax_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("net_tax_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("ledger_sha256", sa.String(64), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopened_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reopen_reason", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("filing_scope IN ('company', 'branch')", name="filing_scope"),
        sa.CheckConstraint("status IN ('open', 'review', 'closed', 'locked')", name="status"),
        sa.CheckConstraint("period_month >= 1 AND period_month <= 12", name="month"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["closed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["reopened_by"], ["users.id"]),
        sa.UniqueConstraint("company_id", "scope_key", "period_year", "period_month", name="uq_tax_period_scope_month"),
    )
    op.create_index("ix_tax_periods_company_id", "tax_periods", ["company_id"])
    op.create_index("ix_tax_periods_branch_id", "tax_periods", ["branch_id"])
    op.create_index("ix_tax_period_company_period", "tax_periods", ["company_id", "period_year", "period_month"])

    op.create_table(
        "tax_reconciliation_issues",
        _id(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("issue_code", sa.String(50), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'open'")),
        sa.Column("source_document_type", sa.String(40), nullable=True),
        sa.Column("source_document_id", sa.String(100), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("expected_value", sa.Text(), nullable=True),
        sa.Column("actual_value", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("severity IN ('warning', 'error', 'blocker')", name="severity"),
        sa.CheckConstraint("status IN ('open', 'resolved', 'ignored')", name="status"),
        sa.CheckConstraint("period_month >= 1 AND period_month <= 12", name="month"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
        sa.UniqueConstraint("company_id", "fingerprint", name="uq_tax_reconciliation_fingerprint"),
    )
    op.create_index("ix_tax_reconciliation_issues_company_id", "tax_reconciliation_issues", ["company_id"])
    op.create_index("ix_tax_reconciliation_issues_branch_id", "tax_reconciliation_issues", ["branch_id"])
    op.create_index("ix_tax_reconciliation_company_period", "tax_reconciliation_issues", ["company_id", "period_year", "period_month", "status"])

    op.create_table(
        "tax_export_batches",
        _id(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("export_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'generated'")),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("base_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("tax_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False, server_default=sa.text("'text/csv'")),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("generated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("export_type IN ('vat_sales', 'vat_purchases', 'pp30_summary', 'wht_pnd3', 'wht_pnd53', 'etax_manifest', 'tax_archive')", name="export_type"),
        sa.CheckConstraint("status IN ('generated', 'superseded')", name="status"),
        sa.CheckConstraint("period_month >= 1 AND period_month <= 12", name="month"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["generated_by"], ["users.id"]),
    )
    op.create_index("ix_tax_export_batches_company_id", "tax_export_batches", ["company_id"])
    op.create_index("ix_tax_export_batches_branch_id", "tax_export_batches", ["branch_id"])
    op.create_index("ix_tax_export_company_period", "tax_export_batches", ["company_id", "period_year", "period_month"])


def downgrade() -> None:
    op.drop_table("tax_export_batches")
    op.drop_table("tax_reconciliation_issues")
    op.drop_table("tax_periods")
    op.drop_table("tax_ledger_entries")
    op.drop_constraint("claimable_reason", "supplier_invoices", type_="check")
    op.drop_column("supplier_invoices", "nonclaimable_reason")
    op.drop_column("supplier_invoices", "input_vat_claimable")
    op.drop_column("supplier_invoices", "tax_invoice_date")
    op.drop_column("supplier_invoices", "tax_invoice_number")
    op.drop_constraint("tax_entity_type", "suppliers", type_="check")
    op.drop_column("suppliers", "tax_entity_type")
