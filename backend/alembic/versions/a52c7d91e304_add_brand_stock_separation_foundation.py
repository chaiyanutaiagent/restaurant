"""add restaurant stock separation foundation

Revision ID: a52c7d91e304
Revises: f40a7c13e426
Create Date: 2026-07-22 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a52c7d91e304"
down_revision: Union[str, None] = "f40a7c13e426"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INVENTORY_ROLES = "'central_raw', 'central_ready', 'store_local', 'not_stocked'"


def upgrade() -> None:
    op.add_column(
        "brands",
        sa.Column(
            "central_ready_location_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_brands_central_ready_location_id",
        "brands",
        ["central_ready_location_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_brands_central_ready_location_id_stock_locations",
        "brands",
        "stock_locations",
        ["central_ready_location_id"],
        ["id"],
    )

    op.add_column(
        "products",
        sa.Column(
            "inventory_role",
            sa.String(length=30),
            nullable=True,
            comment="central_raw, central_ready, store_local, or not_stocked",
        ),
    )
    op.create_index(
        "ix_products_inventory_role",
        "products",
        ["inventory_role"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_products_inventory_role",
        "products",
        f"inventory_role IS NULL OR inventory_role IN ({INVENTORY_ROLES})",
    )

    op.add_column(
        "user_branches",
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_user_branches_brand_id",
        "user_branches",
        ["brand_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_user_branches_brand_id_brands",
        "user_branches",
        "brands",
        ["brand_id"],
        ["id"],
    )
    op.execute(
        """
        UPDATE user_branches AS ub
        SET brand_id = (
            SELECT uar.brand_id
            FROM user_access_requests AS uar
            WHERE uar.activated_user_id = ub.user_id
              AND uar.branch_id = ub.branch_id
              AND uar.brand_id IS NOT NULL
            ORDER BY uar.activated_at DESC NULLS LAST, uar.updated_at DESC
            LIMIT 1
        )
        WHERE ub.brand_id IS NULL
          AND EXISTS (
              SELECT 1
              FROM user_access_requests AS uar
              WHERE uar.activated_user_id = ub.user_id
                AND uar.branch_id = ub.branch_id
                AND uar.brand_id IS NOT NULL
          )
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_user_branches_brand_id_brands",
        "user_branches",
        type_="foreignkey",
    )
    op.drop_index("ix_user_branches_brand_id", table_name="user_branches")
    op.drop_column("user_branches", "brand_id")

    op.drop_constraint("ck_products_inventory_role", "products", type_="check")
    op.drop_index("ix_products_inventory_role", table_name="products")
    op.drop_column("products", "inventory_role")

    op.drop_constraint(
        "fk_brands_central_ready_location_id_stock_locations",
        "brands",
        type_="foreignkey",
    )
    op.drop_index("ix_brands_central_ready_location_id", table_name="brands")
    op.drop_column("brands", "central_ready_location_id")
