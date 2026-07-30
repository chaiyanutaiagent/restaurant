"""add_accounting

Revision ID: e63d4c134990
Revises: ab12cd34ef56
Create Date: 2026-05-14 05:27:20.985811

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e63d4c134990"
down_revision: Union[str, None] = "ab12cd34ef56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("name_en", sa.String(length=255), nullable=True),
        sa.Column("account_type", sa.String(length=20), nullable=False),
        sa.Column("account_subtype", sa.String(length=50), nullable=True),
        sa.Column(
            "normal_balance",
            sa.String(length=6),
            server_default=sa.text("'debit'"),
            nullable=False,
        ),
        sa.Column("is_header", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_accounts_company_id_companies")),
        sa.ForeignKeyConstraint(["parent_id"], ["accounts.id"], name=op.f("fk_accounts_parent_id_accounts")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
        sa.UniqueConstraint("company_id", "code", name="uq_accounts_company_id_code"),
    )
    op.create_index(op.f("ix_accounts_company_id"), "accounts", ["company_id"], unique=False)
    op.create_index("ix_accounts_parent_id", "accounts", ["parent_id"], unique=False)

    op.create_table(
        "account_balances",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("opening_balance", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("debit_total", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("credit_total", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("closing_balance", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], name=op.f("fk_account_balances_account_id_accounts")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_account_balances_company_id_companies")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_balances")),
        sa.UniqueConstraint("account_id", "period_year", "period_month", name="uq_account_balances_account_period"),
    )
    op.create_index(op.f("ix_account_balances_account_id"), "account_balances", ["account_id"], unique=False)
    op.create_index(op.f("ix_account_balances_company_id"), "account_balances", ["company_id"], unique=False)

    op.create_table(
        "journal_entries",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=True),
        sa.Column("entry_number", sa.String(length=30), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("entry_type", sa.String(length=30), nullable=False),
        sa.Column("reference_type", sa.String(length=50), nullable=True),
        sa.Column("reference_id", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_posted", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_reversed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("reversed_by", sa.UUID(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_journal_entries_branch_id_branches")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_journal_entries_company_id_companies")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_journal_entries_created_by_users")),
        sa.ForeignKeyConstraint(["reversed_by"], ["journal_entries.id"], name=op.f("fk_journal_entries_reversed_by_journal_entries")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_entries")),
        sa.UniqueConstraint("entry_number", name=op.f("uq_journal_entries_entry_number")),
    )
    op.create_index(op.f("ix_journal_entries_branch_id"), "journal_entries", ["branch_id"], unique=False)
    op.create_index("ix_journal_entries_company_entry_number", "journal_entries", ["company_id", "entry_number"], unique=False)
    op.create_index(op.f("ix_journal_entries_company_id"), "journal_entries", ["company_id"], unique=False)
    op.create_index(op.f("ix_journal_entries_entry_date"), "journal_entries", ["entry_date"], unique=False)
    op.create_index("ix_journal_entries_period_year_period_month", "journal_entries", ["period_year", "period_month"], unique=False)
    op.create_index(op.f("ix_journal_entries_reference_id"), "journal_entries", ["reference_id"], unique=False)
    op.create_index(
        "ix_journal_entries_reference_type_reference_id",
        "journal_entries",
        ["reference_type", "reference_id"],
        unique=False,
    )

    op.create_table(
        "journal_lines",
        sa.Column("entry_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("debit_amount", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("credit_amount", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.CheckConstraint("NOT (debit_amount > 0 AND credit_amount > 0)", name=op.f("ck_journal_lines_journal_lines_single_side")),
        sa.CheckConstraint("debit_amount >= 0 AND credit_amount >= 0", name=op.f("ck_journal_lines_journal_lines_non_negative")),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], name=op.f("fk_journal_lines_account_id_accounts")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_journal_lines_company_id_companies")),
        sa.ForeignKeyConstraint(["entry_id"], ["journal_entries.id"], name=op.f("fk_journal_lines_entry_id_journal_entries")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_lines")),
    )
    op.create_index(op.f("ix_journal_lines_account_id"), "journal_lines", ["account_id"], unique=False)
    op.create_index(op.f("ix_journal_lines_company_id"), "journal_lines", ["company_id"], unique=False)
    op.create_index(op.f("ix_journal_lines_entry_id"), "journal_lines", ["entry_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_journal_lines_entry_id"), table_name="journal_lines")
    op.drop_index(op.f("ix_journal_lines_company_id"), table_name="journal_lines")
    op.drop_index(op.f("ix_journal_lines_account_id"), table_name="journal_lines")
    op.drop_table("journal_lines")
    op.drop_index("ix_journal_entries_reference_type_reference_id", table_name="journal_entries")
    op.drop_index(op.f("ix_journal_entries_reference_id"), table_name="journal_entries")
    op.drop_index("ix_journal_entries_period_year_period_month", table_name="journal_entries")
    op.drop_index(op.f("ix_journal_entries_entry_date"), table_name="journal_entries")
    op.drop_index(op.f("ix_journal_entries_company_id"), table_name="journal_entries")
    op.drop_index("ix_journal_entries_company_entry_number", table_name="journal_entries")
    op.drop_index(op.f("ix_journal_entries_branch_id"), table_name="journal_entries")
    op.drop_table("journal_entries")
    op.drop_index(op.f("ix_account_balances_company_id"), table_name="account_balances")
    op.drop_index(op.f("ix_account_balances_account_id"), table_name="account_balances")
    op.drop_table("account_balances")
    op.drop_index("ix_accounts_parent_id", table_name="accounts")
    op.drop_index(op.f("ix_accounts_company_id"), table_name="accounts")
    op.drop_table("accounts")
