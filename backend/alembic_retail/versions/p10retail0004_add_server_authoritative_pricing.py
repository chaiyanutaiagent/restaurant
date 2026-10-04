"""add server-authoritative pricing quotes to the Retail boundary

Revision ID: p10retail0004
Revises: p9retail0003
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p10retail0004"
down_revision: Union[str, None] = "p9retail0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "price_calculations",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("brand_id", sa.UUID(), nullable=True),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column("operation", sa.String(length=30), nullable=False, server_default=sa.text("'calculate'")),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'THB'")),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("calculation_hash", sa.String(length=64), nullable=False),
        sa.Column("calculation_version", sa.String(length=30), nullable=False),
        sa.Column("cart_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("price_list_id", sa.UUID(), nullable=True),
        sa.Column("price_list_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'quoted'")),
        sa.Column("consumed_order_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_price_calculations_company_id_companies")),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], name=op.f("fk_price_calculations_brand_id_brands")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_price_calculations_branch_id_branches")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_price_calculations_user_id_users")),
        sa.ForeignKeyConstraint(["price_list_id"], ["price_lists.id"], name=op.f("fk_price_calculations_price_list_id_price_lists")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_calculations")),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "operation",
            "idempotency_key",
            name="uq_price_calculations_idempotency",
        ),
    )
    op.create_index(
        "ix_price_calculations_context",
        "price_calculations",
        ["company_id", "branch_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_price_calculations_context", table_name="price_calculations")
    op.drop_table("price_calculations")
