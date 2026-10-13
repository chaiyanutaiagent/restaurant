"""Optional central warehouse -> store transfers within Retail only."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "retailtransfer0010"
down_revision = "retailcatalog0009"
branch_labels = None
depends_on = None


def ref(name, table, nullable=False, primary_key=False):
    return sa.Column(name, UUID(as_uuid=True), sa.ForeignKey(table + ".id"), nullable=nullable, primary_key=primary_key)


def common():
    return [sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def upgrade():
    op.create_table("transfer_orders", *common(), ref("company_id","companies"),
        sa.Column("to_number", sa.String(30), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        ref("from_branch_id","branches"),ref("to_branch_id","branches"),
        ref("from_location_id","stock_locations"),ref("to_location_id","stock_locations"),
        ref("requested_by","users"),ref("approved_by","users",True),ref("received_by","users",True),
        sa.Column("request_date",sa.Date(),nullable=False,server_default=sa.text("CURRENT_DATE")),
        sa.Column("expected_date",sa.Date()),
        *[sa.Column(name,sa.DateTime(timezone=True)) for name in ("approved_at","shipped_at","last_received_at","completed_at","cancelled_at")],
        *[sa.Column(name,sa.Text()) for name in ("cancel_reason","discrepancy_note","note")],
        sa.Column("has_discrepancy",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column("destination_posted_at_ship",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.CheckConstraint("from_location_id <> to_location_id", name="ck_transfer_orders_locations_different"))
    op.create_index("ix_transfer_orders_company_branch", "transfer_orders", ["company_id","from_branch_id","to_branch_id"])
    op.create_table("transfer_order_items", *common(),ref("company_id","companies"),ref("to_id","transfer_orders"),
        ref("product_id","products"),ref("variant_id","product_variants",True),
        sa.Column("product_name",sa.String(500),nullable=False),sa.Column("sku",sa.String(100),nullable=False),
        sa.Column("unit_code",sa.String(20)),sa.Column("qty_requested",sa.Numeric(15,4),nullable=False),
        *[sa.Column(name,sa.Numeric(15,4)) for name in ("qty_approved","qty_sent","qty_received")],
        sa.Column("unit_cost",sa.Numeric(15,4),nullable=False,server_default="0"),
        sa.Column("qty_discrepancy",sa.Numeric(15,4),nullable=False,server_default="0"))
    op.create_index("ix_transfer_order_items_to_id", "transfer_order_items", ["to_id"])
    op.create_table("retail_transfer_scopes",ref("order_id","transfer_orders",primary_key=True),
        ref("company_id","companies"),ref("brand_id","brands"),sa.Column("version",sa.Integer(),nullable=False,server_default="1"))


def downgrade():
    op.drop_table("retail_transfer_scopes")
    op.drop_table("transfer_order_items")
    op.drop_table("transfer_orders")
