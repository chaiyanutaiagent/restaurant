"""add_etax_documents

Revision ID: 5d350c34d9d8
Revises: e63d4c134990
Create Date: 2026-05-14 05:49:47.306989

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5d350c34d9d8"
down_revision: Union[str, None] = "e63d4c134990"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tax_documents",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("document_number", sa.String(length=30), nullable=False),
        sa.Column("document_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'issued'"), nullable=False),
        sa.Column("reference_type", sa.String(length=50), nullable=False),
        sa.Column("reference_id", sa.String(length=100), nullable=False),
        sa.Column("seller_tax_id", sa.String(length=20), nullable=False),
        sa.Column("seller_name", sa.String(length=255), nullable=False),
        sa.Column("seller_branch_code", sa.String(length=10), nullable=True),
        sa.Column("seller_address", sa.Text(), nullable=True),
        sa.Column("buyer_tax_id", sa.String(length=20), nullable=True),
        sa.Column("buyer_name", sa.String(length=255), nullable=True),
        sa.Column("buyer_branch_code", sa.String(length=10), nullable=True),
        sa.Column("buyer_address", sa.Text(), nullable=True),
        sa.Column("subtotal", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("vat_rate", sa.Numeric(precision=5, scale=2), server_default=sa.text("7.00"), nullable=False),
        sa.Column("vat_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("issue_datetime", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("original_document_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("xml_content", sa.Text(), nullable=True),
        sa.Column("xml_hash", sa.String(length=64), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.UUID(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_tax_documents_branch_id_branches")),
        sa.ForeignKeyConstraint(["cancelled_by"], ["users.id"], name=op.f("fk_tax_documents_cancelled_by_users")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_tax_documents_company_id_companies")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_tax_documents_created_by_users")),
        sa.ForeignKeyConstraint(["original_document_id"], ["tax_documents.id"], name=op.f("fk_tax_documents_original_document_id_tax_documents")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tax_documents")),
        sa.UniqueConstraint("document_number", name=op.f("uq_tax_documents_document_number")),
    )
    op.create_index(op.f("ix_tax_documents_branch_id"), "tax_documents", ["branch_id"], unique=False)
    op.create_index("ix_tax_documents_company_document_number", "tax_documents", ["company_id", "document_number"], unique=False)
    op.create_index(op.f("ix_tax_documents_company_id"), "tax_documents", ["company_id"], unique=False)
    op.create_index("ix_tax_documents_document_type", "tax_documents", ["document_type"], unique=False)
    op.create_index("ix_tax_documents_issue_date", "tax_documents", ["issue_date"], unique=False)
    op.create_index(op.f("ix_tax_documents_reference_id"), "tax_documents", ["reference_id"], unique=False)
    op.create_index("ix_tax_documents_reference_type_reference_id", "tax_documents", ["reference_type", "reference_id"], unique=False)

    op.create_table(
        "tax_document_items",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("unit_code", sa.String(length=20), nullable=True),
        sa.Column("qty", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("discount_amount", sa.Numeric(precision=15, scale=4), server_default=sa.text("0"), nullable=False),
        sa.Column("vat_type", sa.String(length=20), nullable=False),
        sa.Column("vat_rate", sa.Numeric(precision=5, scale=2), server_default=sa.text("7.00"), nullable=False),
        sa.Column("vat_amount", sa.Numeric(precision=15, scale=4), server_default=sa.text("0"), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["tax_documents.id"], name=op.f("fk_tax_document_items_document_id_tax_documents")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tax_document_items")),
    )
    op.create_index(op.f("ix_tax_document_items_document_id"), "tax_document_items", ["document_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tax_document_items_document_id"), table_name="tax_document_items")
    op.drop_table("tax_document_items")
    op.drop_index("ix_tax_documents_reference_type_reference_id", table_name="tax_documents")
    op.drop_index(op.f("ix_tax_documents_reference_id"), table_name="tax_documents")
    op.drop_index("ix_tax_documents_issue_date", table_name="tax_documents")
    op.drop_index("ix_tax_documents_document_type", table_name="tax_documents")
    op.drop_index(op.f("ix_tax_documents_company_id"), table_name="tax_documents")
    op.drop_index("ix_tax_documents_company_document_number", table_name="tax_documents")
    op.drop_index(op.f("ix_tax_documents_branch_id"), table_name="tax_documents")
    op.drop_table("tax_documents")
