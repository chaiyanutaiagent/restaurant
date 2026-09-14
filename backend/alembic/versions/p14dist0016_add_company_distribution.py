"""add Company supply-chain distribution orchestration

Revision ID: p14dist0016
Revises: p13kitchen0015
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p14dist0016"
down_revision: Union[str, None] = "p13kitchen0015"
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
    op.create_table(
        "company_distribution_demands",
        _id(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_module", sa.String(length=30), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("needed_on", sa.Date(), nullable=False),
        sa.Column("requested_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_code", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'submitted'")),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("source_module IN ('restaurant_pos', 'takeaway_pos', 'retail_pos')", name="ck_company_distribution_demands_module"),
        sa.CheckConstraint("status IN ('submitted', 'partially_allocated', 'allocated', 'fulfilled', 'cancelled')", name="ck_company_distribution_demands_status"),
        sa.CheckConstraint("requested_qty > 0", name="ck_company_distribution_demands_qty_positive"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_company_distribution_demands_idempotency"),
    )
    for column in ("company_id", "source_module", "brand_id", "branch_id", "product_id"):
        op.create_index(f"ix_company_distribution_demands_{column}", "company_distribution_demands", [column])
    op.create_index("ix_company_distribution_demands_queue", "company_distribution_demands", ["company_id", "needed_on", "status", "source_module"])

    op.create_table(
        "company_distribution_shipments",
        _id(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("demand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transfer_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_module", sa.String(length=30), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shipment_number", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'planned'")),
        sa.Column("planned_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("shipped_qty", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("received_qty", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("rejected_qty", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("returned_qty", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("unit_code", sa.String(length=30), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("planned_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("source_module IN ('restaurant_pos', 'takeaway_pos', 'retail_pos')", name="ck_company_distribution_shipments_module"),
        sa.CheckConstraint("status IN ('planned', 'in_transit', 'partially_received', 'received', 'rejected', 'partially_returned', 'returned', 'cancelled')", name="ck_company_distribution_shipments_status"),
        sa.CheckConstraint("planned_qty > 0", name="ck_company_distribution_shipments_planned_positive"),
        sa.CheckConstraint("shipped_qty >= 0 AND received_qty >= 0 AND rejected_qty >= 0 AND returned_qty >= 0", name="ck_company_distribution_shipments_qty_nonnegative"),
        sa.CheckConstraint("shipped_qty <= planned_qty", name="ck_company_distribution_shipments_ship_le_plan"),
        sa.CheckConstraint("received_qty + rejected_qty <= shipped_qty", name="ck_company_distribution_shipments_settle_le_ship"),
        sa.CheckConstraint("returned_qty <= received_qty", name="ck_company_distribution_shipments_return_le_receive"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["demand_id"], ["company_distribution_demands.id"]),
        sa.ForeignKeyConstraint(["transfer_order_id"], ["transfer_orders.id"]),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["from_location_id"], ["stock_locations.id"]),
        sa.ForeignKeyConstraint(["to_location_id"], ["stock_locations.id"]),
        sa.ForeignKeyConstraint(["planned_by"], ["users.id"]),
        sa.UniqueConstraint("company_id", "shipment_number", name="uq_company_distribution_shipments_number"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_company_distribution_shipments_idempotency"),
        sa.UniqueConstraint("transfer_order_id", name="uq_company_distribution_shipments_transfer"),
    )
    for column in ("company_id", "demand_id", "transfer_order_id", "source_module", "brand_id", "branch_id", "product_id"):
        op.create_index(f"ix_company_distribution_shipments_{column}", "company_distribution_shipments", [column])
    op.create_index("ix_company_distribution_shipments_tracking", "company_distribution_shipments", ["company_id", "status", "source_module", "brand_id", "branch_id"])

    op.create_table(
        "company_distribution_events",
        _id(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shipment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transfer_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_module", sa.String(length=30), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_code", sa.String(length=30), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("event_type IN ('planned', 'dispatched', 'received', 'rejected', 'returned', 'cancelled')", name="ck_company_distribution_events_type"),
        sa.CheckConstraint("qty >= 0", name="ck_company_distribution_events_qty_nonnegative"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["shipment_id"], ["company_distribution_shipments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transfer_order_id"], ["transfer_orders.id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_company_distribution_events_idempotency"),
    )
    for column in ("company_id", "shipment_id", "transfer_order_id", "source_module", "created_at"):
        op.create_index(f"ix_company_distribution_events_{column}", "company_distribution_events", [column])
    op.create_index("ix_company_distribution_events_report", "company_distribution_events", ["company_id", "created_at", "event_type", "source_module"])


def downgrade() -> None:
    op.drop_table("company_distribution_events")
    op.drop_table("company_distribution_shipments")
    op.drop_table("company_distribution_demands")
