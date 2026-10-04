"""add shared ERP tax configuration

Revision ID: p15taxset0017
Revises: p14dist0016
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p15taxset0017"
down_revision: Union[str, None] = "p14dist0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _id() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def upgrade() -> None:
    op.create_table(
        "company_tax_profiles",
        _id(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=True),
        sa.Column("tax_id", sa.String(length=13), nullable=True),
        sa.Column("vat_registered", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("vat_registration_date", sa.Date(), nullable=True),
        sa.Column("registered_address", sa.Text(), nullable=True),
        sa.Column("default_price_vat_type", sa.String(length=20), nullable=False, server_default=sa.text("'included'")),
        sa.Column("default_vat_rate", sa.Numeric(5, 2), nullable=False, server_default=sa.text("7.00")),
        sa.Column("vat_filing_mode", sa.String(length=20), nullable=False, server_default=sa.text("'separate'")),
        sa.Column("consolidated_filing_approved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_timestamps(),
        sa.CheckConstraint("default_price_vat_type IN ('included', 'excluded', 'exempt')", name="default_vat_type"),
        sa.CheckConstraint("vat_filing_mode IN ('separate', 'consolidated')", name="filing_mode"),
        sa.CheckConstraint("default_vat_rate >= 0 AND default_vat_rate <= 100", name="default_rate"),
        sa.CheckConstraint("tax_id IS NULL OR tax_id ~ '^[0-9]{13}$'", name="tax_id_format"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.UniqueConstraint("company_id", name="uq_company_tax_profiles_company_id"),
    )
    op.create_index("ix_company_tax_profiles_company_id", "company_tax_profiles", ["company_id"])

    op.create_table(
        "branch_tax_profiles",
        _id(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tax_branch_code", sa.String(length=5), nullable=False),
        sa.Column("is_head_office", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("legal_name", sa.String(length=255), nullable=True),
        sa.Column("registered_address", sa.Text(), nullable=True),
        sa.Column("vat_registration_date", sa.Date(), nullable=True),
        sa.Column("filing_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("tax_branch_code ~ '^[0-9]{5}$'", name="code_format"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="effective_period"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.UniqueConstraint("branch_id", name="uq_branch_tax_profiles_branch_id"),
        sa.UniqueConstraint("company_id", "tax_branch_code", name="uq_branch_tax_profiles_company_tax_code"),
    )
    op.create_index("ix_branch_tax_profiles_company_id", "branch_tax_profiles", ["company_id"])
    op.create_index("ix_branch_tax_profiles_branch_id", "branch_tax_profiles", ["branch_id"])
    op.create_index("ix_branch_tax_profiles_company_branch", "branch_tax_profiles", ["company_id", "branch_id"])
    op.create_index(
        "uq_branch_tax_profiles_head_office",
        "branch_tax_profiles",
        ["company_id"],
        unique=True,
        postgresql_where=sa.text("is_head_office"),
    )

    op.create_table(
        "tax_rate_rules",
        _id(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("tax_category", sa.String(length=20), nullable=False),
        sa.Column("rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("price_vat_type", sa.String(length=20), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_timestamps(),
        sa.CheckConstraint("tax_category IN ('standard', 'zero', 'exempt')", name="category"),
        sa.CheckConstraint("price_vat_type IN ('included', 'excluded', 'exempt')", name="price_vat_type"),
        sa.CheckConstraint("rate >= 0 AND rate <= 100", name="rate"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="effective_period"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.UniqueConstraint("company_id", "code", "effective_from", name="uq_tax_rate_rules_company_code_start"),
    )
    op.create_index("ix_tax_rate_rules_company_id", "tax_rate_rules", ["company_id"])
    op.create_index("ix_tax_rate_rules_company_period", "tax_rate_rules", ["company_id", "effective_from", "effective_to"])


def downgrade() -> None:
    op.drop_table("tax_rate_rules")
    op.drop_table("branch_tax_profiles")
    op.drop_table("company_tax_profiles")
