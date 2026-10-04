"""add restaurant cancellation approval waste and audit

Revision ID: wp45cancel0021
Revises: wp44hold0020
Create Date: 2026-09-20 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "wp45cancel0021"
down_revision: Union[str, None] = "wp44hold0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BASE_APPROVAL_ACTIONS = (
    "pos.discount.override",
    "pos.price.override",
    "pos.sale.void",
    "pos.refund.create",
    "inventory.stock.adjust",
)
WP45_APPROVAL_ACTIONS = BASE_APPROVAL_ACTIONS + (
    "fb.order.cancel_after_kitchen",
    "fb.order.cancel.reopen",
)


def _approval_check(actions: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{action}'" for action in actions) + ")"


def _append_only(table_name: str) -> None:
    function_name = f"prevent_{table_name}_mutation"
    trigger_name = f"trg_{table_name}_append_only"
    op.execute(
        f"""
        CREATE FUNCTION {function_name}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION '{table_name} is append-only' USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {trigger_name}
        BEFORE UPDATE OR DELETE ON {table_name}
        FOR EACH ROW EXECUTE FUNCTION {function_name}()
        """
    )


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_approval_grant_usages_supported_action"),
        "approval_grant_usages",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_approval_grant_usages_supported_action"),
        "approval_grant_usages",
        _approval_check(WP45_APPROVAL_ACTIONS),
    )

    op.add_column(
        "dining_order_items",
        sa.Column("row_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_dining_order_items_row_version_positive"),
        "dining_order_items",
        "row_version >= 1",
    )
    op.add_column(
        "kitchen_tickets",
        sa.Column("row_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_kitchen_tickets_row_version_positive"),
        "kitchen_tickets",
        "row_version >= 1",
    )

    op.create_table(
        "restaurant_cancellations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("stage_before", sa.String(length=20), nullable=False),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approver_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("origin_device_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("origin_device_code", sa.String(length=100), nullable=True),
        sa.Column("station_key", sa.String(length=100), nullable=True),
        sa.Column("reason_code", sa.String(length=50), nullable=False),
        sa.Column("reason_note", sa.Text(), nullable=True),
        sa.Column("before_state", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("approval_policy_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("bill_impact", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("waste_disposition", sa.String(length=20), nullable=False),
        sa.Column("waste_status", sa.String(length=20), nullable=False),
        sa.Column("stock_location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approval_grant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approval_mode", sa.String(length=30), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("target_type IN ('item', 'order')", name=op.f("ck_restaurant_cancellations_target_type")),
        sa.CheckConstraint("stage_before IN ('pending', 'cooking', 'done')", name=op.f("ck_restaurant_cancellations_stage_before")),
        sa.CheckConstraint("waste_disposition IN ('none', 'full')", name=op.f("ck_restaurant_cancellations_waste_disposition")),
        sa.CheckConstraint("waste_status IN ('not_required', 'posted')", name=op.f("ck_restaurant_cancellations_waste_status")),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["dining_orders.id"]),
        sa.ForeignKeyConstraint(["order_item_id"], ["dining_order_items.id"]),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["dining_sessions.id"]),
        sa.ForeignKeyConstraint(["stock_location_id"], ["stock_locations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "branch_id", "requester_id", "idempotency_key",
            name="uq_restaurant_cancellations_idempotency",
        ),
    )
    for name, columns in (
        ("ix_restaurant_cancellations_company_id", ["company_id"]),
        ("ix_restaurant_cancellations_brand_id", ["brand_id"]),
        ("ix_restaurant_cancellations_branch_id", ["branch_id"]),
        ("ix_restaurant_cancellations_session_id", ["session_id"]),
        ("ix_restaurant_cancellations_order_id", ["order_id"]),
        ("ix_restaurant_cancellations_order_item_id", ["order_item_id"]),
        ("ix_restaurant_cancellations_requester_id", ["requester_id"]),
        ("ix_restaurant_cancellations_approver_id", ["approver_id"]),
        ("ix_restaurant_cancellations_origin_device_id", ["origin_device_id"]),
        ("ix_restaurant_cancellations_scope_created", ["company_id", "brand_id", "branch_id", "created_at"]),
    ):
        op.create_index(name, "restaurant_cancellations", columns)

    op.create_table(
        "restaurant_cancellation_waste",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cancellation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("unit", sa.String(length=30), nullable=True),
        sa.Column("stock_movement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_restaurant_cancellation_waste_quantity_positive")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["cancellation_id"], ["restaurant_cancellations.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["stock_locations.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["stock_movement_id"], ["stock_movements.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cancellation_id", "product_id", name="uq_restaurant_cancel_waste_product"),
        sa.UniqueConstraint("stock_movement_id", name="uq_restaurant_cancellation_waste_stock_movement_id"),
    )
    op.create_index("ix_restaurant_cancellation_waste_cancellation_id", "restaurant_cancellation_waste", ["cancellation_id"])
    op.create_index("ix_restaurant_cancel_waste_scope", "restaurant_cancellation_waste", ["company_id", "branch_id", "created_at"])

    op.create_table(
        "kitchen_cancellation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cancellation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("station", sa.String(length=50), nullable=True),
        sa.Column("reason_code", sa.String(length=50), nullable=False),
        sa.Column("reason_note", sa.Text(), nullable=True),
        sa.Column("ticket_status_before", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending_ack'"), nullable=False),
        sa.Column("row_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acknowledged_device_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending_ack', 'acknowledged')", name=op.f("ck_kitchen_cancellation_events_status")),
        sa.CheckConstraint("row_version >= 1", name=op.f("ck_kitchen_cancellation_events_row_version_positive")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["cancellation_id"], ["restaurant_cancellations.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["kitchen_tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cancellation_id", "ticket_id", name="uq_kitchen_cancel_event_ticket"),
    )
    op.create_index("ix_kitchen_cancellation_events_cancellation_id", "kitchen_cancellation_events", ["cancellation_id"])
    op.create_index("ix_kitchen_cancellation_events_ticket_id", "kitchen_cancellation_events", ["ticket_id"])
    op.create_index("ix_kitchen_cancellation_events_brand_id", "kitchen_cancellation_events", ["brand_id"])
    op.create_index("ix_kitchen_cancel_events_queue", "kitchen_cancellation_events", ["company_id", "brand_id", "branch_id", "status", "created_at"])

    op.create_table(
        "restaurant_cancellation_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cancellation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approver_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("station_key", sa.String(length=100), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("from_state", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("to_state", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", postgresql.JSON(astext_type=sa.Text()), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["cancellation_id"], ["restaurant_cancellations.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "branch_id", "action", "idempotency_key",
            name="uq_restaurant_cancel_audits_idempotency",
        ),
    )
    op.create_index("ix_restaurant_cancellation_audits_cancellation_id", "restaurant_cancellation_audits", ["cancellation_id"])
    op.create_index("ix_restaurant_cancel_audits_cancellation", "restaurant_cancellation_audits", ["cancellation_id", "created_at"])
    op.create_index("ix_restaurant_cancel_audits_scope", "restaurant_cancellation_audits", ["company_id", "branch_id", "created_at"])

    for table_name in (
        "restaurant_cancellations",
        "restaurant_cancellation_waste",
        "restaurant_cancellation_audits",
    ):
        _append_only(table_name)


def downgrade() -> None:
    for table_name in (
        "restaurant_cancellation_audits",
        "restaurant_cancellation_waste",
        "restaurant_cancellations",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name}")
        op.execute(f"DROP FUNCTION IF EXISTS prevent_{table_name}_mutation()")

    op.drop_index("ix_restaurant_cancel_audits_scope", table_name="restaurant_cancellation_audits")
    op.drop_index("ix_restaurant_cancel_audits_cancellation", table_name="restaurant_cancellation_audits")
    op.drop_index("ix_restaurant_cancellation_audits_cancellation_id", table_name="restaurant_cancellation_audits")
    op.drop_table("restaurant_cancellation_audits")
    op.drop_index("ix_kitchen_cancel_events_queue", table_name="kitchen_cancellation_events")
    op.drop_index("ix_kitchen_cancellation_events_brand_id", table_name="kitchen_cancellation_events")
    op.drop_index("ix_kitchen_cancellation_events_ticket_id", table_name="kitchen_cancellation_events")
    op.drop_index("ix_kitchen_cancellation_events_cancellation_id", table_name="kitchen_cancellation_events")
    op.drop_table("kitchen_cancellation_events")
    op.drop_index("ix_restaurant_cancel_waste_scope", table_name="restaurant_cancellation_waste")
    op.drop_index("ix_restaurant_cancellation_waste_cancellation_id", table_name="restaurant_cancellation_waste")
    op.drop_table("restaurant_cancellation_waste")
    for name in (
        "ix_restaurant_cancellations_scope_created",
        "ix_restaurant_cancellations_origin_device_id",
        "ix_restaurant_cancellations_approver_id",
        "ix_restaurant_cancellations_requester_id",
        "ix_restaurant_cancellations_order_item_id",
        "ix_restaurant_cancellations_order_id",
        "ix_restaurant_cancellations_session_id",
        "ix_restaurant_cancellations_branch_id",
        "ix_restaurant_cancellations_brand_id",
        "ix_restaurant_cancellations_company_id",
    ):
        op.drop_index(name, table_name="restaurant_cancellations")
    op.drop_table("restaurant_cancellations")

    op.drop_constraint(op.f("ck_kitchen_tickets_row_version_positive"), "kitchen_tickets", type_="check")
    op.drop_column("kitchen_tickets", "row_version")
    op.drop_constraint(op.f("ck_dining_order_items_row_version_positive"), "dining_order_items", type_="check")
    op.drop_column("dining_order_items", "row_version")

    op.drop_constraint(
        op.f("ck_approval_grant_usages_supported_action"),
        "approval_grant_usages",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_approval_grant_usages_supported_action"),
        "approval_grant_usages",
        _approval_check(BASE_APPROVAL_ACTIONS),
    )
