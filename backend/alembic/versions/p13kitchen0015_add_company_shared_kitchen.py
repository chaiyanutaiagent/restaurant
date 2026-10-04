"""add Company shared central-kitchen ledger

Revision ID: p13kitchen0015
Revises: p12route0014
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p13kitchen0015"
down_revision: Union[str, None] = "p12route0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _id() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def upgrade() -> None:
    op.create_table(
        "company_kitchens",
        _id(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("timezone", sa.String(length=50), nullable=False, server_default=sa.text("'Asia/Bangkok'")),
        sa.Column("costing_method", sa.String(length=20), nullable=False, server_default=sa.text("'fifo'")),
        sa.Column("allow_negative_stock", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("costing_method IN ('fifo')", name="ck_company_kitchens_costing_method"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["raw_location_id"], ["stock_locations.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint("company_id", name="uq_company_kitchens_company_id"),
        sa.UniqueConstraint("raw_location_id", name="uq_company_kitchens_raw_location_id"),
    )
    op.create_index("ix_company_kitchens_company_id", "company_kitchens", ["company_id"])
    op.create_index("ix_company_kitchens_branch_id", "company_kitchens", ["branch_id"])
    op.create_index("ix_company_kitchens_raw_location_id", "company_kitchens", ["raw_location_id"])

    op.create_table(
        "company_ingredients",
        _id(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("base_unit_code", sa.String(length=30), nullable=False),
        sa.Column("unit_dimension", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_timestamps(),
        sa.CheckConstraint("unit_dimension IN ('mass', 'volume', 'count')", name="ck_company_ingredients_unit_dimension"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["canonical_product_id"], ["products.id"]),
        sa.UniqueConstraint("company_id", "code", name="uq_company_ingredients_company_code"),
        sa.UniqueConstraint("company_id", "canonical_product_id", name="uq_company_ingredients_company_product"),
    )
    op.create_index("ix_company_ingredients_company_id", "company_ingredients", ["company_id"])
    op.create_index("ix_company_ingredients_canonical_product_id", "company_ingredients", ["canonical_product_id"])

    op.create_table(
        "company_ingredient_aliases",
        _id(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingredient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_unit_code", sa.String(length=30), nullable=False),
        sa.Column("conversion_factor", sa.Numeric(18, 8), nullable=False, server_default=sa.text("1")),
        sa.Column("supplier_sku", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_timestamps(),
        sa.CheckConstraint("conversion_factor > 0", name="ck_company_ingredient_aliases_conversion_positive"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["ingredient_id"], ["company_ingredients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_product_id"], ["products.id"]),
        sa.UniqueConstraint("company_id", "brand_id", "source_product_id", name="uq_company_ingredient_aliases_brand_product"),
    )
    op.create_index("ix_company_ingredient_aliases_company_id", "company_ingredient_aliases", ["company_id"])
    op.create_index("ix_company_ingredient_aliases_brand_id", "company_ingredient_aliases", ["brand_id"])
    op.create_index("ix_company_ingredient_aliases_source_product_id", "company_ingredient_aliases", ["source_product_id"])
    op.create_index("ix_company_ingredient_aliases_company_ingredient", "company_ingredient_aliases", ["company_id", "ingredient_id"])

    op.create_table(
        "company_ingredient_lots",
        _id(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kitchen_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingredient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lot_code", sa.String(length=100), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("qty_on_hand", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")),
        *_timestamps(),
        sa.CheckConstraint("qty_on_hand >= 0", name="ck_company_ingredient_lots_qty_nonnegative"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_company_ingredient_lots_cost_nonnegative"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["kitchen_id"], ["company_kitchens.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["company_ingredients.id"]),
        sa.UniqueConstraint("kitchen_id", "ingredient_id", "lot_code", name="uq_company_ingredient_lots_identity"),
    )
    op.create_index("ix_company_ingredient_lots_company_id", "company_ingredient_lots", ["company_id"])
    op.create_index("ix_company_ingredient_lots_ingredient_id", "company_ingredient_lots", ["ingredient_id"])
    op.create_index("ix_company_ingredient_lots_fifo", "company_ingredient_lots", ["company_id", "kitchen_id", "ingredient_id", "expires_on", "received_at"])

    op.create_table(
        "company_production_demands",
        _id(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("output_product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("needed_on", sa.Date(), nullable=False),
        sa.Column("requested_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_code", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'submitted'")),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("status IN ('submitted', 'converted', 'cancelled')", name="ck_company_production_demands_status"),
        sa.CheckConstraint("requested_qty > 0", name="ck_company_production_demands_qty_positive"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["output_product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_company_production_demands_idempotency"),
    )
    op.create_index("ix_company_production_demands_company_id", "company_production_demands", ["company_id"])
    op.create_index("ix_company_production_demands_brand_id", "company_production_demands", ["brand_id"])
    op.create_index("ix_company_production_demands_branch_id", "company_production_demands", ["branch_id"])
    op.create_index("ix_company_production_demands_output_product_id", "company_production_demands", ["output_product_id"])
    op.create_index("ix_company_production_demands_plan", "company_production_demands", ["company_id", "needed_on", "status", "brand_id"])

    op.create_table(
        "company_production_orders",
        _id(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kitchen_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("demand_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recipe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("output_product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ready_location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_number", sa.String(length=50), nullable=False),
        sa.Column("planned_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'planned'")),
        sa.Column("planned_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("actual_output_qty", sa.Numeric(18, 4), nullable=True),
        sa.Column("waste_qty", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("output_unit_code", sa.String(length=30), nullable=False),
        sa.Column("total_input_cost", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("output_cost_per_unit", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("completion_key", sa.String(length=120), nullable=True),
        sa.Column("reversal_key", sa.String(length=120), nullable=True),
        sa.Column("planned_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reversed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("status IN ('planned', 'in_progress', 'completed', 'reversed', 'cancelled')", name="ck_company_production_orders_status"),
        sa.CheckConstraint("planned_qty > 0", name="ck_company_production_orders_planned_positive"),
        sa.CheckConstraint("actual_output_qty IS NULL OR actual_output_qty > 0", name="ck_company_production_orders_output_positive"),
        sa.CheckConstraint("waste_qty >= 0", name="ck_company_production_orders_waste_nonnegative"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["kitchen_id"], ["company_kitchens.id"]),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["demand_id"], ["company_production_demands.id"]),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"]),
        sa.ForeignKeyConstraint(["output_product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["ready_location_id"], ["stock_locations.id"]),
        sa.ForeignKeyConstraint(["planned_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["started_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["completed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["reversed_by"], ["users.id"]),
        sa.UniqueConstraint("company_id", "order_number", name="uq_company_production_orders_number"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_company_production_orders_idempotency"),
        sa.UniqueConstraint("company_id", "completion_key", name="uq_company_production_orders_completion"),
        sa.UniqueConstraint("company_id", "reversal_key", name="uq_company_production_orders_reversal"),
    )
    op.create_index("ix_company_production_orders_company_id", "company_production_orders", ["company_id"])
    op.create_index("ix_company_production_orders_brand_id", "company_production_orders", ["brand_id"])
    op.create_index("ix_company_production_orders_demand_id", "company_production_orders", ["demand_id"])
    op.create_index("ix_company_production_orders_output_product_id", "company_production_orders", ["output_product_id"])
    op.create_index("ix_company_production_orders_company_brand_status", "company_production_orders", ["company_id", "brand_id", "status"])

    op.create_table(
        "company_production_inputs",
        _id(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingredient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("planned_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("actual_qty", sa.Numeric(18, 4), nullable=True),
        sa.Column("base_unit_code", sa.String(length=30), nullable=False),
        sa.Column("actual_cost", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")),
        *_timestamps(),
        sa.CheckConstraint("planned_qty > 0", name="ck_company_production_inputs_planned_positive"),
        sa.CheckConstraint("actual_qty IS NULL OR actual_qty >= 0", name="ck_company_production_inputs_actual_nonnegative"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["company_production_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["company_ingredients.id"]),
        sa.UniqueConstraint("order_id", "ingredient_id", name="uq_company_production_inputs_order_ingredient"),
    )
    op.create_index("ix_company_production_inputs_company_id", "company_production_inputs", ["company_id"])
    op.create_index("ix_company_production_inputs_ingredient_id", "company_production_inputs", ["ingredient_id"])

    op.create_table(
        "company_kitchen_movements",
        _id(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kitchen_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingredient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("production_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reversal_of_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("movement_type", sa.String(length=30), nullable=False),
        sa.Column("qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("qty_before", sa.Numeric(18, 4), nullable=False),
        sa.Column("qty_after", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("reference_type", sa.String(length=50), nullable=False),
        sa.Column("reference_id", sa.String(length=120), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("movement_type IN ('receipt', 'production_issue', 'production_reversal', 'waste', 'adjustment')", name="ck_company_kitchen_movements_type"),
        sa.CheckConstraint("qty <> 0", name="ck_company_kitchen_movements_qty_nonzero"),
        sa.CheckConstraint("qty_after >= 0", name="ck_company_kitchen_movements_after_nonnegative"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_company_kitchen_movements_cost_nonnegative"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["kitchen_id"], ["company_kitchens.id"]),
        sa.ForeignKeyConstraint(["ingredient_id"], ["company_ingredients.id"]),
        sa.ForeignKeyConstraint(["lot_id"], ["company_ingredient_lots.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["stock_locations.id"]),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["production_order_id"], ["company_production_orders.id"]),
        sa.ForeignKeyConstraint(["reversal_of_id"], ["company_kitchen_movements.id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_company_kitchen_movements_idempotency"),
        sa.UniqueConstraint("reversal_of_id", name="uq_company_kitchen_movements_reversal"),
    )
    op.create_index("ix_company_kitchen_movements_company_id", "company_kitchen_movements", ["company_id"])
    op.create_index("ix_company_kitchen_movements_ingredient_id", "company_kitchen_movements", ["ingredient_id"])
    op.create_index("ix_company_kitchen_movements_lot_id", "company_kitchen_movements", ["lot_id"])
    op.create_index("ix_company_kitchen_movements_location_id", "company_kitchen_movements", ["location_id"])
    op.create_index("ix_company_kitchen_movements_brand_id", "company_kitchen_movements", ["brand_id"])
    op.create_index("ix_company_kitchen_movements_production_order_id", "company_kitchen_movements", ["production_order_id"])
    op.create_index("ix_company_kitchen_movements_created_at", "company_kitchen_movements", ["created_at"])
    op.create_index("ix_company_kitchen_movements_report", "company_kitchen_movements", ["company_id", "created_at", "brand_id", "ingredient_id"])


def downgrade() -> None:
    op.drop_table("company_kitchen_movements")
    op.drop_table("company_production_inputs")
    op.drop_table("company_production_orders")
    op.drop_table("company_production_demands")
    op.drop_table("company_ingredient_lots")
    op.drop_table("company_ingredient_aliases")
    op.drop_table("company_ingredients")
    op.drop_table("company_kitchens")
