"""add tenant brand branch foundation

Revision ID: 5a6b7c8d9e01
Revises: 4e5f6a7b8c93
Create Date: 2026-07-31 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5a6b7c8d9e01"
down_revision: Union[str, None] = "4e5f6a7b8c93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BUSINESS_TYPES = "'restaurant', 'retail_pos', 'takeaway'"


def upgrade() -> None:
    op.add_column(
        "brands",
        sa.Column(
            "business_type",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'restaurant'"),
        ),
    )
    op.create_index("ix_brands_business_type", "brands", ["business_type"])
    op.create_check_constraint(
        "ck_brands_business_type",
        "brands",
        f"business_type IN ({BUSINESS_TYPES})",
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM brand_branches
                WHERE is_active
                GROUP BY branch_id
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'P1-FOUNDATION-01 requires at most one active Brand per Branch';
            END IF;
        END
        $$
        """
    )
    op.create_index(
        "uq_brand_branches_active_branch",
        "brand_branches",
        ["branch_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.add_column(
        "user_branches",
        sa.Column("business_type", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "user_branches",
        sa.Column("target_database", sa.String(length=30), nullable=True),
    )
    op.create_index("ix_user_branches_business_type", "user_branches", ["business_type"])
    op.create_index("ix_user_branches_target_database", "user_branches", ["target_database"])

    op.execute(
        """
        UPDATE user_branches AS ub
        SET brand_id = resolved.brand_id
        FROM (
            SELECT branch_id, min(brand_id::text)::uuid AS brand_id
            FROM brand_branches
            WHERE is_active
            GROUP BY branch_id
            HAVING count(*) = 1
        ) AS resolved
        WHERE ub.branch_id = resolved.branch_id
          AND ub.brand_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE user_branches AS ub
        SET business_type = brand.business_type,
            target_database = brand.business_type
        FROM brands AS brand
        WHERE ub.brand_id = brand.id
        """
    )
    op.create_check_constraint(
        "ck_user_branches_business_type",
        "user_branches",
        f"business_type IS NULL OR business_type IN ({BUSINESS_TYPES})",
    )
    op.create_check_constraint(
        "ck_user_branches_target_database",
        "user_branches",
        f"target_database IS NULL OR target_database IN ({BUSINESS_TYPES})",
    )
    op.create_check_constraint(
        "ck_user_branches_context_complete",
        "user_branches",
        "(brand_id IS NULL AND business_type IS NULL AND target_database IS NULL) "
        "OR (brand_id IS NOT NULL AND business_type IS NOT NULL "
        "AND target_database = business_type)",
    )


def downgrade() -> None:
    # Use exact physical names because the project naming convention prefixes
    # explicit check-constraint names with the table name.
    op.execute(
        "ALTER TABLE user_branches DROP CONSTRAINT IF EXISTS "
        "ck_user_branches_ck_user_branches_context_complete"
    )
    # Compatibility for development databases upgraded while this migration
    # was being verified before the stronger completeness check was finalized.
    op.execute(
        "ALTER TABLE user_branches DROP CONSTRAINT IF EXISTS "
        "ck_user_branches_ck_user_branches_business_database_match"
    )
    op.drop_constraint(
        "ck_user_branches_target_database",
        "user_branches",
        type_="check",
    )
    op.drop_constraint(
        "ck_user_branches_business_type",
        "user_branches",
        type_="check",
    )
    op.drop_index("ix_user_branches_target_database", table_name="user_branches")
    op.drop_index("ix_user_branches_business_type", table_name="user_branches")
    op.drop_column("user_branches", "target_database")
    op.drop_column("user_branches", "business_type")

    op.drop_index("uq_brand_branches_active_branch", table_name="brand_branches")
    op.drop_constraint("ck_brands_business_type", "brands", type_="check")
    op.drop_index("ix_brands_business_type", table_name="brands")
    op.drop_column("brands", "business_type")
