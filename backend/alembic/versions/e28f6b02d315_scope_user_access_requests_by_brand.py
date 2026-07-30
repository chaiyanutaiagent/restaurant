"""scope user access requests by brand

Revision ID: e28f6b02d315
Revises: d17e5a91c204
Create Date: 2026-07-21 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e28f6b02d315"
down_revision: Union[str, None] = "d17e5a91c204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_access_requests", sa.Column("brand_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_user_access_requests_brand_id_brands"),
        "user_access_requests",
        "brands",
        ["brand_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_user_access_requests_brand_id"),
        "user_access_requests",
        ["brand_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_access_requests_company_brand_status",
        "user_access_requests",
        ["company_id", "brand_id", "status"],
        unique=False,
    )

    # Existing requests can be backfilled safely only when their branch belongs
    # to exactly one active brand. Ambiguous legacy rows remain company-admin only.
    op.execute(
        sa.text(
            "UPDATE user_access_requests AS request "
            "SET brand_id = mapping.brand_id "
            "FROM ("
            "  SELECT branch_id, MIN(brand_id::text)::uuid AS brand_id "
            "  FROM brand_branches "
            "  WHERE is_active = true "
            "  GROUP BY branch_id "
            "  HAVING COUNT(DISTINCT brand_id) = 1"
            ") AS mapping "
            "WHERE request.branch_id = mapping.branch_id AND request.brand_id IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_user_access_requests_company_brand_status", table_name="user_access_requests")
    op.drop_index(op.f("ix_user_access_requests_brand_id"), table_name="user_access_requests")
    op.drop_constraint(
        op.f("fk_user_access_requests_brand_id_brands"),
        "user_access_requests",
        type_="foreignkey",
    )
    op.drop_column("user_access_requests", "brand_id")
