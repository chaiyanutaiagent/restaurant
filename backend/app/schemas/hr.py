from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid

from app.schemas import BaseSchema


class DepartmentBase(BaseSchema):
    code: str
    name: str
    name_en: str | None = None
    parent_id: uuid.UUID | None = None
    is_active: bool = True


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseSchema):
    code: str | None = None
    name: str | None = None
    name_en: str | None = None
    parent_id: uuid.UUID | None = None
    is_active: bool | None = None


class DepartmentRead(DepartmentBase):
    id: uuid.UUID
    company_id: uuid.UUID


class PositionBase(BaseSchema):
    code: str
    name: str
    name_en: str | None = None
    department_id: uuid.UUID | None = None
    level: int = 1
    is_active: bool = True


class PositionCreate(PositionBase):
    pass


class PositionUpdate(BaseSchema):
    code: str | None = None
    name: str | None = None
    name_en: str | None = None
    department_id: uuid.UUID | None = None
    level: int | None = None
    is_active: bool | None = None


class PositionRead(PositionBase):
    id: uuid.UUID
    company_id: uuid.UUID


class EmployeeBase(BaseSchema):
    employee_code: str
    title: str | None = None
    first_name: str
    last_name: str
    first_name_en: str | None = None
    last_name_en: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    national_id: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    hire_date: date
    probation_end_date: date | None = None
    employment_type: str = "fulltime"
    base_salary: float = 0
    salary_type: str = "monthly"
    bank_name: str | None = None
    bank_account: str | None = None
    bank_account_name: str | None = None
    tax_id: str | None = None
    sso_number: str | None = None
    sso_registered: bool = True
    pit_allowance_personal: float = 60000
    is_active: bool = True


class EmployeeCreate(EmployeeBase):
    branch_id: uuid.UUID
    department_id: uuid.UUID | None = None
    position_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None


class EmployeeUpdate(BaseSchema):
    employee_code: str | None = None
    title: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    first_name_en: str | None = None
    last_name_en: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    national_id: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    hire_date: date | None = None
    probation_end_date: date | None = None
    termination_date: date | None = None
    employment_type: str | None = None
    base_salary: float | None = None
    salary_type: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    bank_account_name: str | None = None
    tax_id: str | None = None
    sso_number: str | None = None
    sso_registered: bool | None = None
    pit_allowance_personal: float | None = None
    is_active: bool | None = None
    branch_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    position_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None


class EmployeeRead(EmployeeBase):
    id: uuid.UUID
    company_id: uuid.UUID
    branch_id: uuid.UUID
    user_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    position_id: uuid.UUID | None = None
    department_name: str | None = None
    position_name: str | None = None
    branch_name: str | None = None
    created_at: datetime
    updated_at: datetime


class EmployeeListItem(BaseSchema):
    id: uuid.UUID
    employee_code: str
    title: str | None = None
    first_name: str
    last_name: str
    department_name: str | None = None
    position_name: str | None = None
    branch_name: str | None = None
    employment_type: str
    base_salary: float
    is_active: bool
    hire_date: date


class SalaryComponentRead(BaseSchema):
    id: uuid.UUID
    code: str
    name: str
    component_type: str
    is_taxable: bool
    is_sso_base: bool
    is_fixed: bool
    is_system: bool
    sort_order: int
    is_active: bool


class WorkScheduleBase(BaseSchema):
    name: str
    work_days: list[int]
    start_time: str
    end_time: str
    break_minutes: int = 60
    is_default: bool = False


class WorkScheduleCreate(WorkScheduleBase):
    pass


class WorkScheduleRead(WorkScheduleBase):
    id: uuid.UUID
    is_active: bool


class PublicHolidayBase(BaseSchema):
    holiday_date: date
    name: str
    name_en: str | None = None
    is_recurring: bool = True


class PublicHolidayCreate(PublicHolidayBase):
    pass


class PublicHolidayRead(PublicHolidayBase):
    id: uuid.UUID


class AttendanceRecordRead(BaseSchema):
    id: uuid.UUID
    employee_id: uuid.UUID
    work_date: date
    clock_in: datetime | None = None
    clock_out: datetime | None = None
    work_minutes: int | None = None
    ot_minutes: int
    ot_rate: Decimal
    ot_amount: Decimal
    is_absent: bool
    is_late: bool
    late_minutes: int
    is_holiday: bool
    note: str | None = None
    entry_type: str
    created_at: datetime
    employee_name: str
    employee_code: str


class RecordAttendanceRequest(BaseSchema):
    employee_id: uuid.UUID
    work_date: date
    clock_in: datetime | None = None
    clock_out: datetime | None = None
    note: str | None = None


class ClockInRequest(BaseSchema):
    employee_id: uuid.UUID
    timestamp: datetime | None = None


class ClockOutRequest(BaseSchema):
    employee_id: uuid.UUID
    timestamp: datetime | None = None


class AttendanceSummary(BaseSchema):
    employee_id: str
    employee_name: str
    employee_code: str
    period_year: int
    period_month: int
    total_days: int
    present_days: int
    absent_days: int
    late_days: int
    total_late_minutes: int
    ot_days: int
    total_ot_minutes: int
    total_ot_amount: Decimal


class LeaveTypeBase(BaseSchema):
    code: str
    name: str
    name_en: str | None = None
    days_per_year: int
    is_paid: bool = True
    carry_over: bool = False
    max_carry_over: int = 0
    requires_doc: bool = False
    gender_restrict: str | None = None
    is_active: bool = True


class LeaveTypeCreate(LeaveTypeBase):
    is_system: bool = False


class LeaveTypeRead(LeaveTypeBase):
    id: uuid.UUID
    is_system: bool


class LeaveBalanceRead(BaseSchema):
    id: uuid.UUID
    employee_id: uuid.UUID
    leave_type_id: uuid.UUID
    year: int
    entitled_days: Decimal
    used_days: Decimal
    remaining_days: Decimal
    carry_over_days: Decimal
    leave_type_name: str


class CreateLeaveRequestRequest(BaseSchema):
    employee_id: uuid.UUID
    leave_type_id: uuid.UUID
    start_date: date
    end_date: date
    reason: str | None = None


class LeaveRequestRead(BaseSchema):
    id: uuid.UUID
    request_number: str
    employee_id: uuid.UUID
    leave_type_id: uuid.UUID
    status: str
    start_date: date
    end_date: date
    days_requested: Decimal
    reason: str | None = None
    document_url: str | None = None
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    created_at: datetime
    employee_name: str
    leave_type_name: str


class ReviewLeaveRequest(BaseSchema):
    action: str
    review_note: str | None = None


class InitializeLeaveBalancesRequest(BaseSchema):
    year: int


class CreatePayrollRunRequest(BaseSchema):
    period_year: int
    period_month: int
    pay_date: date
    branch_id: uuid.UUID | None = None
    note: str | None = None


class PayrollItemLineRead(BaseSchema):
    component_name: str
    component_type: str
    amount: float
    note: str | None = None


class PayrollItemRead(BaseSchema):
    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    employee_code: str
    position_name: str | None = None
    department_name: str | None = None
    bank_account: str | None = None
    base_salary: float
    earnings_total: float
    sso_employee: float
    sso_employer: float
    pit_withheld: float
    other_deductions: float
    total_deductions: float
    net_pay: float
    ytd_gross: float
    ytd_pit: float
    lines: list[PayrollItemLineRead]


class PayrollRunRead(BaseSchema):
    id: uuid.UUID
    run_number: str
    period_year: int
    period_month: int
    pay_date: date
    status: str
    branch_id: uuid.UUID | None = None
    total_employees: int
    total_gross: float
    total_deductions: float
    total_net: float
    total_sso_employee: float
    total_sso_employer: float
    total_pit: float
    note: str | None = None
    created_by: uuid.UUID
    processed_by: uuid.UUID | None = None
    processed_at: datetime | None = None
    created_at: datetime


class PayrollRunDetailRead(PayrollRunRead):
    items: list[PayrollItemRead]


class TerminateEmployeeRequest(BaseSchema):
    termination_date: date
