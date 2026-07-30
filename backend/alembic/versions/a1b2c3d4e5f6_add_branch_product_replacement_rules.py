"""add branch product replacement rules

Revision ID: a1b2c3d4e5f6
Revises: 9f8e7d6c5b4a
Create Date: 2026-05-24 16:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "9f8e7d6c5b4a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "branch_product_replacement_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("replacement_product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["replacement_product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["source_product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("branch_id", "source_product_id", name="uq_branch_product_replacement_rules_branch_source"),
    )
    op.create_index(
        op.f("ix_branch_product_replacement_rules_company_id"),
        "branch_product_replacement_rules",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_branch_product_replacement_rules_branch_id"),
        "branch_product_replacement_rules",
        ["branch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_branch_product_replacement_rules_source_product_id"),
        "branch_product_replacement_rules",
        ["source_product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_branch_product_replacement_rules_replacement_product_id"),
        "branch_product_replacement_rules",
        ["replacement_product_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_branch_product_replacement_rules_replacement_product_id"), table_name="branch_product_replacement_rules")
    op.drop_index(op.f("ix_branch_product_replacement_rules_source_product_id"), table_name="branch_product_replacement_rules")
    op.drop_index(op.f("ix_branch_product_replacement_rules_branch_id"), table_name="branch_product_replacement_rules")
    op.drop_index(op.f("ix_branch_product_replacement_rules_company_id"), table_name="branch_product_replacement_rules")
    op.drop_table("branch_product_replacement_rules")
