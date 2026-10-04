"""add public ordering tokens

Revision ID: p6takeaway0004
Revises: p6takeaway0003
Create Date: 2026-09-11 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p6takeaway0004"
down_revision: Union[str, None] = "p6takeaway0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "takeaway_ordering_tokens",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("brand_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_takeaway_ordering_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_takeaway_ordering_tokens_token_hash")),
    )
    op.create_index(
        "ix_takeaway_ordering_token_scope",
        "takeaway_ordering_tokens",
        ["company_id", "brand_id", "branch_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_takeaway_ordering_token_scope", table_name="takeaway_ordering_tokens")
    op.drop_table("takeaway_ordering_tokens")
