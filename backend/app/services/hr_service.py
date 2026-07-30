from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import uuid

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.accounting import JournalEntry
from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.company import Company
from app.models.hr import (
    AttendanceRecord,
    Department,
    Employee,
    EmployeeSalary,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    PayrollItem,
    PayrollItemLine,
    PayrollRun,
    Position,
    PublicHoliday,
    SalaryComponent,
    WorkSchedule,
)
from app.models.user import User
from app.schemas.hr import (
    AttendanceSummary,
    ClockInRequest,
    ClockOutRequest,
    CreateLeaveRequestRequest,
    CreatePayrollRunRequest,
    DepartmentCreate,
    DepartmentUpdate,
    EmployeeCreate,
    EmployeeUpdate,
    LeaveTypeCreate,
    PositionCreate,
    PositionUpdate,
    PublicHolidayCreate,
    RecordAttendanceRequest,
    ReviewLeaveRequest,
    WorkScheduleCreate,
)
from app.services.accounting_service import AccountingService
from app.services.notification_service import NotificationService
from app.utils.attendance_calculator import calc_hourly_rate, calc_ot, count_leave_days, is_late, is_working_day
from app.utils.payroll_calculator import calculate_payroll_item
from app.utils.posting_rules import PostingLine

TWOPLACES = Decimal("0.01")
ONEPLACE = Decimal("0.1")


def q2(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def q1(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(value or 0).quantize(ONEPLACE, rounding=ROUND_HALF_UP)


class HRService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_departments(self, company_id: uuid.UUID) -> list[Department]:
        rows = (
            await self.db.scalars(
                select(Department)
                .where(Department.company_id == company_id, Department.deleted_at.is_(None))
                .order_by(Department.code.asc())
            )
        ).all()
        return rows

    async def create_department(self, company_id: uuid.UUID, data: DepartmentCreate) -> Department:
        await self._ensure_department_code_available(company_id, data.code)
        if data.parent_id is not None:
            await self._get_department(data.parent_id, company_id)
        row = Department(company_id=company_id, **data.model_dump())
        self.db.add(row)
        await self.db.commit()
        return await self._get_department(row.id, company_id)

    async def update_department(self, dept_id: uuid.UUID, company_id: uuid.UUID, data: DepartmentUpdate) -> Department:
        row = await self._get_department(dept_id, company_id)
        payload = data.model_dump(exclude_unset=True)
        if "code" in payload and payload["code"] != row.code:
            await self._ensure_department_code_available(company_id, payload["code"], exclude_id=row.id)
        if "parent_id" in payload and payload["parent_id"] is not None:
            if payload["parent_id"] == row.id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department cannot be its own parent")
            await self._get_department(payload["parent_id"], company_id)
        for field, value in payload.items():
            setattr(row, field, value)
        await self.db.commit()
        return await self._get_department(row.id, company_id)

    async def list_positions(self, company_id: uuid.UUID, department_id: uuid.UUID | None = None) -> list[Position]:
        filters = [Position.company_id == company_id, Position.deleted_at.is_(None)]
        if department_id is not None:
            filters.append(Position.department_id == department_id)
        rows = (await self.db.scalars(select(Position).where(*filters).order_by(Position.code.asc()))).all()
        return rows

    async def create_position(self, company_id: uuid.UUID, data: PositionCreate) -> Position:
        await self._ensure_position_code_available(company_id, data.code)
        if data.department_id is not None:
            await self._get_department(data.department_id, company_id)
        row = Position(company_id=company_id, **data.model_dump())
        self.db.add(row)
        await self.db.commit()
        return await self._get_position(row.id, company_id)

    async def update_position(self, pos_id: uuid.UUID, company_id: uuid.UUID, data: PositionUpdate) -> Position:
        row = await self._get_position(pos_id, company_id)
        payload = data.model_dump(exclude_unset=True)
        if "code" in payload and payload["code"] != row.code:
            await self._ensure_position_code_available(company_id, payload["code"], exclude_id=row.id)
        if "department_id" in payload and payload["department_id"] is not None:
            await self._get_department(payload["department_id"], company_id)
        for field, value in payload.items():
            setattr(row, field, value)
        await self.db.commit()
        return await self._get_position(row.id, company_id)

    async def list_employees(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None = None,
        department_id: uuid.UUID | None = None,
        is_active: bool | None = None,
        search: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Employee], int]:
        filters = [Employee.company_id == company_id, Employee.deleted_at.is_(None)]
        if branch_id is not None:
            filters.append(Employee.branch_id == branch_id)
        if department_id is not None:
            filters.append(Employee.department_id == department_id)
        if is_active is not None:
            filters.append(Employee.is_active.is_(is_active))
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    Employee.employee_code.ilike(pattern),
                    Employee.first_name.ilike(pattern),
                    Employee.last_name.ilike(pattern),
                    func.concat(Employee.first_name, " ", Employee.last_name).ilike(pattern),
                )
            )
        total = int((await self.db.scalar(select(func.count(Employee.id)).where(*filters))) or 0)
        rows = (
            await self.db.scalars(
                select(Employee)
                .where(*filters)
                .options(
                    selectinload(Employee.branch),
                    selectinload(Employee.department),
                    selectinload(Employee.position),
                )
                .order_by(Employee.created_at.desc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        ).all()
        for employee in rows:
            self._hydrate_employee(employee)
        return rows, total

    async def get_employee(self, employee_id: uuid.UUID, company_id: uuid.UUID) -> Employee:
        row = await self.db.scalar(
            select(Employee)
            .where(Employee.id == employee_id, Employee.company_id == company_id, Employee.deleted_at.is_(None))
            .options(
                selectinload(Employee.branch),
                selectinload(Employee.department),
                selectinload(Employee.position),
                selectinload(Employee.salaries).selectinload(EmployeeSalary.component),
            )
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
        self._hydrate_employee(row)
        return row

    async def create_employee(self, company_id: uuid.UUID, user_id_actor: uuid.UUID, data: EmployeeCreate) -> Employee:
        await self._ensure_employee_code_available(company_id, data.employee_code)
        await self._get_branch(company_id, data.branch_id)
        if data.department_id is not None:
            await self._get_department(data.department_id, company_id)
        if data.position_id is not None:
            await self._get_position(data.position_id, company_id)
        linked_user = None
        if data.user_id is not None:
            linked_user = await self._get_user(company_id, data.user_id)
            in_use = await self.db.scalar(
                select(Employee.id).where(Employee.user_id == data.user_id, Employee.deleted_at.is_(None))
            )
            if in_use is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already linked to another employee")

        row = Employee(company_id=company_id, **data.model_dump())
        self.db.add(row)
        await self.db.flush()
        if linked_user is not None:
            linked_user.employee_code = row.employee_code
        self._audit(company_id, user_id_actor, "hr.employee.create", "Employee", row.id)
        await self.db.commit()
        return await self.get_employee(row.id, company_id)

    async def update_employee(self, employee_id: uuid.UUID, company_id: uuid.UUID, data: EmployeeUpdate) -> Employee:
        row = await self.get_employee(employee_id, company_id)
        payload = data.model_dump(exclude_unset=True)
        if "employee_code" in payload and payload["employee_code"] != row.employee_code:
            await self._ensure_employee_code_available(company_id, payload["employee_code"], exclude_id=row.id)
        if "branch_id" in payload and payload["branch_id"] is not None:
            await self._get_branch(company_id, payload["branch_id"])
        if "department_id" in payload and payload["department_id"] is not None:
            await self._get_department(payload["department_id"], company_id)
        if "position_id" in payload and payload["position_id"] is not None:
            await self._get_position(payload["position_id"], company_id)
        if "user_id" in payload and payload["user_id"] is not None:
            await self._get_user(company_id, payload["user_id"])
            linked = await self.db.scalar(
                select(Employee.id).where(
                    Employee.user_id == payload["user_id"],
                    Employee.id != row.id,
                    Employee.deleted_at.is_(None),
                )
            )
            if linked is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already linked to another employee")
        for field, value in payload.items():
            setattr(row, field, value)
        if row.user_id is not None:
            linked_user = await self._get_user(company_id, row.user_id)
            linked_user.employee_code = row.employee_code
        self._audit(company_id, None, "hr.employee.update", "Employee", row.id)
        await self.db.commit()
        return await self.get_employee(row.id, company_id)

    async def terminate_employee(
        self,
        employee_id: uuid.UUID,
        company_id: uuid.UUID,
        termination_date: date,
        user_id: uuid.UUID,
    ) -> Employee:
        row = await self.get_employee(employee_id, company_id)
        row.termination_date = termination_date
        row.is_active = False
        self._audit(company_id, user_id, "hr.employee.terminate", "Employee", row.id)
        await self.db.commit()
        return await self.get_employee(row.id, company_id)

    async def list_components(self, company_id: uuid.UUID) -> list[SalaryComponent]:
        rows = (
            await self.db.scalars(
                select(SalaryComponent)
                .where(SalaryComponent.company_id == company_id, SalaryComponent.deleted_at.is_(None))
                .order_by(SalaryComponent.sort_order.asc(), SalaryComponent.code.asc())
            )
        ).all()
        return rows

    async def create_payroll_run(self, company_id: uuid.UUID, user_id: uuid.UUID, data: CreatePayrollRunRequest) -> PayrollRun:
        existing = await self.db.scalar(
            select(PayrollRun.id).where(
                PayrollRun.company_id == company_id,
                PayrollRun.period_year == data.period_year,
                PayrollRun.period_month == data.period_month,
            )
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payroll run already exists for this period")
        if data.branch_id is not None:
            await self._get_branch(company_id, data.branch_id)
        run = PayrollRun(
            company_id=company_id,
            branch_id=data.branch_id,
            run_number=f"PAY-RUN-{data.period_year}-{data.period_month:02d}",
            period_year=data.period_year,
            period_month=data.period_month,
            pay_date=data.pay_date,
            status="draft",
            note=data.note,
            created_by=user_id,
        )
        self.db.add(run)
        await self.db.flush()
        self._audit(company_id, user_id, "hr.payroll.create", "PayrollRun", run.id)
        await self.db.commit()
        return await self.get_payroll_run(run.id, company_id)

    async def process_payroll(self, run_id: uuid.UUID, company_id: uuid.UUID, user_id: uuid.UUID) -> PayrollRun:
        run = await self._get_payroll_run_for_update(run_id, company_id)
        if run.status != "draft":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payroll run is not in draft status")

        employees = await self._load_payroll_employees(company_id, run.branch_id, run.pay_date)
        components = await self.list_components(company_id)
        component_map = {component.code: component for component in components}
        run.status = "processing"
        await self.db.flush()

        total_gross = Decimal("0")
        total_deductions = Decimal("0")
        total_net = Decimal("0")
        total_sso_employee = Decimal("0")
        total_sso_employer = Decimal("0")
        total_pit = Decimal("0")

        for employee in employees:
            fixed_rows = [
                salary
                for salary in employee.salaries
                if salary.effective_from <= run.pay_date and (salary.effective_to is None or salary.effective_to >= run.pay_date)
            ]
            variable_earnings: dict[str, Decimal] = {}
            variable_deductions: dict[str, Decimal] = {}
            for salary in fixed_rows:
                code = salary.component.code
                if code == "BASE":
                    continue
                if salary.component.component_type == "earning":
                    variable_earnings[code] = q2(salary.amount)
                else:
                    variable_deductions[code] = q2(salary.amount)

            ot_amount = await self.get_ot_for_payroll(company_id, run.period_year, run.period_month, employee.id)
            if ot_amount > 0:
                variable_earnings["OT"] = q2(variable_earnings.get("OT", Decimal("0")) + ot_amount)

            ytd_taxable, ytd_pit_paid = await self._get_employee_ytd(employee.id, company_id, run.period_year, run.period_month)
            calc = calculate_payroll_item(
                employee_id=employee.id,
                base_salary=q2(employee.base_salary),
                variable_earnings=variable_earnings,
                variable_deductions=variable_deductions,
                components=components,
                month=run.period_month,
                ytd_taxable=ytd_taxable,
                ytd_pit_paid=ytd_pit_paid,
                personal_allowance=q2(employee.pit_allowance_personal),
            )

            earnings_total = q2(sum(calc.earnings.values(), Decimal("0")))
            other_deduction_total = q2(sum(calc.other_deductions.values(), Decimal("0")))
            item = PayrollItem(
                run_id=run.id,
                employee_id=employee.id,
                company_id=company_id,
                base_salary=calc.base_salary,
                earnings_total=earnings_total,
                sso_employee=calc.sso_employee,
                sso_employer=calc.sso_employer,
                pit_withheld=calc.pit_withheld,
                other_deductions=other_deduction_total,
                total_deductions=calc.total_deductions,
                net_pay=calc.net_pay,
                ytd_gross=q2(ytd_taxable + calc.gross_taxable),
                ytd_pit=q2(ytd_pit_paid + calc.pit_withheld),
                employee_name=employee.full_name,
                employee_code=employee.employee_code,
                position_name=employee.position.name if employee.position else None,
                department_name=employee.department.name if employee.department else None,
                bank_account=employee.bank_account,
            )
            self.db.add(item)
            await self.db.flush()

            self.db.add(
                PayrollItemLine(
                    payroll_item_id=item.id,
                    component_id=component_map["BASE"].id,
                    component_name=component_map["BASE"].name,
                    component_type="earning",
                    amount=calc.base_salary,
                )
            )
            for code, amount in sorted(variable_earnings.items()):
                component = component_map.get(code)
                if component is None:
                    continue
                self.db.add(
                    PayrollItemLine(
                        payroll_item_id=item.id,
                        component_id=component.id,
                        component_name=component.name,
                        component_type="earning",
                        amount=q2(amount),
                    )
                )
            if calc.sso_employee > 0 and "SSO_EE" in component_map:
                self.db.add(
                    PayrollItemLine(
                        payroll_item_id=item.id,
                        component_id=component_map["SSO_EE"].id,
                        component_name=component_map["SSO_EE"].name,
                        component_type="deduction",
                        amount=calc.sso_employee,
                    )
                )
            if calc.pit_withheld > 0 and "PIT" in component_map:
                self.db.add(
                    PayrollItemLine(
                        payroll_item_id=item.id,
                        component_id=component_map["PIT"].id,
                        component_name=component_map["PIT"].name,
                        component_type="deduction",
                        amount=calc.pit_withheld,
                    )
                )
            for code, amount in sorted(calc.other_deductions.items()):
                component = component_map.get(code)
                if component is None:
                    continue
                self.db.add(
                    PayrollItemLine(
                        payroll_item_id=item.id,
                        component_id=component.id,
                        component_name=component.name,
                        component_type="deduction",
                        amount=q2(amount),
                    )
                )

            total_gross += earnings_total
            total_deductions += calc.total_deductions
            total_net += calc.net_pay
            total_sso_employee += calc.sso_employee
            total_sso_employer += calc.sso_employer
            total_pit += calc.pit_withheld

        run.total_employees = len(employees)
        run.total_gross = q2(total_gross)
        run.total_deductions = q2(total_deductions)
        run.total_net = q2(total_net)
        run.total_sso_employee = q2(total_sso_employee)
        run.total_sso_employer = q2(total_sso_employer)
        run.total_pit = q2(total_pit)
        run.status = "completed"
        run.processed_by = user_id
        run.processed_at = datetime.now(timezone.utc)

        accounting = AccountingService(self.db)
        await accounting._post_entry(
            company_id=company_id,
            branch_id=run.branch_id,
            user_id=user_id,
            entry_date=run.pay_date,
            entry_type="manual",
            description=f"Payroll run {run.run_number}",
            lines=[
                PostingLine(account_code="6001", debit_amount=q2(total_gross + total_sso_employer), credit_amount=Decimal("0.00"), description="ค่าใช้จ่ายเงินเดือน"),
                PostingLine(account_code="2104", debit_amount=Decimal("0.00"), credit_amount=q2(total_net), description="เงินเดือนค้างจ่าย"),
                PostingLine(account_code="2103", debit_amount=Decimal("0.00"), credit_amount=q2(total_pit), description="ภาษีหัก ณ ที่จ่ายค้างจ่าย"),
                PostingLine(account_code="2104", debit_amount=Decimal("0.00"), credit_amount=q2(total_sso_employee + total_sso_employer), description="ประกันสังคมค้างจ่าย"),
            ],
            reference_type="PayrollRun",
            reference_id=str(run.id),
        )
        self._audit(company_id, user_id, "hr.payroll.process", "PayrollRun", run.id)
        try:
            notif_svc = NotificationService(self.db)
            thai_months = ["", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
            period = f"{thai_months[run.period_month]} {run.period_year + 543}"
            await notif_svc.notify_event(
                company_id,
                "payroll.processed",
                context={
                    "period": period,
                    "total_employees": str(run.total_employees),
                    "total_net": f"{run.total_net:,.2f}",
                },
                reference_type="PayrollRun",
                reference_id=str(run.id),
            )
        except Exception:
            pass
        await self.db.commit()
        return await self.get_payroll_run(run.id, company_id)

    async def cancel_payroll(self, run_id: uuid.UUID, company_id: uuid.UUID, user_id: uuid.UUID) -> PayrollRun:
        run = await self._get_payroll_run_for_update(run_id, company_id)
        if run.status not in {"draft", "completed"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payroll run cannot be cancelled")
        if run.status == "completed" and run.pay_date < date.today():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Completed payroll can only be cancelled before pay date")

        if run.status == "completed":
            entry = await self.db.scalar(
                select(JournalEntry)
                .where(
                    JournalEntry.company_id == company_id,
                    JournalEntry.reference_type == "PayrollRun",
                    JournalEntry.reference_id == str(run.id),
                )
                .options(selectinload(JournalEntry.lines).selectinload(JournalEntry.account))
            )
            if entry is not None and not entry.is_reversed:
                await AccountingService(self.db).reverse_entry(entry.id, company_id, user_id)

        for item in list(run.items):
            await self.db.delete(item)

        run.status = "cancelled"
        run.total_employees = 0
        run.total_gross = Decimal("0")
        run.total_deductions = Decimal("0")
        run.total_net = Decimal("0")
        run.total_sso_employee = Decimal("0")
        run.total_sso_employer = Decimal("0")
        run.total_pit = Decimal("0")
        self._audit(company_id, user_id, "hr.payroll.cancel", "PayrollRun", run.id)
        await self.db.commit()
        return await self.get_payroll_run(run.id, company_id)

    async def list_payroll_runs(self, company_id: uuid.UUID, page: int = 1, limit: int = 20) -> tuple[list[PayrollRun], int]:
        total = int((await self.db.scalar(select(func.count(PayrollRun.id)).where(PayrollRun.company_id == company_id))) or 0)
        rows = (
            await self.db.scalars(
                select(PayrollRun)
                .where(PayrollRun.company_id == company_id)
                .order_by(PayrollRun.period_year.desc(), PayrollRun.period_month.desc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        ).all()
        return rows, total

    async def get_payroll_run(self, run_id: uuid.UUID, company_id: uuid.UUID) -> PayrollRun:
        row = await self.db.scalar(
            select(PayrollRun)
            .where(PayrollRun.id == run_id, PayrollRun.company_id == company_id)
            .options(selectinload(PayrollRun.items).selectinload(PayrollItem.lines))
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll run not found")
        return row

    async def get_employee_payslip(self, run_id: uuid.UUID, employee_id: uuid.UUID, company_id: uuid.UUID) -> PayrollItem:
        item = await self.db.scalar(
            select(PayrollItem)
            .join(PayrollRun, PayrollRun.id == PayrollItem.run_id)
            .where(
                PayrollItem.run_id == run_id,
                PayrollItem.employee_id == employee_id,
                PayrollItem.company_id == company_id,
                PayrollRun.company_id == company_id,
            )
            .options(selectinload(PayrollItem.lines))
        )
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payslip not found")
        return item

    async def get_company(self, company_id: uuid.UUID) -> Company:
        row = await self.db.get(Company, company_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        return row

    async def list_schedules(self, company_id: uuid.UUID) -> list[WorkSchedule]:
        rows = (
            await self.db.scalars(
                select(WorkSchedule)
                .where(WorkSchedule.company_id == company_id)
                .order_by(WorkSchedule.is_default.desc(), WorkSchedule.name.asc())
            )
        ).all()
        return rows

    async def create_schedule(self, company_id: uuid.UUID, data: WorkScheduleCreate) -> WorkSchedule:
        if data.is_default:
            await self._clear_default_schedule(company_id)
        row = WorkSchedule(company_id=company_id, **data.model_dump(), is_active=True)
        self.db.add(row)
        await self.db.commit()
        return row

    async def list_holidays(self, company_id: uuid.UUID, year: int | None = None) -> list[PublicHoliday]:
        target_year = year or date.today().year
        rows = (
            await self.db.scalars(
                select(PublicHoliday)
                .where(PublicHoliday.company_id == company_id)
                .order_by(PublicHoliday.holiday_date.asc(), PublicHoliday.name.asc())
            )
        ).all()
        result: list[PublicHoliday] = []
        for row in rows:
            holiday_year = row.holiday_date.year
            if holiday_year == target_year:
                result.append(row)
                continue
            if row.is_recurring:
                clone = PublicHoliday(
                    id=row.id,
                    company_id=row.company_id,
                    holiday_date=date(target_year, row.holiday_date.month, row.holiday_date.day),
                    name=row.name,
                    name_en=row.name_en,
                    is_recurring=row.is_recurring,
                )
                result.append(clone)
        result.sort(key=lambda item: item.holiday_date)
        return result

    async def create_holiday(self, company_id: uuid.UUID, data: PublicHolidayCreate) -> PublicHoliday:
        exists = await self.db.scalar(
            select(PublicHoliday.id).where(
                PublicHoliday.company_id == company_id,
                PublicHoliday.holiday_date == data.holiday_date,
            )
        )
        if exists is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Holiday already exists")
        row = PublicHoliday(company_id=company_id, **data.model_dump())
        self.db.add(row)
        await self.db.commit()
        return row

    async def delete_holiday(self, holiday_id: uuid.UUID, company_id: uuid.UUID) -> None:
        row = await self.db.scalar(
            select(PublicHoliday).where(PublicHoliday.id == holiday_id, PublicHoliday.company_id == company_id)
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holiday not found")
        await self.db.delete(row)
        await self.db.commit()

    async def clock_in(self, company_id: uuid.UUID, user_id: uuid.UUID, data: ClockInRequest) -> AttendanceRecord:
        employee = await self.get_employee(data.employee_id, company_id)
        timestamp = data.timestamp or datetime.now(timezone.utc)
        record = await self._get_or_create_attendance_record(company_id, employee.id, timestamp.date(), user_id)
        record.clock_in = timestamp
        record.entry_type = "system"
        record.is_absent = False
        schedule = await self._get_employee_schedule(company_id, employee)
        if schedule is not None:
            late_flag, late_minutes = is_late(timestamp, schedule.start_time)
            record.is_late = late_flag
            record.late_minutes = late_minutes
            record.schedule_id = schedule.id
        await self.db.commit()
        return await self._get_attendance_record(record.id, company_id)

    async def clock_out(self, company_id: uuid.UUID, user_id: uuid.UUID, data: ClockOutRequest) -> AttendanceRecord:
        employee = await self.get_employee(data.employee_id, company_id)
        timestamp = data.timestamp or datetime.now(timezone.utc)
        record = await self.db.scalar(
            select(AttendanceRecord)
            .where(
                AttendanceRecord.company_id == company_id,
                AttendanceRecord.employee_id == employee.id,
                AttendanceRecord.work_date == timestamp.date(),
            )
            .options(selectinload(AttendanceRecord.employee), selectinload(AttendanceRecord.schedule))
        )
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance record not found for today")
        record.clock_out = timestamp
        record.created_by = user_id
        record.entry_type = "system"
        schedule = await self._get_employee_schedule(company_id, employee)
        holiday_dates = await self._get_holiday_dates(company_id, record.work_date.year)
        await self._apply_attendance_metrics(record, employee, schedule, holiday_dates)
        await self.db.commit()
        return await self._get_attendance_record(record.id, company_id)

    async def record_attendance(self, company_id: uuid.UUID, user_id: uuid.UUID, data: RecordAttendanceRequest) -> AttendanceRecord:
        employee = await self.get_employee(data.employee_id, company_id)
        record = await self._get_or_create_attendance_record(company_id, employee.id, data.work_date, user_id)
        record.clock_in = data.clock_in
        record.clock_out = data.clock_out
        record.note = data.note
        record.entry_type = "manual"
        record.created_by = user_id
        record.is_absent = False
        schedule = await self._get_employee_schedule(company_id, employee)
        holiday_dates = await self._get_holiday_dates(company_id, data.work_date.year)
        if data.clock_in and data.clock_out:
            await self._apply_attendance_metrics(record, employee, schedule, holiday_dates)
        else:
            record.work_minutes = None
            record.ot_minutes = 0
            record.ot_rate = Decimal("1.5")
            record.ot_amount = Decimal("0")
            record.is_late = False
            record.late_minutes = 0
            record.is_holiday = data.work_date in holiday_dates
        await self.db.commit()
        return await self._get_attendance_record(record.id, company_id)

    async def list_attendance(
        self,
        company_id: uuid.UUID,
        employee_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> tuple[list[AttendanceRecord], int]:
        filters = [AttendanceRecord.company_id == company_id]
        if employee_id is not None:
            filters.append(AttendanceRecord.employee_id == employee_id)
        if date_from is not None:
            filters.append(AttendanceRecord.work_date >= date_from)
        if date_to is not None:
            filters.append(AttendanceRecord.work_date <= date_to)
        total = int((await self.db.scalar(select(func.count(AttendanceRecord.id)).where(*filters))) or 0)
        rows = (
            await self.db.scalars(
                select(AttendanceRecord)
                .where(*filters)
                .options(selectinload(AttendanceRecord.employee))
                .order_by(AttendanceRecord.work_date.desc(), AttendanceRecord.created_at.desc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        ).all()
        for row in rows:
            self._hydrate_attendance(row)
        return rows, total

    async def get_attendance_summary(
        self,
        company_id: uuid.UUID,
        period_year: int,
        period_month: int,
        branch_id: uuid.UUID | None = None,
        department_id: uuid.UUID | None = None,
    ) -> list[AttendanceSummary]:
        first_day = date(period_year, period_month, 1)
        last_day = date(period_year, period_month, monthrange(period_year, period_month)[1])
        holiday_dates = await self._get_holiday_dates(company_id, period_year)
        employees = await self._load_active_employees(company_id, branch_id, department_id, last_day)
        records = (
            await self.db.scalars(
                select(AttendanceRecord)
                .where(
                    AttendanceRecord.company_id == company_id,
                    AttendanceRecord.work_date >= first_day,
                    AttendanceRecord.work_date <= last_day,
                )
                .options(selectinload(AttendanceRecord.employee))
            )
        ).all()
        record_map: dict[uuid.UUID, list[AttendanceRecord]] = {}
        for record in records:
            record_map.setdefault(record.employee_id, []).append(record)

        summaries: list[AttendanceSummary] = []
        for employee in employees:
            schedule = await self._get_employee_schedule(company_id, employee)
            work_days = schedule.work_days if schedule is not None else [1, 2, 3, 4, 5]
            employment_start = max(employee.hire_date, first_day)
            employment_end = min(employee.termination_date or last_day, last_day)
            total_days = 0
            if employment_start <= employment_end:
                total_days = int(count_leave_days(employment_start, employment_end, work_days, holiday_dates))
            employee_records = record_map.get(employee.id, [])
            present_days = sum(1 for row in employee_records if not row.is_absent)
            absent_days = sum(1 for row in employee_records if row.is_absent)
            late_days = sum(1 for row in employee_records if row.is_late)
            total_late_minutes = sum(row.late_minutes or 0 for row in employee_records)
            ot_rows = [row for row in employee_records if (row.ot_minutes or 0) > 0]
            summaries.append(
                AttendanceSummary(
                    employee_id=str(employee.id),
                    employee_name=employee.full_name,
                    employee_code=employee.employee_code,
                    period_year=period_year,
                    period_month=period_month,
                    total_days=total_days,
                    present_days=present_days,
                    absent_days=absent_days,
                    late_days=late_days,
                    total_late_minutes=total_late_minutes,
                    ot_days=len(ot_rows),
                    total_ot_minutes=sum(row.ot_minutes or 0 for row in ot_rows),
                    total_ot_amount=q2(sum((row.ot_amount or Decimal("0")) for row in ot_rows)),
                )
            )
        summaries.sort(key=lambda item: item.employee_code)
        return summaries

    async def list_leave_types(self, company_id: uuid.UUID) -> list[LeaveType]:
        rows = (
            await self.db.scalars(
                select(LeaveType)
                .where(LeaveType.company_id == company_id, LeaveType.deleted_at.is_(None))
                .order_by(LeaveType.is_system.desc(), LeaveType.code.asc())
            )
        ).all()
        return rows

    async def create_leave_type(self, company_id: uuid.UUID, data: LeaveTypeCreate) -> LeaveType:
        exists = await self.db.scalar(
            select(LeaveType.id).where(
                LeaveType.company_id == company_id,
                LeaveType.code == data.code,
                LeaveType.deleted_at.is_(None),
            )
        )
        if exists is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Leave type code already exists")
        row = LeaveType(company_id=company_id, **data.model_dump())
        self.db.add(row)
        await self.db.commit()
        return row

    async def get_employee_leave_balances(self, employee_id: uuid.UUID, company_id: uuid.UUID, year: int) -> list[LeaveBalance]:
        employee = await self.get_employee(employee_id, company_id)
        leave_types = await self.list_leave_types(company_id)
        created = False
        for leave_type in leave_types:
            if not leave_type.is_active:
                continue
            balance = await self._ensure_leave_balance(company_id, employee, leave_type, year)
            self._hydrate_leave_balance(balance)
            created = created or balance in self.db.new
        if created:
            await self.db.commit()
        rows = (
            await self.db.scalars(
                select(LeaveBalance)
                .where(
                    LeaveBalance.company_id == company_id,
                    LeaveBalance.employee_id == employee_id,
                    LeaveBalance.year == year,
                )
                .options(selectinload(LeaveBalance.leave_type))
                .order_by(LeaveBalance.created_at.asc())
            )
        ).all()
        for row in rows:
            self._hydrate_leave_balance(row)
        return rows

    async def initialize_leave_balances(self, company_id: uuid.UUID, year: int) -> int:
        employees = await self._load_active_employees(company_id, None, None, date(year, 12, 31))
        leave_types = [row for row in await self.list_leave_types(company_id) if row.is_active]
        created = 0
        for employee in employees:
            for leave_type in leave_types:
                existing = await self.db.scalar(
                    select(LeaveBalance.id).where(
                        LeaveBalance.company_id == company_id,
                        LeaveBalance.employee_id == employee.id,
                        LeaveBalance.leave_type_id == leave_type.id,
                        LeaveBalance.year == year,
                    )
                )
                if existing is not None:
                    continue
                balance = await self._ensure_leave_balance(company_id, employee, leave_type, year)
                if balance in self.db.new:
                    created += 1
        await self.db.commit()
        return created

    async def create_leave_request(self, company_id: uuid.UUID, user_id: uuid.UUID, data: CreateLeaveRequestRequest) -> LeaveRequest:
        if data.end_date < data.start_date:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="End date must be on or after start date")
        employee = await self.get_employee(data.employee_id, company_id)
        leave_type = await self._get_leave_type(data.leave_type_id, company_id)
        if leave_type.gender_restrict and leave_type.gender_restrict != employee.gender:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Leave type is restricted by gender")
        schedule = await self._get_employee_schedule(company_id, employee)
        work_days = schedule.work_days if schedule is not None else [1, 2, 3, 4, 5]
        holiday_dates = await self._get_holiday_dates(company_id, data.start_date.year)
        days_requested = count_leave_days(data.start_date, data.end_date, work_days, holiday_dates)
        balance = await self._ensure_leave_balance(company_id, employee, leave_type, data.start_date.year)
        if balance.remaining_days < days_requested:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient leave balance")
        request_number = await self._generate_leave_request_number(company_id)
        row = LeaveRequest(
            company_id=company_id,
            employee_id=employee.id,
            leave_type_id=leave_type.id,
            request_number=request_number,
            status="pending",
            start_date=data.start_date,
            end_date=data.end_date,
            days_requested=q1(days_requested),
            reason=data.reason,
            created_by=user_id,
            auto_attendance=True,
        )
        self.db.add(row)
        await self.db.flush()
        self._audit(company_id, user_id, "hr.leave.request_created", "LeaveRequest", row.id)
        await self.db.commit()
        return await self.get_leave_request(row.id, company_id)

    async def review_leave_request(
        self,
        request_id: uuid.UUID,
        company_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        data: ReviewLeaveRequest,
    ) -> LeaveRequest:
        row = await self._get_leave_request_for_update(request_id, company_id)
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Leave request is not pending")
        if data.action not in {"approve", "reject"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid review action")

        if data.action == "approve":
            balance = await self._ensure_leave_balance(company_id, row.employee, row.leave_type, row.start_date.year)
            if balance.remaining_days < row.days_requested:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient leave balance")
            balance.used_days = q1(balance.used_days + row.days_requested)
            balance.remaining_days = q1(balance.remaining_days - row.days_requested)
            if row.auto_attendance:
                await self._create_leave_absence_attendance(company_id, reviewer_id, row)
            row.status = "approved"
        else:
            row.status = "rejected"

        row.reviewed_by = reviewer_id
        row.reviewed_at = datetime.now(timezone.utc)
        row.review_note = data.review_note
        self._audit(company_id, reviewer_id, "hr.leave.reviewed", "LeaveRequest", row.id)
        await self.db.commit()
        return await self.get_leave_request(row.id, company_id)

    async def cancel_leave_request(self, request_id: uuid.UUID, company_id: uuid.UUID, user_id: uuid.UUID) -> LeaveRequest:
        row = await self._get_leave_request_for_update(request_id, company_id)
        if row.status not in {"pending", "approved"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Leave request cannot be cancelled")
        if row.status == "approved" and row.start_date <= date.today():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approved leave can only be cancelled before start date")

        if row.status == "approved":
            balance = await self._ensure_leave_balance(company_id, row.employee, row.leave_type, row.start_date.year)
            balance.used_days = q1(balance.used_days - row.days_requested)
            balance.remaining_days = q1(balance.remaining_days + row.days_requested)
            await self._delete_leave_absence_attendance(company_id, row)

        row.status = "cancelled"
        row.reviewed_by = user_id
        row.reviewed_at = datetime.now(timezone.utc)
        self._audit(company_id, user_id, "hr.leave.cancelled", "LeaveRequest", row.id)
        await self.db.commit()
        return await self.get_leave_request(row.id, company_id)

    async def list_leave_requests(
        self,
        company_id: uuid.UUID,
        employee_id: uuid.UUID | None = None,
        status: str | None = None,
        leave_type_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[LeaveRequest], int]:
        filters = [LeaveRequest.company_id == company_id]
        if employee_id is not None:
            filters.append(LeaveRequest.employee_id == employee_id)
        if status:
            filters.append(LeaveRequest.status == status)
        if leave_type_id is not None:
            filters.append(LeaveRequest.leave_type_id == leave_type_id)
        if date_from is not None:
            filters.append(LeaveRequest.start_date >= date_from)
        if date_to is not None:
            filters.append(LeaveRequest.end_date <= date_to)
        total = int((await self.db.scalar(select(func.count(LeaveRequest.id)).where(*filters))) or 0)
        rows = (
            await self.db.scalars(
                select(LeaveRequest)
                .where(*filters)
                .options(selectinload(LeaveRequest.employee), selectinload(LeaveRequest.leave_type))
                .order_by(LeaveRequest.created_at.desc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        ).all()
        for row in rows:
            self._hydrate_leave_request(row)
        return rows, total

    async def get_leave_request(self, request_id: uuid.UUID, company_id: uuid.UUID) -> LeaveRequest:
        row = await self.db.scalar(
            select(LeaveRequest)
            .where(LeaveRequest.id == request_id, LeaveRequest.company_id == company_id)
            .options(selectinload(LeaveRequest.employee), selectinload(LeaveRequest.leave_type))
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave request not found")
        self._hydrate_leave_request(row)
        return row

    async def get_ot_for_payroll(
        self,
        company_id: uuid.UUID,
        period_year: int,
        period_month: int,
        employee_id: uuid.UUID,
    ) -> Decimal:
        start_date = date(period_year, period_month, 1)
        end_date = date(period_year, period_month, monthrange(period_year, period_month)[1])
        total = await self.db.scalar(
            select(func.coalesce(func.sum(AttendanceRecord.ot_amount), 0))
            .where(
                AttendanceRecord.company_id == company_id,
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.work_date >= start_date,
                AttendanceRecord.work_date <= end_date,
            )
        )
        return q2(total)

    async def _get_department(self, dept_id: uuid.UUID, company_id: uuid.UUID) -> Department:
        row = await self.db.scalar(
            select(Department).where(Department.id == dept_id, Department.company_id == company_id, Department.deleted_at.is_(None))
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
        return row

    async def _get_position(self, pos_id: uuid.UUID, company_id: uuid.UUID) -> Position:
        row = await self.db.scalar(
            select(Position).where(Position.id == pos_id, Position.company_id == company_id, Position.deleted_at.is_(None))
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")
        return row

    async def _get_branch(self, company_id: uuid.UUID, branch_id: uuid.UUID) -> Branch:
        row = await self.db.scalar(
            select(Branch).where(Branch.id == branch_id, Branch.company_id == company_id, Branch.deleted_at.is_(None))
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
        return row

    async def _get_user(self, company_id: uuid.UUID, user_id: uuid.UUID) -> User:
        row = await self.db.scalar(
            select(User).where(User.id == user_id, User.company_id == company_id, User.deleted_at.is_(None))
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return row

    async def _ensure_department_code_available(self, company_id: uuid.UUID, code: str, exclude_id: uuid.UUID | None = None) -> None:
        query = select(Department.id).where(Department.company_id == company_id, Department.code == code, Department.deleted_at.is_(None))
        if exclude_id is not None:
            query = query.where(Department.id != exclude_id)
        if await self.db.scalar(query) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Department code already exists")

    async def _ensure_position_code_available(self, company_id: uuid.UUID, code: str, exclude_id: uuid.UUID | None = None) -> None:
        query = select(Position.id).where(Position.company_id == company_id, Position.code == code, Position.deleted_at.is_(None))
        if exclude_id is not None:
            query = query.where(Position.id != exclude_id)
        if await self.db.scalar(query) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Position code already exists")

    async def _ensure_employee_code_available(self, company_id: uuid.UUID, code: str, exclude_id: uuid.UUID | None = None) -> None:
        query = select(Employee.id).where(Employee.company_id == company_id, Employee.employee_code == code, Employee.deleted_at.is_(None))
        if exclude_id is not None:
            query = query.where(Employee.id != exclude_id)
        if await self.db.scalar(query) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee code already exists")

    async def _get_payroll_run_for_update(self, run_id: uuid.UUID, company_id: uuid.UUID) -> PayrollRun:
        row = await self.db.scalar(
            select(PayrollRun)
            .where(PayrollRun.id == run_id, PayrollRun.company_id == company_id)
            .options(selectinload(PayrollRun.items).selectinload(PayrollItem.lines))
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll run not found")
        return row

    async def _load_payroll_employees(self, company_id: uuid.UUID, branch_id: uuid.UUID | None, pay_date: date) -> list[Employee]:
        filters = [
            Employee.company_id == company_id,
            Employee.deleted_at.is_(None),
            Employee.is_active.is_(True),
            Employee.hire_date <= pay_date,
            or_(Employee.termination_date.is_(None), Employee.termination_date >= pay_date),
        ]
        if branch_id is not None:
            filters.append(Employee.branch_id == branch_id)
        rows = (
            await self.db.scalars(
                select(Employee)
                .where(*filters)
                .options(
                    selectinload(Employee.department),
                    selectinload(Employee.position),
                    selectinload(Employee.salaries).selectinload(EmployeeSalary.component),
                )
                .order_by(Employee.employee_code.asc())
            )
        ).all()
        return rows

    async def _load_active_employees(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None,
        department_id: uuid.UUID | None,
        active_on: date,
    ) -> list[Employee]:
        filters = [
            Employee.company_id == company_id,
            Employee.deleted_at.is_(None),
            Employee.hire_date <= active_on,
            or_(Employee.termination_date.is_(None), Employee.termination_date >= active_on),
        ]
        if branch_id is not None:
            filters.append(Employee.branch_id == branch_id)
        if department_id is not None:
            filters.append(Employee.department_id == department_id)
        return (
            await self.db.scalars(
                select(Employee)
                .where(*filters)
                .options(selectinload(Employee.department), selectinload(Employee.position), selectinload(Employee.branch))
                .order_by(Employee.employee_code.asc())
            )
        ).all()

    async def _get_employee_ytd(self, employee_id: uuid.UUID, company_id: uuid.UUID, period_year: int, period_month: int) -> tuple[Decimal, Decimal]:
        previous = await self.db.scalar(
            select(PayrollItem)
            .join(PayrollRun, PayrollRun.id == PayrollItem.run_id)
            .where(
                PayrollItem.employee_id == employee_id,
                PayrollItem.company_id == company_id,
                PayrollRun.company_id == company_id,
                PayrollRun.period_year == period_year,
                PayrollRun.status == "completed",
                PayrollRun.period_month < period_month,
            )
            .order_by(PayrollRun.period_month.desc())
            .limit(1)
        )
        if previous is None:
            return Decimal("0"), Decimal("0")
        return q2(previous.ytd_gross), q2(previous.ytd_pit)

    async def _clear_default_schedule(self, company_id: uuid.UUID) -> None:
        rows = await self.list_schedules(company_id)
        for row in rows:
            row.is_default = False

    async def _get_employee_schedule(self, company_id: uuid.UUID, employee: Employee) -> WorkSchedule | None:
        del employee
        return await self.db.scalar(
            select(WorkSchedule)
            .where(
                WorkSchedule.company_id == company_id,
                WorkSchedule.is_active.is_(True),
            )
            .order_by(WorkSchedule.is_default.desc(), WorkSchedule.created_at.asc())
            .limit(1)
        )

    async def _get_holiday_dates(self, company_id: uuid.UUID, year: int) -> set[date]:
        rows = await self.list_holidays(company_id, year)
        return {row.holiday_date for row in rows}

    async def _get_or_create_attendance_record(
        self,
        company_id: uuid.UUID,
        employee_id: uuid.UUID,
        work_date: date,
        user_id: uuid.UUID,
    ) -> AttendanceRecord:
        row = await self.db.scalar(
            select(AttendanceRecord).where(
                AttendanceRecord.company_id == company_id,
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.work_date == work_date,
            )
        )
        if row is not None:
            return row
        row = AttendanceRecord(
            company_id=company_id,
            employee_id=employee_id,
            work_date=work_date,
            created_by=user_id,
            entry_type="manual",
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def _apply_attendance_metrics(
        self,
        record: AttendanceRecord,
        employee: Employee,
        schedule: WorkSchedule | None,
        holiday_dates: set[date],
    ) -> None:
        if record.clock_in is None or record.clock_out is None:
            return
        if record.clock_out < record.clock_in:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Clock-out must be after clock-in")
        if schedule is None:
            schedule = WorkSchedule(
                company_id=employee.company_id,
                name="Default",
                work_days=[1, 2, 3, 4, 5],
                start_time="08:00",
                end_time="17:00",
                break_minutes=60,
                is_default=True,
                is_active=True,
            )

        hourly_rate = calc_hourly_rate(q2(employee.base_salary))
        is_holiday_flag = record.work_date in holiday_dates or record.work_date.isoweekday() not in schedule.work_days
        total_minutes = max(int((record.clock_out - record.clock_in).total_seconds() // 60), 0)
        work_minutes = max(total_minutes - schedule.break_minutes, 0)
        ot_minutes, ot_rate, ot_amount = calc_ot(
            clock_in=record.clock_in,
            clock_out=record.clock_out,
            schedule_start=schedule.start_time,
            schedule_end=schedule.end_time,
            break_minutes=schedule.break_minutes,
            is_holiday=is_holiday_flag,
            hourly_rate=hourly_rate,
        )
        late_flag, late_minutes = is_late(record.clock_in, schedule.start_time)
        record.schedule_id = schedule.id
        record.work_minutes = work_minutes
        record.ot_minutes = ot_minutes
        record.ot_rate = ot_rate
        record.ot_amount = ot_amount
        record.is_holiday = is_holiday_flag
        record.is_late = late_flag
        record.late_minutes = late_minutes
        record.is_absent = False

    async def _get_attendance_record(self, record_id: uuid.UUID, company_id: uuid.UUID) -> AttendanceRecord:
        row = await self.db.scalar(
            select(AttendanceRecord)
            .where(AttendanceRecord.id == record_id, AttendanceRecord.company_id == company_id)
            .options(selectinload(AttendanceRecord.employee), selectinload(AttendanceRecord.schedule))
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance record not found")
        self._hydrate_attendance(row)
        return row

    async def _get_leave_type(self, leave_type_id: uuid.UUID, company_id: uuid.UUID) -> LeaveType:
        row = await self.db.scalar(
            select(LeaveType)
            .where(LeaveType.id == leave_type_id, LeaveType.company_id == company_id, LeaveType.deleted_at.is_(None))
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave type not found")
        return row

    async def _ensure_leave_balance(
        self,
        company_id: uuid.UUID,
        employee: Employee,
        leave_type: LeaveType,
        year: int,
    ) -> LeaveBalance:
        row = await self.db.scalar(
            select(LeaveBalance)
            .where(
                LeaveBalance.company_id == company_id,
                LeaveBalance.employee_id == employee.id,
                LeaveBalance.leave_type_id == leave_type.id,
                LeaveBalance.year == year,
            )
            .options(selectinload(LeaveBalance.leave_type))
        )
        if row is not None:
            return row
        carry_over_days = Decimal("0")
        if leave_type.carry_over:
            previous = await self.db.scalar(
                select(LeaveBalance).where(
                    LeaveBalance.company_id == company_id,
                    LeaveBalance.employee_id == employee.id,
                    LeaveBalance.leave_type_id == leave_type.id,
                    LeaveBalance.year == year - 1,
                )
            )
            if previous is not None:
                carry_over_days = previous.remaining_days
                if leave_type.max_carry_over:
                    carry_over_days = min(carry_over_days, Decimal(leave_type.max_carry_over))
        entitled_days = q1(leave_type.days_per_year)
        row = LeaveBalance(
            company_id=company_id,
            employee_id=employee.id,
            leave_type_id=leave_type.id,
            year=year,
            entitled_days=entitled_days,
            used_days=Decimal("0.0"),
            remaining_days=q1(entitled_days + q1(carry_over_days)),
            carry_over_days=q1(carry_over_days),
        )
        self.db.add(row)
        await self.db.flush()
        row.leave_type = leave_type
        return row

    async def _generate_leave_request_number(self, company_id: uuid.UUID) -> str:
        today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        prefix = f"LV{today_str}-"
        count = int(
            (
                await self.db.scalar(
                    select(func.count(LeaveRequest.id)).where(
                        LeaveRequest.company_id == company_id,
                        LeaveRequest.request_number.like(f"{prefix}%"),
                    )
                )
            )
            or 0
        )
        return f"{prefix}{count + 1:04d}"

    async def _get_leave_request_for_update(self, request_id: uuid.UUID, company_id: uuid.UUID) -> LeaveRequest:
        row = await self.db.scalar(
            select(LeaveRequest)
            .where(LeaveRequest.id == request_id, LeaveRequest.company_id == company_id)
            .options(selectinload(LeaveRequest.employee), selectinload(LeaveRequest.leave_type))
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave request not found")
        return row

    async def _create_leave_absence_attendance(self, company_id: uuid.UUID, user_id: uuid.UUID, request: LeaveRequest) -> None:
        schedule = await self._get_employee_schedule(company_id, request.employee)
        work_days = schedule.work_days if schedule is not None else [1, 2, 3, 4, 5]
        holiday_dates = await self._get_holiday_dates(company_id, request.start_date.year)
        current = request.start_date
        while current <= request.end_date:
            if is_working_day(current, work_days, holiday_dates):
                row = await self.db.scalar(
                    select(AttendanceRecord).where(
                        AttendanceRecord.company_id == company_id,
                        AttendanceRecord.employee_id == request.employee_id,
                        AttendanceRecord.work_date == current,
                    )
                )
                if row is None:
                    row = AttendanceRecord(
                        company_id=company_id,
                        employee_id=request.employee_id,
                        work_date=current,
                        schedule_id=schedule.id if schedule else None,
                        is_absent=True,
                        is_holiday=False,
                        note=f"AUTO_LEAVE:{request.id}",
                        entry_type="system",
                        created_by=user_id,
                    )
                    self.db.add(row)
            current += timedelta(days=1)

    async def _delete_leave_absence_attendance(self, company_id: uuid.UUID, request: LeaveRequest) -> None:
        rows = (
            await self.db.scalars(
                select(AttendanceRecord).where(
                    AttendanceRecord.company_id == company_id,
                    AttendanceRecord.employee_id == request.employee_id,
                    AttendanceRecord.work_date >= request.start_date,
                    AttendanceRecord.work_date <= request.end_date,
                    AttendanceRecord.entry_type == "system",
                    AttendanceRecord.note == f"AUTO_LEAVE:{request.id}",
                    AttendanceRecord.is_absent.is_(True),
                )
            )
        ).all()
        for row in rows:
            await self.db.delete(row)

    def _hydrate_employee(self, employee: Employee) -> None:
        employee.department_name = employee.department.name if employee.department else None
        employee.position_name = employee.position.name if employee.position else None
        employee.branch_name = employee.branch.name if employee.branch else None

    def _hydrate_attendance(self, record: AttendanceRecord) -> None:
        record.employee_name = record.employee.full_name if record.employee else ""
        record.employee_code = record.employee.employee_code if record.employee else ""

    def _hydrate_leave_balance(self, row: LeaveBalance) -> None:
        row.leave_type_name = row.leave_type.name if row.leave_type else ""

    def _hydrate_leave_request(self, row: LeaveRequest) -> None:
        row.employee_name = row.employee.full_name if row.employee else ""
        row.leave_type_name = row.leave_type.name if row.leave_type else ""

    def _audit(self, company_id: uuid.UUID, user_id: uuid.UUID | None, action: str, resource: str, resource_id: uuid.UUID) -> None:
        self.db.add(
            AuditLog(
                company_id=company_id,
                user_id=user_id,
                action=action,
                resource=resource,
                resource_id=str(resource_id),
            )
        )
