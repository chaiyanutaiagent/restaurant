"""Add explicit per-branch stock targets; never guess targets from current stock."""
from alembic import op
import sqlalchemy as sa

revision = "p6takeaway0011"
down_revision = "p6takeaway0010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("takeaway_replenishment_policies", sa.Column("target_stock_qty", sa.Numeric(15, 4), nullable=True))
    op.create_check_constraint("ck_takeaway_replenishment_target", "takeaway_replenishment_policies",
                               "target_stock_qty IS NULL OR target_stock_qty > 0")


def downgrade():
    op.drop_constraint("ck_takeaway_replenishment_target", "takeaway_replenishment_policies", type_="check")
    op.drop_column("takeaway_replenishment_policies", "target_stock_qty")
