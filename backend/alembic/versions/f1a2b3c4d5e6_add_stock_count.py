"""add_stock_count

Revision ID: f1a2b3c4d5e6
Revises: c4d5e6f7a8b9
Create Date: 2026-05-14 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("stock_count_sessions"):
        op.create_table(
            "stock_count_sessions",
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("branch_id", sa.UUID(), nullable=False),
            sa.Column("location_id", sa.UUID(), nullable=False),
            sa.Column("session_number", sa.String(length=30), nullable=False),
            sa.Column("status", sa.String(length=20), server_default=sa.text("'draft'"), nullable=False),
            sa.Column("count_date", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.UUID(), nullable=False),
            sa.Column("completed_by", sa.UUID(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("total_items", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("items_matched", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("items_over", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("items_short", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("total_variance_value", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_stock_count_sessions_branch_id_branches")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_stock_count_sessions_company_id_companies")),
            sa.ForeignKeyConstraint(["completed_by"], ["users.id"], name=op.f("fk_stock_count_sessions_completed_by_users")),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_stock_count_sessions_created_by_users")),
            sa.ForeignKeyConstraint(["location_id"], ["stock_locations.id"], name=op.f("fk_stock_count_sessions_location_id_stock_locations")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_count_sessions")),
            sa.UniqueConstraint("session_number", name=op.f("uq_stock_count_sessions_session_number")),
        )
        op.create_index(op.f("ix_stock_count_sessions_company_id"), "stock_count_sessions", ["company_id"], unique=False)
        op.create_index(op.f("ix_stock_count_sessions_branch_id"), "stock_count_sessions", ["branch_id"], unique=False)
        op.create_index(op.f("ix_stock_count_sessions_location_id"), "stock_count_sessions", ["location_id"], unique=False)
        op.create_index("ix_stock_count_sessions_company_id_session_number", "stock_count_sessions", ["company_id", "session_number"], unique=False)
        op.create_index("ix_stock_count_sessions_status", "stock_count_sessions", ["status"], unique=False)

    if not inspector.has_table("stock_count_items"):
        op.create_table(
            "stock_count_items",
            sa.Column("session_id", sa.UUID(), nullable=False),
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("product_id", sa.UUID(), nullable=False),
            sa.Column("variant_id", sa.UUID(), nullable=True),
            sa.Column("product_name", sa.String(length=500), nullable=False),
            sa.Column("sku", sa.String(length=100), nullable=False),
            sa.Column("unit_code", sa.String(length=20), nullable=True),
            sa.Column("expected_qty", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
            sa.Column("actual_qty", sa.Numeric(15, 4), nullable=True),
            sa.Column("variance_qty", sa.Numeric(15, 4), nullable=True),
            sa.Column("cost_per_unit", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
            sa.Column("variance_value", sa.Numeric(15, 2), nullable=True),
            sa.Column("counted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("counted_by", sa.UUID(), nullable=True),
            sa.Column("note", sa.String(length=500), nullable=True),
            sa.Column("is_adjusted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_stock_count_items_company_id_companies")),
            sa.ForeignKeyConstraint(["counted_by"], ["users.id"], name=op.f("fk_stock_count_items_counted_by_users")),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_stock_count_items_product_id_products")),
            sa.ForeignKeyConstraint(["session_id"], ["stock_count_sessions.id"], name=op.f("fk_stock_count_items_session_id_stock_count_sessions")),
            sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"], name=op.f("fk_stock_count_items_variant_id_product_variants")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_count_items")),
            sa.UniqueConstraint("session_id", "product_id", "variant_id", name="uq_stock_count_items_session_product_variant"),
        )
        op.create_index(op.f("ix_stock_count_items_session_id"), "stock_count_items", ["session_id"], unique=False)
        op.create_index(op.f("ix_stock_count_items_company_id"), "stock_count_items", ["company_id"], unique=False)
        op.create_index(op.f("ix_stock_count_items_product_id"), "stock_count_items", ["product_id"], unique=False)
        op.create_index(op.f("ix_stock_count_items_variant_id"), "stock_count_items", ["variant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_stock_count_items_variant_id"), table_name="stock_count_items")
    op.drop_index(op.f("ix_stock_count_items_product_id"), table_name="stock_count_items")
    op.drop_index(op.f("ix_stock_count_items_company_id"), table_name="stock_count_items")
    op.drop_index(op.f("ix_stock_count_items_session_id"), table_name="stock_count_items")
    op.drop_table("stock_count_items")
    op.drop_index("ix_stock_count_sessions_status", table_name="stock_count_sessions")
    op.drop_index("ix_stock_count_sessions_company_id_session_number", table_name="stock_count_sessions")
    op.drop_index(op.f("ix_stock_count_sessions_location_id"), table_name="stock_count_sessions")
    op.drop_index(op.f("ix_stock_count_sessions_branch_id"), table_name="stock_count_sessions")
    op.drop_index(op.f("ix_stock_count_sessions_company_id"), table_name="stock_count_sessions")
    op.drop_table("stock_count_sessions")
