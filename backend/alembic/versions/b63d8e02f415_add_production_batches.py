"""add production batches

Revision ID: b63d8e02f415
Revises: a52c7d91e304
Create Date: 2026-07-22 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b63d8e02f415"
down_revision: Union[str, None] = "a52c7d91e304"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "production_batches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_number", sa.String(length=50), nullable=False),
        sa.Column("planned_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'planned'")),
        sa.Column("raw_location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ready_location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("planned_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("planned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('draft', 'planned', 'in_progress', 'completed', 'cancelled')",
            name="ck_production_batches_status",
        ),
        sa.CheckConstraint(
            "raw_location_id <> ready_location_id",
            name="ck_production_batches_distinct_locations",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["raw_location_id"], ["stock_locations.id"]),
        sa.ForeignKeyConstraint(["ready_location_id"], ["stock_locations.id"]),
        sa.ForeignKeyConstraint(["planned_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["started_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["completed_by"], ["users.id"]),
        sa.UniqueConstraint("company_id", "batch_number", name="uq_production_batches_company_number"),
    )
    op.create_index(
        "ix_production_batches_company_brand_date",
        "production_batches",
        ["company_id", "brand_id", "planned_date"],
    )
    op.create_index(
        "ix_production_batches_brand_status",
        "production_batches",
        ["brand_id", "status"],
    )
    op.create_index("ix_production_batches_raw_location_id", "production_batches", ["raw_location_id"])
    op.create_index("ix_production_batches_ready_location_id", "production_batches", ["ready_location_id"])

    op.create_table(
        "production_batch_lines",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_type", sa.String(length=20), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("destination_location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("planned_qty", sa.Numeric(15, 4), nullable=False),
        sa.Column("actual_qty", sa.Numeric(15, 4), nullable=True),
        sa.Column("unit_code", sa.String(length=30), nullable=False),
        sa.Column("cost_per_unit", sa.Numeric(15, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("line_type IN ('input', 'output')", name="ck_production_batch_lines_type"),
        sa.CheckConstraint("planned_qty > 0", name="ck_production_batch_lines_planned_qty"),
        sa.CheckConstraint("actual_qty IS NULL OR actual_qty >= 0", name="ck_production_batch_lines_actual_qty"),
        sa.CheckConstraint(
            "(line_type = 'input' AND source_location_id IS NOT NULL AND destination_location_id IS NULL) "
            "OR (line_type = 'output' AND source_location_id IS NULL AND destination_location_id IS NOT NULL)",
            name="ck_production_batch_lines_location_direction",
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["production_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
        sa.ForeignKeyConstraint(["source_location_id"], ["stock_locations.id"]),
        sa.ForeignKeyConstraint(["destination_location_id"], ["stock_locations.id"]),
    )
    op.create_index("ix_production_batch_lines_batch_id", "production_batch_lines", ["batch_id"])
    op.create_index("ix_production_batch_lines_product_id", "production_batch_lines", ["product_id"])
    op.create_index(
        "ix_production_batch_lines_batch_type_order",
        "production_batch_lines",
        ["batch_id", "line_type", "sort_order"],
    )


def downgrade() -> None:
    op.drop_table("production_batch_lines")
    op.drop_table("production_batches")
