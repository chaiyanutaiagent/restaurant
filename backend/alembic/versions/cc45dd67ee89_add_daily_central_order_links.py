"""add daily central order links

Revision ID: cc45dd67ee89
Revises: bb12cc34dd56
Create Date: 2026-07-07 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "cc45dd67ee89"
down_revision: Union[str, None] = "bb12cc34dd56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("wap_shift_closures", sa.Column("round_no", sa.Integer(), nullable=False, server_default=sa.text("1")))
    op.create_index(
        "ix_wap_shift_closures_brand_branch_date_round",
        "wap_shift_closures",
        ["brand_id", "branch_id", "business_date", "round_no"],
    )

    op.create_table(
        "central_order_shift_closures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("central_order_id", UUID(as_uuid=True), sa.ForeignKey("central_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shift_closure_id", UUID(as_uuid=True), sa.ForeignKey("wap_shift_closures.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=True),
        sa.Column("branch_id", UUID(as_uuid=True), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("business_date", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_central_order_shift_closures_closure",
        "central_order_shift_closures",
        ["shift_closure_id"],
    )
    op.create_index("ix_central_order_shift_closures_order", "central_order_shift_closures", ["central_order_id"])
    op.create_index("ix_central_order_shift_closures_company_id", "central_order_shift_closures", ["company_id"])
    op.create_index("ix_central_order_shift_closures_brand_id", "central_order_shift_closures", ["brand_id"])
    op.create_index("ix_central_order_shift_closures_branch_id", "central_order_shift_closures", ["branch_id"])
    op.create_index(
        "ix_central_order_shift_closures_branch_date",
        "central_order_shift_closures",
        ["branch_id", "business_date"],
    )

    op.execute(
        """
        INSERT INTO central_order_shift_closures (
            central_order_id,
            shift_closure_id,
            company_id,
            brand_id,
            branch_id,
            business_date,
            created_at
        )
        SELECT
            co.id,
            co.shift_closure_id,
            co.company_id,
            co.brand_id,
            co.branch_id,
            co.business_date,
            co.created_at
        FROM central_orders co
        WHERE co.shift_closure_id IS NOT NULL
        ON CONFLICT (shift_closure_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("central_order_shift_closures")
    op.drop_index("ix_wap_shift_closures_brand_branch_date_round", table_name="wap_shift_closures")
    op.drop_column("wap_shift_closures", "round_no")
