"""add shared Company reporting projection

Revision ID: p13platform0017
Revises: p12platform0016
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p13platform0017"
down_revision: Union[str, None] = "p12platform0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_reporting_source_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_stream", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'idle'"), nullable=False),
        sa.Column("cursor_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cursor_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("failure_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error_code", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('idle', 'healthy', 'failed', 'degraded')",
            name="ck_company_reporting_source_states_status_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_stream", name="uq_company_reporting_source_states_source_stream"),
    )

    op.create_table(
        "company_reporting_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_key", sa.String(length=30), nullable=False),
        sa.Column("business_type", sa.String(length=30), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("source_document_type", sa.String(length=50), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_number", sa.String(length=80), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'THB'"), nullable=False),
        sa.Column("gross_sales", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("discount_amount", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("tax_amount", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("refund_amount", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("net_sales", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("source_status", sa.String(length=30), nullable=False),
        sa.Column("source_stream", sa.String(length=50), nullable=False),
        sa.Column("last_source_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_projected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "module_key IN ('restaurant_pos', 'takeaway_pos', 'retail_pos')",
            name="ck_company_reporting_facts_module_key_valid",
        ),
        sa.CheckConstraint(
            "business_type IN ('restaurant', 'takeaway', 'retail_pos')",
            name="ck_company_reporting_facts_business_type_valid",
        ),
        sa.CheckConstraint(
            "source_status IN ('completed', 'paid', 'partially_refunded', 'refunded', 'voided')",
            name="ck_company_reporting_facts_source_status_valid",
        ),
        sa.CheckConstraint(
            "gross_sales >= 0 AND discount_amount >= 0 AND tax_amount >= 0 "
            "AND refund_amount >= 0 AND net_sales >= 0",
            name="ck_company_reporting_facts_amounts_nonnegative",
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "module_key",
            "source_document_type",
            "source_document_id",
            name="uq_company_reporting_facts_company_module_source_document",
        ),
    )
    op.create_index(
        "ix_company_reporting_facts_company_date_module",
        "company_reporting_facts",
        ["company_id", "business_date", "module_key"],
    )
    op.create_index(
        "ix_company_reporting_facts_workspace_date",
        "company_reporting_facts",
        ["company_id", "brand_id", "branch_id", "business_date"],
    )

    op.create_table(
        "company_reporting_event_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_stream", sa.String(length=50), nullable=False),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_key", sa.String(length=30), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('processed', 'dead_letter')",
            name="ck_company_reporting_event_receipts_status_valid",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_stream",
            "source_event_id",
            name="uq_company_reporting_event_receipts_source_stream_event",
        ),
    )
    op.create_index(
        "ix_company_reporting_receipts_company_processed",
        "company_reporting_event_receipts",
        ["company_id", "processed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_reporting_receipts_company_processed",
        table_name="company_reporting_event_receipts",
    )
    op.drop_table("company_reporting_event_receipts")
    op.drop_index(
        "ix_company_reporting_facts_workspace_date",
        table_name="company_reporting_facts",
    )
    op.drop_index(
        "ix_company_reporting_facts_company_date_module",
        table_name="company_reporting_facts",
    )
    op.drop_table("company_reporting_facts")
    op.drop_table("company_reporting_source_states")
