"""Add preparation copy without reinterpreting legacy merchant audits."""
from alembic import op

revision = "p6takeaway0010"
down_revision = "p6takeaway0009"
branch_labels = None
depends_on = None

def upgrade():
    op.drop_constraint("ck_takeaway_receipt_print_copy", "takeaway_receipts", type_="check")
    op.create_check_constraint("ck_takeaway_receipt_print_copy", "takeaway_receipts",
        "last_printed_copy IS NULL OR last_printed_copy IN ('customer', 'merchant', 'preparation')")

def downgrade():
    # Do not erase/relabel preparation history to satisfy the old contract.
    # Roll back application images while retaining this additive constraint.
    raise RuntimeError("Preparation print history must be preserved; schema downgrade requires reviewed data migration")
