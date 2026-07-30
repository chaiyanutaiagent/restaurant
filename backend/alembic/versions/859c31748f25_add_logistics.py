"""add_logistics

Revision ID: 859c31748f25
Revises: 20f2b8ef1375
Create Date: 2026-05-15 15:11:32.475074

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "859c31748f25"
down_revision: Union[str, None] = "20f2b8ef1375"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "carriers",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("name_en", sa.String(length=255), nullable=True),
        sa.Column("tracking_url", sa.String(length=500), nullable=True),
        sa.Column("is_cod", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_carriers_company_id_companies")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_carriers")),
        sa.UniqueConstraint("company_id", "code", name="uq_carriers_company_id_code"),
    )
    op.create_index(op.f("ix_carriers_company_id"), "carriers", ["company_id"], unique=False)

    op.create_table(
        "shipping_rates",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("carrier_id", sa.UUID(), nullable=False),
        sa.Column("service_name", sa.String(length=100), nullable=False),
        sa.Column("zone", sa.String(length=20), server_default=sa.text("'all'"), nullable=False),
        sa.Column("min_weight_g", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_weight_g", sa.Integer(), nullable=True),
        sa.Column("base_rate", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("per_kg_rate", sa.Numeric(precision=10, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("cod_fee", sa.Numeric(precision=10, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["carrier_id"], ["carriers.id"], name=op.f("fk_shipping_rates_carrier_id_carriers")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_shipping_rates_company_id_companies")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shipping_rates")),
    )
    op.create_index(op.f("ix_shipping_rates_carrier_id"), "shipping_rates", ["carrier_id"], unique=False)
    op.create_index(op.f("ix_shipping_rates_company_id"), "shipping_rates", ["company_id"], unique=False)

    op.create_table(
        "shipments",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("carrier_id", sa.UUID(), nullable=False),
        sa.Column("shipment_number", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("sale_order_id", sa.UUID(), nullable=True),
        sa.Column("external_order_id", sa.UUID(), nullable=True),
        sa.Column("sender_name", sa.String(length=255), nullable=False),
        sa.Column("sender_phone", sa.String(length=20), nullable=False),
        sa.Column("sender_address", sa.Text(), nullable=False),
        sa.Column("recipient_name", sa.String(length=255), nullable=False),
        sa.Column("recipient_phone", sa.String(length=20), nullable=False),
        sa.Column("recipient_address", sa.Text(), nullable=False),
        sa.Column("weight_grams", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("width_cm", sa.Integer(), nullable=True),
        sa.Column("height_cm", sa.Integer(), nullable=True),
        sa.Column("depth_cm", sa.Integer(), nullable=True),
        sa.Column("service_name", sa.String(length=100), nullable=True),
        sa.Column("is_cod", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("cod_amount", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("shipping_cost", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("tracking_number", sa.String(length=100), nullable=True),
        sa.Column("picked_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_shipments_branch_id_branches")),
        sa.ForeignKeyConstraint(["carrier_id"], ["carriers.id"], name=op.f("fk_shipments_carrier_id_carriers")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_shipments_company_id_companies")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_shipments_created_by_users")),
        sa.ForeignKeyConstraint(["external_order_id"], ["external_orders.id"], name=op.f("fk_shipments_external_order_id_external_orders")),
        sa.ForeignKeyConstraint(["sale_order_id"], ["sale_orders.id"], name=op.f("fk_shipments_sale_order_id_sale_orders")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shipments")),
        sa.UniqueConstraint("shipment_number", name=op.f("uq_shipments_shipment_number")),
    )
    op.create_index(op.f("ix_shipments_branch_id"), "shipments", ["branch_id"], unique=False)
    op.create_index(op.f("ix_shipments_carrier_id"), "shipments", ["carrier_id"], unique=False)
    op.create_index(op.f("ix_shipments_company_id"), "shipments", ["company_id"], unique=False)
    op.create_index("ix_shipments_company_id_shipment_number", "shipments", ["company_id", "shipment_number"], unique=False)
    op.create_index(op.f("ix_shipments_external_order_id"), "shipments", ["external_order_id"], unique=False)
    op.create_index(op.f("ix_shipments_sale_order_id"), "shipments", ["sale_order_id"], unique=False)
    op.create_index("ix_shipments_status", "shipments", ["status"], unique=False)
    op.create_index(op.f("ix_shipments_tracking_number"), "shipments", ["tracking_number"], unique=False)

    op.create_table(
        "shipment_events",
        sa.Column("shipment_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("event_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_shipment_events_created_by_users")),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], name=op.f("fk_shipment_events_shipment_id_shipments")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shipment_events")),
    )
    op.create_index(op.f("ix_shipment_events_shipment_id"), "shipment_events", ["shipment_id"], unique=False)

    op.create_table(
        "shipment_items",
        sa.Column("shipment_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=True),
        sa.Column("product_name", sa.String(length=500), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("qty", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_shipment_items_product_id_products")),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], name=op.f("fk_shipment_items_shipment_id_shipments")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shipment_items")),
    )
    op.create_index(op.f("ix_shipment_items_shipment_id"), "shipment_items", ["shipment_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_shipment_items_shipment_id"), table_name="shipment_items")
    op.drop_table("shipment_items")
    op.drop_index(op.f("ix_shipment_events_shipment_id"), table_name="shipment_events")
    op.drop_table("shipment_events")
    op.drop_index(op.f("ix_shipments_tracking_number"), table_name="shipments")
    op.drop_index("ix_shipments_status", table_name="shipments")
    op.drop_index(op.f("ix_shipments_sale_order_id"), table_name="shipments")
    op.drop_index(op.f("ix_shipments_external_order_id"), table_name="shipments")
    op.drop_index("ix_shipments_company_id_shipment_number", table_name="shipments")
    op.drop_index(op.f("ix_shipments_company_id"), table_name="shipments")
    op.drop_index(op.f("ix_shipments_carrier_id"), table_name="shipments")
    op.drop_index(op.f("ix_shipments_branch_id"), table_name="shipments")
    op.drop_table("shipments")
    op.drop_index(op.f("ix_shipping_rates_company_id"), table_name="shipping_rates")
    op.drop_index(op.f("ix_shipping_rates_carrier_id"), table_name="shipping_rates")
    op.drop_table("shipping_rates")
    op.drop_index(op.f("ix_carriers_company_id"), table_name="carriers")
    op.drop_table("carriers")
