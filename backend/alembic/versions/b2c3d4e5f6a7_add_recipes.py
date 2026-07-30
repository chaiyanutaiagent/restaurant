"""add_recipes

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-31 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # recipes
    op.create_table(
        "recipes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True), sa.ForeignKey("branches.id"), nullable=True),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("yield_qty", sa.Numeric(10, 4), nullable=False, server_default=sa.text("1")),
        sa.Column("yield_unit", sa.String(30), nullable=False, server_default=sa.text("'แก้ว'")),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"), onupdate=sa.text("now()")),
        sa.UniqueConstraint("product_id", "branch_id", name="uq_recipes_product_branch"),
    )
    op.create_index("ix_recipes_company_id", "recipes", ["company_id"])
    op.create_index("ix_recipes_product_id", "recipes", ["product_id"])
    op.create_index("ix_recipes_branch_id", "recipes", ["branch_id"])

    # recipe_ingredients
    op.create_table(
        "recipe_ingredients",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("recipe_id", UUID(as_uuid=True), sa.ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ingredient_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("notes", sa.String(255), nullable=True),
    )
    op.create_index("ix_recipe_ingredients_recipe_id", "recipe_ingredients", ["recipe_id"])
    op.create_index("ix_recipe_ingredients_ingredient_id", "recipe_ingredients", ["ingredient_id"])


def downgrade() -> None:
    op.drop_table("recipe_ingredients")
    op.drop_table("recipes")
