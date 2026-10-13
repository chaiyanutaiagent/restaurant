"""Append-only AP document evidence; independent of the Stripe migration.

UAT may upgrade explicitly to docarchive0028 without enabling/applying Stripe.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "docarchive0028"
down_revision = "wp65govern0026"
branch_labels = ("document_archive",)
depends_on = None


def upgrade():
    op.create_table(
        "document_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_kind", sa.String(40), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_number", sa.String(100), nullable=False),
        sa.Column("template_version", sa.String(60), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("captured_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("rendered_html", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.UniqueConstraint("company_id", "document_kind", "source_id", name="uq_document_snapshot_source"),
        sa.CheckConstraint("document_kind IN ('payment_voucher', 'wht_certificate')", name="document_snapshot_kind"),
    )
    op.create_index("ix_document_snapshots_company_id", "document_snapshots", ["company_id"])
    op.create_index("ix_document_snapshots_branch_id", "document_snapshots", ["branch_id"])
    op.execute("""CREATE FUNCTION reject_document_snapshot_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'Document snapshots are append-only';
        END $$""")
    op.execute("""CREATE TRIGGER document_snapshots_immutable
        BEFORE UPDATE OR DELETE ON document_snapshots
        FOR EACH ROW EXECUTE FUNCTION reject_document_snapshot_mutation()""")
    op.execute("""CREATE TRIGGER document_snapshots_no_truncate
        BEFORE TRUNCATE ON document_snapshots
        FOR EACH STATEMENT EXECUTE FUNCTION reject_document_snapshot_mutation()""")


def downgrade():
    # Never silently delete financial evidence. Application rollback retains this table.
    if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM document_snapshots)")).scalar():
        raise RuntimeError("Snapshot evidence exists: use application rollback, not schema downgrade")
    op.drop_table("document_snapshots")
    op.execute("DROP FUNCTION reject_document_snapshot_mutation()")
