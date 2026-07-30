"""add stock cutover runs

Revision ID: 0a7b3c4d5e62
Revises: f96a2b3c4d51
Create Date: 2026-07-22 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0a7b3c4d5e62"
down_revision: Union[str, None] = "f96a2b3c4d51"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stock_cutover_runs",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("brand_id", sa.UUID(), nullable=False),
        sa.Column("source_location_id", sa.UUID(), nullable=False),
        sa.Column("destination_location_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'running'"), nullable=False),
        sa.Column("preview_token", sa.String(length=64), nullable=False),
        sa.Column("preview_snapshot", sa.JSON(), nullable=False),
        sa.Column("item_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_qty", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("executed_by", sa.UUID(), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_stock_cutover_runs_status"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["destination_location_id"], ["stock_locations.id"]),
        sa.ForeignKeyConstraint(["executed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_location_id"], ["stock_locations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_cutover_runs_company_id", "stock_cutover_runs", ["company_id"])
    op.create_index("ix_stock_cutover_runs_brand_id", "stock_cutover_runs", ["brand_id"])
    op.create_index("ix_stock_cutover_runs_source_location_id", "stock_cutover_runs", ["source_location_id"])
    op.create_index("ix_stock_cutover_runs_destination_location_id", "stock_cutover_runs", ["destination_location_id"])
    op.create_index(
        "ix_stock_cutover_runs_company_brand",
        "stock_cutover_runs",
        ["company_id", "brand_id", "created_at"],
    )

    op.create_table(
        "stock_cutover_items",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("variant_id", sa.UUID(), nullable=True),
        sa.Column("qty", sa.Numeric(15, 4), nullable=False),
        sa.Column("cost_per_unit", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("source_qty_before", sa.Numeric(15, 4), nullable=False),
        sa.Column("source_qty_after", sa.Numeric(15, 4), nullable=False),
        sa.Column("destination_qty_before", sa.Numeric(15, 4), nullable=False),
        sa.Column("destination_qty_after", sa.Numeric(15, 4), nullable=False),
        sa.Column("source_movement_id", sa.UUID(), nullable=False),
        sa.Column("destination_movement_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("qty >= 0", name="ck_stock_cutover_items_qty_nonnegative"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["destination_movement_id"], ["stock_movements.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["stock_cutover_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_movement_id"], ["stock_movements.id"]),
        sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "product_id", "variant_id", name="uq_stock_cutover_item_product"),
    )
    op.create_index("ix_stock_cutover_items_run", "stock_cutover_items", ["run_id"])
    op.create_index("ix_stock_cutover_items_company_id", "stock_cutover_items", ["company_id"])
    op.create_index("ix_stock_cutover_items_product_id", "stock_cutover_items", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_cutover_items_product_id", table_name="stock_cutover_items")
    op.drop_index("ix_stock_cutover_items_company_id", table_name="stock_cutover_items")
    op.drop_index("ix_stock_cutover_items_run", table_name="stock_cutover_items")
    op.drop_table("stock_cutover_items")
    op.drop_index("ix_stock_cutover_runs_company_brand", table_name="stock_cutover_runs")
    op.drop_index("ix_stock_cutover_runs_destination_location_id", table_name="stock_cutover_runs")
    op.drop_index("ix_stock_cutover_runs_source_location_id", table_name="stock_cutover_runs")
    op.drop_index("ix_stock_cutover_runs_brand_id", table_name="stock_cutover_runs")
    op.drop_index("ix_stock_cutover_runs_company_id", table_name="stock_cutover_runs")
    op.drop_table("stock_cutover_runs")
