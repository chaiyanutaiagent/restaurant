"""UAT credit sales and receivables; additive, evidence-preserving migration."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "creditsale0031"
down_revision = "doclife0030"
branch_labels = None
depends_on = None


def identity():
    return [sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", pg.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("branch_id", pg.UUID(as_uuid=True), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_key", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False)]


def upgrade():
    op.create_table("credit_sales", *identity(),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("approved_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("transaction_type", sa.String(30), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("seller", sa.JSON(), nullable=False), sa.Column("buyer", sa.JSON(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        *[sa.Column(name, sa.Numeric(15, 2), nullable=False) for name in ("subtotal", "vat_amount", "total_amount", "paid_amount")],
        sa.UniqueConstraint("company_id", "request_key", name="uq_credit_sale_request"),
        sa.CheckConstraint("status IN ('draft','approved','invoiced','partial','paid','cancelled')", name="credit_sale_status"),
        sa.CheckConstraint("total_amount > 0 AND paid_amount >= 0 AND paid_amount <= total_amount", name="credit_sale_amounts"))
    op.create_table("credit_sale_documents", *identity(),
        sa.Column("sale_id", pg.UUID(as_uuid=True), sa.ForeignKey("credit_sales.id"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("number", sa.String(100), nullable=False, unique=True),
        sa.Column("document_date", sa.Date(), nullable=False),
        sa.Column("total_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.UniqueConstraint("company_id", "request_key", name="uq_credit_document_request"),
        sa.CheckConstraint("kind IN ('sales_quotation','sales_delivery','customer_invoice','billing_notice','customer_receipt')", name="credit_document_kind"),
        sa.CheckConstraint("total_amount >= 0", name="credit_document_amount"))
    for table in ("credit_sales", "credit_sale_documents"):
        for col in ("company_id", "branch_id"):
            op.create_index(f"ix_{table}_{col}", table, [col])
    op.create_index("ix_credit_sale_documents_sale_id", "credit_sale_documents", ["sale_id"])
    op.create_index("uq_credit_document_once", "credit_sale_documents", ["sale_id", "kind"], unique=True,
                    postgresql_where=sa.text("kind <> 'customer_receipt'"))
    op.drop_constraint(op.f("ck_document_snapshots_document_snapshot_kind"), "document_snapshots", type_="check")
    op.create_check_constraint("document_snapshot_kind", "document_snapshots",
        "document_kind IN ('purchase_order','goods_receipt','supplier_invoice','payment_voucher','wht_certificate','sales_tax_document','sales_quotation','sales_delivery','customer_invoice','billing_notice','customer_receipt')")
    # Expose explicit approver permission without silently granting it to cashiers.
    op.execute("""INSERT INTO permissions (id, code, name, module, description)
        VALUES ('81c90f45-05f1-420f-a23c-96c5c38c861d', 'accounting.invoice.approve',
        'Approve Credit Sale Quotation', 'accounting', 'Approve another employee credit-sale quotation')
        ON CONFLICT (code) DO NOTHING""")


def downgrade():
    raise RuntimeError("Preserve credit-sale evidence; roll back images, never delete financial history")
