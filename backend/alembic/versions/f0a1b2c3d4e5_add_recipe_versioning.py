"""add_recipe_versioning

Revision ID: f0a1b2c3d4e5
Revises: ad45ef67ab89
Create Date: 2026-07-05 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "ad45ef67ab89"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_recipes_product_branch", "recipes", type_="unique")
    op.add_column("recipes", sa.Column("recipe_type", sa.String(30), nullable=False, server_default=sa.text("'menu_recipe'")))
    op.add_column("recipes", sa.Column("version_no", sa.Integer(), nullable=False, server_default=sa.text("1")))
    op.add_column("recipes", sa.Column("effective_from", sa.Date(), nullable=True))
    op.add_column("recipes", sa.Column("effective_to", sa.Date(), nullable=True))
    op.add_column("recipes", sa.Column("loss_percent", sa.Numeric(7, 4), nullable=False, server_default=sa.text("0")))
    op.create_index(
        "ix_recipes_product_branch_type_active",
        "recipes",
        ["product_id", "branch_id", "recipe_type", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_recipes_product_branch_type_active", table_name="recipes")
    op.drop_column("recipes", "loss_percent")
    op.drop_column("recipes", "effective_to")
    op.drop_column("recipes", "effective_from")
    op.drop_column("recipes", "version_no")
    op.drop_column("recipes", "recipe_type")
    op.create_unique_constraint("uq_recipes_product_branch", "recipes", ["product_id", "branch_id"])
