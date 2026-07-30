"""add_credit_topup_requests

Revision ID: bb12cc34dd56
Revises: f0a1b2c3d4e5
Create Date: 2026-07-07 11:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "bb12cc34dd56"
down_revision: Union[str, None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credit_topup_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("credit_accounts.id"), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("slip_url", sa.Text, nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("requested_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_credit_topup_requests_company_id", "credit_topup_requests", ["company_id"])
    op.create_index("ix_credit_topup_requests_brand_id", "credit_topup_requests", ["brand_id"])
    op.create_index("ix_credit_topup_requests_branch_id", "credit_topup_requests", ["branch_id"])
    op.create_index("ix_credit_topup_requests_account_id", "credit_topup_requests", ["account_id"])
    op.create_index("ix_credit_topup_requests_requested_by", "credit_topup_requests", ["requested_by"])
    op.create_index("ix_credit_topup_requests_reviewed_by", "credit_topup_requests", ["reviewed_by"])
    op.create_index(
        "ix_credit_topup_requests_company_brand_status",
        "credit_topup_requests",
        ["company_id", "brand_id", "status"],
    )
    op.create_index(
        "ix_credit_topup_requests_branch_status",
        "credit_topup_requests",
        ["branch_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("credit_topup_requests")
