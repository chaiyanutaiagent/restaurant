"""add_payable_and_wht

Revision ID: 3335eaff7ed8
Revises: 5d350c34d9d8
Create Date: 2026-05-14 06:28:46.684341

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3335eaff7ed8"
down_revision: Union[str, None] = "5d350c34d9d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ap_payments",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("payment_number", sa.String(length=30), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("payment_method", sa.String(length=30), nullable=False),
        sa.Column("bank_account", sa.String(length=100), nullable=True),
        sa.Column("reference_no", sa.String(length=100), nullable=True),
        sa.Column("total_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_ap_payments_branch_id_branches")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_ap_payments_company_id_companies")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_ap_payments_created_by_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ap_payments")),
        sa.UniqueConstraint("payment_number", name=op.f("uq_ap_payments_payment_number")),
    )
    op.create_index(op.f("ix_ap_payments_branch_id"), "ap_payments", ["branch_id"], unique=False)
    op.create_index(op.f("ix_ap_payments_company_id"), "ap_payments", ["company_id"], unique=False)
    op.create_index("ix_ap_payments_company_payment_number", "ap_payments", ["company_id", "payment_number"], unique=False)
    op.create_index("ix_ap_payments_payment_date", "ap_payments", ["payment_date"], unique=False)

    op.create_table(
        "supplier_invoices",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("supplier_id", sa.UUID(), nullable=False),
        sa.Column("po_id", sa.UUID(), nullable=True),
        sa.Column("invoice_number", sa.String(length=30), nullable=False),
        sa.Column("supplier_ref", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'unpaid'"), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("vat_amount", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("wht_amount", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("paid_amount", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("remaining_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_supplier_invoices_branch_id_branches")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_supplier_invoices_company_id_companies")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_supplier_invoices_created_by_users")),
        sa.ForeignKeyConstraint(["po_id"], ["purchase_orders.id"], name=op.f("fk_supplier_invoices_po_id_purchase_orders")),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name=op.f("fk_supplier_invoices_supplier_id_suppliers")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_supplier_invoices")),
        sa.UniqueConstraint("invoice_number", name=op.f("uq_supplier_invoices_invoice_number")),
    )
    op.create_index(op.f("ix_supplier_invoices_branch_id"), "supplier_invoices", ["branch_id"], unique=False)
    op.create_index(op.f("ix_supplier_invoices_company_id"), "supplier_invoices", ["company_id"], unique=False)
    op.create_index("ix_supplier_invoices_company_invoice_number", "supplier_invoices", ["company_id", "invoice_number"], unique=False)
    op.create_index("ix_supplier_invoices_due_date", "supplier_invoices", ["due_date"], unique=False)
    op.create_index(op.f("ix_supplier_invoices_po_id"), "supplier_invoices", ["po_id"], unique=False)
    op.create_index("ix_supplier_invoices_status", "supplier_invoices", ["status"], unique=False)
    op.create_index("ix_supplier_invoices_supplier_id", "supplier_invoices", ["supplier_id"], unique=False)

    op.create_table(
        "wht_certificates",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("payment_id", sa.UUID(), nullable=False),
        sa.Column("supplier_id", sa.UUID(), nullable=False),
        sa.Column("certificate_number", sa.String(length=30), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("wht_type", sa.String(length=50), nullable=False),
        sa.Column("wht_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("base_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("wht_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("income_type", sa.String(length=100), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_wht_certificates_branch_id_branches")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_wht_certificates_company_id_companies")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_wht_certificates_created_by_users")),
        sa.ForeignKeyConstraint(["payment_id"], ["ap_payments.id"], name=op.f("fk_wht_certificates_payment_id_ap_payments")),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name=op.f("fk_wht_certificates_supplier_id_suppliers")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wht_certificates")),
        sa.UniqueConstraint("certificate_number", name=op.f("uq_wht_certificates_certificate_number")),
    )
    op.create_index(op.f("ix_wht_certificates_branch_id"), "wht_certificates", ["branch_id"], unique=False)
    op.create_index(op.f("ix_wht_certificates_company_id"), "wht_certificates", ["company_id"], unique=False)
    op.create_index(op.f("ix_wht_certificates_payment_id"), "wht_certificates", ["payment_id"], unique=False)
    op.create_index(op.f("ix_wht_certificates_supplier_id"), "wht_certificates", ["supplier_id"], unique=False)

    op.create_table(
        "ap_payment_allocations",
        sa.Column("payment_id", sa.UUID(), nullable=False),
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("allocated_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("wht_amount", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("wht_rate", sa.Numeric(precision=5, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("wht_type", sa.String(length=50), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_ap_payment_allocations_company_id_companies")),
        sa.ForeignKeyConstraint(["invoice_id"], ["supplier_invoices.id"], name=op.f("fk_ap_payment_allocations_invoice_id_supplier_invoices")),
        sa.ForeignKeyConstraint(["payment_id"], ["ap_payments.id"], name=op.f("fk_ap_payment_allocations_payment_id_ap_payments")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ap_payment_allocations")),
        sa.UniqueConstraint("payment_id", "invoice_id", name="uq_ap_payment_allocations_payment_invoice"),
    )
    op.create_index(op.f("ix_ap_payment_allocations_company_id"), "ap_payment_allocations", ["company_id"], unique=False)
    op.create_index(op.f("ix_ap_payment_allocations_invoice_id"), "ap_payment_allocations", ["invoice_id"], unique=False)
    op.create_index(op.f("ix_ap_payment_allocations_payment_id"), "ap_payment_allocations", ["payment_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ap_payment_allocations_payment_id"), table_name="ap_payment_allocations")
    op.drop_index(op.f("ix_ap_payment_allocations_invoice_id"), table_name="ap_payment_allocations")
    op.drop_index(op.f("ix_ap_payment_allocations_company_id"), table_name="ap_payment_allocations")
    op.drop_table("ap_payment_allocations")
    op.drop_index(op.f("ix_wht_certificates_supplier_id"), table_name="wht_certificates")
    op.drop_index(op.f("ix_wht_certificates_payment_id"), table_name="wht_certificates")
    op.drop_index(op.f("ix_wht_certificates_company_id"), table_name="wht_certificates")
    op.drop_index(op.f("ix_wht_certificates_branch_id"), table_name="wht_certificates")
    op.drop_table("wht_certificates")
    op.drop_index("ix_supplier_invoices_supplier_id", table_name="supplier_invoices")
    op.drop_index("ix_supplier_invoices_status", table_name="supplier_invoices")
    op.drop_index(op.f("ix_supplier_invoices_po_id"), table_name="supplier_invoices")
    op.drop_index("ix_supplier_invoices_due_date", table_name="supplier_invoices")
    op.drop_index("ix_supplier_invoices_company_invoice_number", table_name="supplier_invoices")
    op.drop_index(op.f("ix_supplier_invoices_company_id"), table_name="supplier_invoices")
    op.drop_index(op.f("ix_supplier_invoices_branch_id"), table_name="supplier_invoices")
    op.drop_table("supplier_invoices")
    op.drop_index("ix_ap_payments_payment_date", table_name="ap_payments")
    op.drop_index("ix_ap_payments_company_payment_number", table_name="ap_payments")
    op.drop_index(op.f("ix_ap_payments_company_id"), table_name="ap_payments")
    op.drop_index(op.f("ix_ap_payments_branch_id"), table_name="ap_payments")
    op.drop_table("ap_payments")
