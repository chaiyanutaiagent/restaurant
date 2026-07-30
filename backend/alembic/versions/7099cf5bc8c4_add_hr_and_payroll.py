"""add_hr_and_payroll

Revision ID: 7099cf5bc8c4
Revises: 3335eaff7ed8
Create Date: 2026-05-15 00:51:56.266974

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7099cf5bc8c4"
down_revision: Union[str, None] = "3335eaff7ed8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("name_en", sa.String(length=255), nullable=True),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_departments_company_id_companies")),
        sa.ForeignKeyConstraint(["parent_id"], ["departments.id"], name=op.f("fk_departments_parent_id_departments")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_departments")),
        sa.UniqueConstraint("company_id", "code", name="uq_departments_company_id_code"),
    )
    op.create_index(op.f("ix_departments_company_id"), "departments", ["company_id"], unique=False)

    op.create_table(
        "positions",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("department_id", sa.UUID(), nullable=True),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("name_en", sa.String(length=255), nullable=True),
        sa.Column("level", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_positions_company_id_companies")),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], name=op.f("fk_positions_department_id_departments")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_positions")),
        sa.UniqueConstraint("company_id", "code", name="uq_positions_company_id_code"),
    )
    op.create_index(op.f("ix_positions_company_id"), "positions", ["company_id"], unique=False)
    op.create_index(op.f("ix_positions_department_id"), "positions", ["department_id"], unique=False)

    op.create_table(
        "employees",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("employee_code", sa.String(length=20), nullable=False),
        sa.Column("department_id", sa.UUID(), nullable=True),
        sa.Column("position_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=10), nullable=True),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("first_name_en", sa.String(length=100), nullable=True),
        sa.Column("last_name_en", sa.String(length=100), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("gender", sa.String(length=10), nullable=True),
        sa.Column("national_id", sa.String(length=20), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("hire_date", sa.Date(), nullable=False),
        sa.Column("probation_end_date", sa.Date(), nullable=True),
        sa.Column("termination_date", sa.Date(), nullable=True),
        sa.Column("employment_type", sa.String(length=20), server_default=sa.text("'fulltime'"), nullable=False),
        sa.Column("base_salary", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("salary_type", sa.String(length=20), server_default=sa.text("'monthly'"), nullable=False),
        sa.Column("bank_name", sa.String(length=100), nullable=True),
        sa.Column("bank_account", sa.String(length=30), nullable=True),
        sa.Column("bank_account_name", sa.String(length=255), nullable=True),
        sa.Column("tax_id", sa.String(length=20), nullable=True),
        sa.Column("sso_number", sa.String(length=20), nullable=True),
        sa.Column("sso_registered", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("pit_allowance_personal", sa.Numeric(precision=15, scale=2), server_default=sa.text("60000"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_employees_branch_id_branches")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_employees_company_id_companies")),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], name=op.f("fk_employees_department_id_departments")),
        sa.ForeignKeyConstraint(["position_id"], ["positions.id"], name=op.f("fk_employees_position_id_positions")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_employees_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employees")),
        sa.UniqueConstraint("company_id", "employee_code", name="uq_employees_company_id_employee_code"),
        sa.UniqueConstraint("national_id", name=op.f("uq_employees_national_id")),
        sa.UniqueConstraint("user_id", name=op.f("uq_employees_user_id")),
    )
    op.create_index(op.f("ix_employees_branch_id"), "employees", ["branch_id"], unique=False)
    op.create_index(op.f("ix_employees_company_id"), "employees", ["company_id"], unique=False)
    op.create_index("ix_employees_company_id_national_id", "employees", ["company_id", "national_id"], unique=False)
    op.create_index(op.f("ix_employees_department_id"), "employees", ["department_id"], unique=False)
    op.create_index(op.f("ix_employees_position_id"), "employees", ["position_id"], unique=False)
    op.create_index("ix_employees_user_id", "employees", ["user_id"], unique=False)

    op.add_column("departments", sa.Column("manager_id", sa.UUID(), nullable=True))
    op.create_foreign_key(op.f("fk_departments_manager_id_employees"), "departments", "employees", ["manager_id"], ["id"])

    op.create_table(
        "salary_components",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("component_type", sa.String(length=20), nullable=False),
        sa.Column("is_taxable", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_sso_base", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_fixed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_salary_components_company_id_companies")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_salary_components")),
        sa.UniqueConstraint("company_id", "code", name="uq_salary_components_company_id_code"),
    )
    op.create_index(op.f("ix_salary_components_company_id"), "salary_components", ["company_id"], unique=False)

    op.create_table(
        "employee_salaries",
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("component_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_employee_salaries_company_id_companies")),
        sa.ForeignKeyConstraint(["component_id"], ["salary_components.id"], name=op.f("fk_employee_salaries_component_id_salary_components")),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], name=op.f("fk_employee_salaries_employee_id_employees")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employee_salaries")),
    )
    op.create_index(op.f("ix_employee_salaries_company_id"), "employee_salaries", ["company_id"], unique=False)
    op.create_index(op.f("ix_employee_salaries_employee_id"), "employee_salaries", ["employee_id"], unique=False)
    op.create_index(
        "ix_employee_salaries_employee_component_active",
        "employee_salaries",
        ["employee_id", "component_id"],
        unique=True,
        postgresql_where=sa.text("effective_to IS NULL"),
    )

    op.create_table(
        "payroll_runs",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=True),
        sa.Column("run_number", sa.String(length=30), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("pay_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("total_employees", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_gross", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("total_deductions", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("total_net", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("total_sso_employee", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("total_sso_employer", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("total_pit", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("processed_by", sa.UUID(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_payroll_runs_branch_id_branches")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_payroll_runs_company_id_companies")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_payroll_runs_created_by_users")),
        sa.ForeignKeyConstraint(["processed_by"], ["users.id"], name=op.f("fk_payroll_runs_processed_by_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payroll_runs")),
        sa.UniqueConstraint("company_id", "period_year", "period_month", name="uq_payroll_runs_company_period"),
        sa.UniqueConstraint("run_number", name=op.f("uq_payroll_runs_run_number")),
    )
    op.create_index(op.f("ix_payroll_runs_branch_id"), "payroll_runs", ["branch_id"], unique=False)
    op.create_index(op.f("ix_payroll_runs_company_id"), "payroll_runs", ["company_id"], unique=False)

    op.create_table(
        "payroll_items",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("base_salary", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("earnings_total", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("sso_employee", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("sso_employer", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("pit_withheld", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("other_deductions", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("total_deductions", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("net_pay", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("ytd_gross", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("ytd_pit", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("employee_name", sa.String(length=255), nullable=False),
        sa.Column("employee_code", sa.String(length=20), nullable=False),
        sa.Column("position_name", sa.String(length=255), nullable=True),
        sa.Column("department_name", sa.String(length=255), nullable=True),
        sa.Column("bank_account", sa.String(length=30), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_payroll_items_company_id_companies")),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], name=op.f("fk_payroll_items_employee_id_employees")),
        sa.ForeignKeyConstraint(["run_id"], ["payroll_runs.id"], name=op.f("fk_payroll_items_run_id_payroll_runs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payroll_items")),
        sa.UniqueConstraint("run_id", "employee_id", name="uq_payroll_items_run_employee"),
    )
    op.create_index(op.f("ix_payroll_items_company_id"), "payroll_items", ["company_id"], unique=False)
    op.create_index(op.f("ix_payroll_items_employee_id"), "payroll_items", ["employee_id"], unique=False)
    op.create_index(op.f("ix_payroll_items_run_id"), "payroll_items", ["run_id"], unique=False)

    op.create_table(
        "payroll_item_lines",
        sa.Column("payroll_item_id", sa.UUID(), nullable=False),
        sa.Column("component_id", sa.UUID(), nullable=False),
        sa.Column("component_name", sa.String(length=255), nullable=False),
        sa.Column("component_type", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["component_id"], ["salary_components.id"], name=op.f("fk_payroll_item_lines_component_id_salary_components")),
        sa.ForeignKeyConstraint(["payroll_item_id"], ["payroll_items.id"], name=op.f("fk_payroll_item_lines_payroll_item_id_payroll_items")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payroll_item_lines")),
    )
    op.create_index(op.f("ix_payroll_item_lines_payroll_item_id"), "payroll_item_lines", ["payroll_item_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_payroll_item_lines_payroll_item_id"), table_name="payroll_item_lines")
    op.drop_table("payroll_item_lines")
    op.drop_index(op.f("ix_payroll_items_run_id"), table_name="payroll_items")
    op.drop_index(op.f("ix_payroll_items_employee_id"), table_name="payroll_items")
    op.drop_index(op.f("ix_payroll_items_company_id"), table_name="payroll_items")
    op.drop_table("payroll_items")
    op.drop_index(op.f("ix_payroll_runs_company_id"), table_name="payroll_runs")
    op.drop_index(op.f("ix_payroll_runs_branch_id"), table_name="payroll_runs")
    op.drop_table("payroll_runs")
    op.drop_index("ix_employee_salaries_employee_component_active", table_name="employee_salaries")
    op.drop_index(op.f("ix_employee_salaries_employee_id"), table_name="employee_salaries")
    op.drop_index(op.f("ix_employee_salaries_company_id"), table_name="employee_salaries")
    op.drop_table("employee_salaries")
    op.drop_index(op.f("ix_salary_components_company_id"), table_name="salary_components")
    op.drop_table("salary_components")
    op.drop_constraint(op.f("fk_departments_manager_id_employees"), "departments", type_="foreignkey")
    op.drop_column("departments", "manager_id")
    op.drop_index("ix_employees_user_id", table_name="employees")
    op.drop_index(op.f("ix_employees_position_id"), table_name="employees")
    op.drop_index(op.f("ix_employees_department_id"), table_name="employees")
    op.drop_index("ix_employees_company_id_national_id", table_name="employees")
    op.drop_index(op.f("ix_employees_company_id"), table_name="employees")
    op.drop_index(op.f("ix_employees_branch_id"), table_name="employees")
    op.drop_table("employees")
    op.drop_index(op.f("ix_positions_department_id"), table_name="positions")
    op.drop_index(op.f("ix_positions_company_id"), table_name="positions")
    op.drop_table("positions")
    op.drop_index(op.f("ix_departments_company_id"), table_name="departments")
    op.drop_table("departments")
