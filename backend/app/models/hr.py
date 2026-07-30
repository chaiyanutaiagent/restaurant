from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.company import Company
    from app.models.user import User


class Department(SoftDeleteMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_departments_company_id_code"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    manager_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    company: Mapped["Company"] = relationship("Company")
    parent: Mapped["Department | None"] = relationship("Department", remote_side="Department.id", back_populates="children")
    children: Mapped[list["Department"]] = relationship("Department", back_populates="parent", order_by="Department.code.asc()")
    manager: Mapped["Employee | None"] = relationship("Employee", foreign_keys=[manager_id], post_update=True)
    positions: Mapped[list["Position"]] = relationship("Position", back_populates="department")
    employees: Mapped[list["Employee"]] = relationship("Employee", back_populates="department", foreign_keys="Employee.department_id")


class Position(SoftDeleteMixin, Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_positions_company_id_code"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    company: Mapped["Company"] = relationship("Company")
    department: Mapped["Department | None"] = relationship("Department", back_populates="positions")
    employees: Mapped[list["Employee"]] = relationship("Employee", back_populates="position")


class Employee(SoftDeleteMixin, Base):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("company_id", "employee_code", name="uq_employees_company_id_employee_code"),
        Index("ix_employees_company_id_national_id", "company_id", "national_id"),
        Index("ix_employees_user_id", "user_id"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, unique=True)
    employee_code: Mapped[str] = mapped_column(String(20), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True, index=True)
    position_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("positions.id"), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(10), nullable=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    first_name_en: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name_en: Mapped[str | None] = mapped_column(String(100), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    national_id: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    probation_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    employment_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'fulltime'"))
    base_salary: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    salary_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'monthly'"))
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_account: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sso_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sso_registered: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    pit_allowance_personal: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("60000"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    company: Mapped["Company"] = relationship("Company")
    branch: Mapped["Branch"] = relationship("Branch")
    user: Mapped["User | None"] = relationship("User")
    department: Mapped["Department | None"] = relationship("Department", back_populates="employees", foreign_keys=[department_id])
    position: Mapped["Position | None"] = relationship("Position", back_populates="employees")
    salaries: Mapped[list["EmployeeSalary"]] = relationship("EmployeeSalary", back_populates="employee", cascade="all, delete-orphan")
    payroll_items: Mapped[list["PayrollItem"]] = relationship("PayrollItem", back_populates="employee")
    attendance_records: Mapped[list["AttendanceRecord"]] = relationship("AttendanceRecord", back_populates="employee")
    leave_balances: Mapped[list["LeaveBalance"]] = relationship("LeaveBalance", back_populates="employee")
    leave_requests: Mapped[list["LeaveRequest"]] = relationship("LeaveRequest", back_populates="employee")

    @property
    def full_name(self) -> str:
        return " ".join(part for part in [self.title, self.first_name, self.last_name] if part)


class SalaryComponent(SoftDeleteMixin, Base):
    __tablename__ = "salary_components"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_salary_components_company_id_code"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    component_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_taxable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_sso_base: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_fixed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    company: Mapped["Company"] = relationship("Company")
    employee_salaries: Mapped[list["EmployeeSalary"]] = relationship("EmployeeSalary", back_populates="component")


class EmployeeSalary(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "employee_salaries"
    __table_args__ = (
        Index("ix_employee_salaries_employee_component_active", "employee_id", "component_id", unique=True, postgresql_where=text("effective_to IS NULL")),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    component_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("salary_components.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    employee: Mapped["Employee"] = relationship("Employee", back_populates="salaries")
    component: Mapped["SalaryComponent"] = relationship("SalaryComponent", back_populates="employee_salaries")
    company: Mapped["Company"] = relationship("Company")


class PayrollRun(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "payroll_runs"
    __table_args__ = (
        UniqueConstraint("company_id", "period_year", "period_month", name="uq_payroll_runs_company_period"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True, index=True)
    run_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    pay_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'draft'"))
    total_employees: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_gross: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    total_deductions: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    total_net: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    total_sso_employee: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    total_sso_employer: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    total_pit: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    processed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship("Company")
    branch: Mapped["Branch | None"] = relationship("Branch")
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    processor: Mapped["User | None"] = relationship("User", foreign_keys=[processed_by])
    items: Mapped[list["PayrollItem"]] = relationship("PayrollItem", back_populates="run", cascade="all, delete-orphan", order_by="PayrollItem.employee_code.asc()")


class PayrollItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "payroll_items"
    __table_args__ = (
        UniqueConstraint("run_id", "employee_id", name="uq_payroll_items_run_employee"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payroll_runs.id"), nullable=False, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    base_salary: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    earnings_total: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    sso_employee: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    sso_employer: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    pit_withheld: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    other_deductions: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    total_deductions: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    net_pay: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    ytd_gross: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    ytd_pit: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    employee_name: Mapped[str] = mapped_column(String(255), nullable=False)
    employee_code: Mapped[str] = mapped_column(String(20), nullable=False)
    position_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_account: Mapped[str | None] = mapped_column(String(30), nullable=True)

    run: Mapped["PayrollRun"] = relationship("PayrollRun", back_populates="items")
    employee: Mapped["Employee"] = relationship("Employee", back_populates="payroll_items")
    company: Mapped["Company"] = relationship("Company")
    lines: Mapped[list["PayrollItemLine"]] = relationship("PayrollItemLine", back_populates="payroll_item", cascade="all, delete-orphan", order_by="PayrollItemLine.component_name.asc()")


class PayrollItemLine(UUIDMixin, Base):
    __tablename__ = "payroll_item_lines"

    payroll_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payroll_items.id"), nullable=False, index=True)
    component_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("salary_components.id"), nullable=False)
    component_name: Mapped[str] = mapped_column(String(255), nullable=False)
    component_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    payroll_item: Mapped["PayrollItem"] = relationship("PayrollItem", back_populates="lines")
    component: Mapped["SalaryComponent"] = relationship("SalaryComponent")


class WorkSchedule(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "work_schedules"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    work_days: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)
    break_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("60"))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    company: Mapped["Company"] = relationship("Company")
    attendance_records: Mapped[list["AttendanceRecord"]] = relationship("AttendanceRecord", back_populates="schedule")


class PublicHoliday(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "public_holidays"
    __table_args__ = (
        UniqueConstraint("company_id", "holiday_date", name="uq_public_holidays_company_id_holiday_date"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    company: Mapped["Company"] = relationship("Company")


class AttendanceRecord(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", name="uq_attendance_records_employee_id_work_date"),
        Index("ix_attendance_records_company_work_date", "company_id", "work_date"),
        Index("ix_attendance_records_employee_work_date", "employee_id", "work_date"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False, index=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("work_schedules.id"), nullable=True)
    clock_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clock_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    work_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ot_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    ot_rate: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, server_default=text("1.5"))
    ot_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    is_absent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_late: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    late_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_holiday: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'manual'"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    employee: Mapped["Employee"] = relationship("Employee", back_populates="attendance_records")
    schedule: Mapped["WorkSchedule | None"] = relationship("WorkSchedule", back_populates="attendance_records")
    creator: Mapped["User | None"] = relationship("User", foreign_keys=[created_by])


class LeaveType(SoftDeleteMixin, Base):
    __tablename__ = "leave_types"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_leave_types_company_id_code"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    days_per_year: Mapped[int] = mapped_column(Integer, nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    carry_over: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    max_carry_over: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    requires_doc: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    gender_restrict: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    company: Mapped["Company"] = relationship("Company")
    balances: Mapped[list["LeaveBalance"]] = relationship("LeaveBalance", back_populates="leave_type")
    requests: Mapped[list["LeaveRequest"]] = relationship("LeaveRequest", back_populates="leave_type")


class LeaveBalance(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "leave_balances"
    __table_args__ = (
        UniqueConstraint("employee_id", "leave_type_id", "year", name="uq_leave_balances_employee_leave_type_year"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False, index=True)
    leave_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leave_types.id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    entitled_days: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)
    used_days: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False, server_default=text("0"))
    remaining_days: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)
    carry_over_days: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False, server_default=text("0"))

    company: Mapped["Company"] = relationship("Company")
    employee: Mapped["Employee"] = relationship("Employee", back_populates="leave_balances")
    leave_type: Mapped["LeaveType"] = relationship("LeaveType", back_populates="balances")


class LeaveRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "leave_requests"
    __table_args__ = (
        Index("ix_leave_requests_employee_start_date", "employee_id", "start_date"),
        Index("ix_leave_requests_status", "status"),
        Index("ix_leave_requests_company_request_number", "company_id", "request_number"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False, index=True)
    leave_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leave_types.id"), nullable=False, index=True)
    request_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    days_requested: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_attendance: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    company: Mapped["Company"] = relationship("Company")
    employee: Mapped["Employee"] = relationship("Employee", back_populates="leave_requests")
    leave_type: Mapped["LeaveType"] = relationship("LeaveType", back_populates="requests")
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    reviewer: Mapped["User | None"] = relationship("User", foreign_keys=[reviewed_by])
