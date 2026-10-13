"""Complete document evidence and append-only lifecycle (no Stripe dependency)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "doclife0030"
down_revision = "docarchive0028"
branch_labels = None
depends_on = None


def upgrade():
    # Existing naming convention prefixes checks with ck_<table>_.
    op.drop_constraint(op.f("ck_document_snapshots_document_snapshot_kind"), "document_snapshots", type_="check")
    op.create_check_constraint("document_snapshot_kind", "document_snapshots", "document_kind IN ('purchase_order','goods_receipt','supplier_invoice','payment_voucher','wht_certificate','sales_tax_document')")
    op.create_table("document_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("document_kind", sa.String(40), nullable=False),
        sa.Column("source_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("actor_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text()), sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("company_id", "document_kind", "source_id", "sequence", name="uq_document_event_sequence"))
    op.create_index("ix_document_events_company_id", "document_events", ["company_id"])
    for action, timing in [("immutable", "UPDATE OR DELETE"), ("no_truncate", "TRUNCATE")]:
        level = "STATEMENT" if timing == "TRUNCATE" else "ROW"
        op.execute(f"CREATE TRIGGER document_events_{action} BEFORE {timing} ON document_events FOR EACH {level} EXECUTE FUNCTION reject_document_snapshot_mutation()")


def downgrade():
    raise RuntimeError("Retain document evidence: roll back application images, not the archive schema")
