from __future__ import annotations

from datetime import date
from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, require_permission
from app.schemas.hr import (
    AttendanceRecordRead,
    AttendanceSummary,
    ClockInRequest,
    ClockOutRequest,
    CreateLeaveRequestRequest,
    CreatePayrollRunRequest,
    DepartmentCreate,
    DepartmentRead,
    DepartmentUpdate,
    EmployeeCreate,
    EmployeeListItem,
    EmployeeRead,
    EmployeeUpdate,
    InitializeLeaveBalancesRequest,
    LeaveBalanceRead,
    LeaveRequestRead,
    LeaveTypeCreate,
    LeaveTypeRead,
    PayrollItemRead,
    PayrollRunDetailRead,
    PayrollRunRead,
    PositionCreate,
    PositionRead,
    PositionUpdate,
    PublicHolidayCreate,
    PublicHolidayRead,
    RecordAttendanceRequest,
    ReviewLeaveRequest,
    SalaryComponentRead,
    TerminateEmployeeRequest,
    WorkScheduleCreate,
    WorkScheduleRead,
)
from app.services.hr_service import HRService
from app.utils.pdf_generator import generate_payslip_pdf

router = APIRouter(prefix="/api/v1/hr", tags=["hr"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


@router.get("/departments")
async def list_departments(
    current: TokenData = Depends(require_permission("hr.employee.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await HRService(db).list_departments(current.company_id)
    return ok([DepartmentRead.model_validate(row).model_dump() for row in rows])


@router.post("/departments", status_code=status.HTTP_201_CREATED)
async def create_department(
    payload: DepartmentCreate,
    current: TokenData = Depends(require_permission("hr.employee.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).create_department(current.company_id, payload)
    return ok(DepartmentRead.model_validate(row).model_dump())


@router.patch("/departments/{dept_id}")
async def update_department(
    dept_id: uuid.UUID,
    payload: DepartmentUpdate,
    current: TokenData = Depends(require_permission("hr.employee.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).update_department(dept_id, current.company_id, payload)
    return ok(DepartmentRead.model_validate(row).model_dump())


@router.get("/positions")
async def list_positions(
    department_id: uuid.UUID | None = Query(default=None),
    current: TokenData = Depends(require_permission("hr.employee.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await HRService(db).list_positions(current.company_id, department_id=department_id)
    return ok([PositionRead.model_validate(row).model_dump() for row in rows])


@router.post("/positions", status_code=status.HTTP_201_CREATED)
async def create_position(
    payload: PositionCreate,
    current: TokenData = Depends(require_permission("hr.employee.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).create_position(current.company_id, payload)
    return ok(PositionRead.model_validate(row).model_dump())


@router.patch("/positions/{pos_id}")
async def update_position(
    pos_id: uuid.UUID,
    payload: PositionUpdate,
    current: TokenData = Depends(require_permission("hr.employee.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).update_position(pos_id, current.company_id, payload)
    return ok(PositionRead.model_validate(row).model_dump())


@router.get("/employees")
async def list_employees(
    branch_id: uuid.UUID | None = Query(default=None),
    department_id: uuid.UUID | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current: TokenData = Depends(require_permission("hr.employee.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await HRService(db).list_employees(
        current.company_id,
        branch_id=branch_id,
        department_id=department_id,
        is_active=is_active,
        search=search,
        page=page,
        limit=limit,
    )
    return ok([EmployeeListItem.model_validate(row).model_dump() for row in rows], meta={"total": total, "page": page, "limit": limit})


@router.post("/employees", status_code=status.HTTP_201_CREATED)
async def create_employee(
    payload: EmployeeCreate,
    current: TokenData = Depends(require_permission("hr.employee.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).create_employee(current.company_id, current.user_id, payload)
    return ok(EmployeeRead.model_validate(row).model_dump())


@router.get("/employees/{employee_id}")
async def get_employee(
    employee_id: uuid.UUID,
    current: TokenData = Depends(require_permission("hr.employee.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).get_employee(employee_id, current.company_id)
    return ok(EmployeeRead.model_validate(row).model_dump())


@router.patch("/employees/{employee_id}")
async def update_employee(
    employee_id: uuid.UUID,
    payload: EmployeeUpdate,
    current: TokenData = Depends(require_permission("hr.employee.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).update_employee(employee_id, current.company_id, payload)
    return ok(EmployeeRead.model_validate(row).model_dump())


@router.post("/employees/{employee_id}/terminate")
async def terminate_employee(
    employee_id: uuid.UUID,
    payload: TerminateEmployeeRequest,
    current: TokenData = Depends(require_permission("hr.employee.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).terminate_employee(employee_id, current.company_id, payload.termination_date, current.user_id)
    return ok(EmployeeRead.model_validate(row).model_dump())


@router.get("/components")
async def list_components(
    current: TokenData = Depends(require_permission("hr.employee.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await HRService(db).list_components(current.company_id)
    return ok([SalaryComponentRead.model_validate(row).model_dump() for row in rows])


@router.get("/schedules")
async def list_schedules(
    current: TokenData = Depends(require_permission("hr.attendance.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await HRService(db).list_schedules(current.company_id)
    return ok([WorkScheduleRead.model_validate(row).model_dump() for row in rows])


@router.post("/schedules", status_code=status.HTTP_201_CREATED)
async def create_schedule(
    payload: WorkScheduleCreate,
    current: TokenData = Depends(require_permission("hr.attendance.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).create_schedule(current.company_id, payload)
    return ok(WorkScheduleRead.model_validate(row).model_dump())


@router.get("/holidays")
async def list_holidays(
    year: int | None = Query(default=None),
    current: TokenData = Depends(require_permission("hr.attendance.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await HRService(db).list_holidays(current.company_id, year or date.today().year)
    return ok([PublicHolidayRead.model_validate(row).model_dump() for row in rows])


@router.post("/holidays", status_code=status.HTTP_201_CREATED)
async def create_holiday(
    payload: PublicHolidayCreate,
    current: TokenData = Depends(require_permission("hr.attendance.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).create_holiday(current.company_id, payload)
    return ok(PublicHolidayRead.model_validate(row).model_dump())


@router.delete("/holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_holiday(
    holiday_id: uuid.UUID,
    current: TokenData = Depends(require_permission("hr.attendance.edit")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await HRService(db).delete_holiday(holiday_id, current.company_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/attendance/clock-in", status_code=status.HTTP_201_CREATED)
async def clock_in(
    payload: ClockInRequest,
    current: TokenData = Depends(require_permission("hr.attendance.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).clock_in(current.company_id, current.user_id, payload)
    return ok(AttendanceRecordRead.model_validate(row).model_dump())


@router.post("/attendance/clock-out")
async def clock_out(
    payload: ClockOutRequest,
    current: TokenData = Depends(require_permission("hr.attendance.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).clock_out(current.company_id, current.user_id, payload)
    return ok(AttendanceRecordRead.model_validate(row).model_dump())


@router.post("/attendance/record")
async def record_attendance(
    payload: RecordAttendanceRequest,
    current: TokenData = Depends(require_permission("hr.attendance.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).record_attendance(current.company_id, current.user_id, payload)
    return ok(AttendanceRecordRead.model_validate(row).model_dump())


@router.get("/attendance")
async def list_attendance(
    employee_id: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    current: TokenData = Depends(require_permission("hr.attendance.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await HRService(db).list_attendance(
        current.company_id,
        employee_id=employee_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        limit=limit,
    )
    return ok([AttendanceRecordRead.model_validate(row).model_dump() for row in rows], meta={"total": total, "page": page, "limit": limit})


@router.get("/attendance/summary")
async def get_attendance_summary(
    period_year: int = Query(...),
    period_month: int = Query(..., ge=1, le=12),
    branch_id: uuid.UUID | None = Query(default=None),
    department_id: uuid.UUID | None = Query(default=None),
    current: TokenData = Depends(require_permission("hr.attendance.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await HRService(db).get_attendance_summary(
        current.company_id,
        period_year=period_year,
        period_month=period_month,
        branch_id=branch_id,
        department_id=department_id,
    )
    return ok([AttendanceSummary.model_validate(row).model_dump() for row in rows])


@router.get("/leave-types")
async def list_leave_types(
    current: TokenData = Depends(require_permission("hr.attendance.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await HRService(db).list_leave_types(current.company_id)
    return ok([LeaveTypeRead.model_validate(row).model_dump() for row in rows])


@router.post("/leave-types", status_code=status.HTTP_201_CREATED)
async def create_leave_type(
    payload: LeaveTypeCreate,
    current: TokenData = Depends(require_permission("hr.attendance.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).create_leave_type(current.company_id, payload)
    return ok(LeaveTypeRead.model_validate(row).model_dump())


@router.get("/employees/{employee_id}/leave-balances")
async def get_employee_leave_balances(
    employee_id: uuid.UUID,
    year: int | None = Query(default=None),
    current: TokenData = Depends(require_permission("hr.attendance.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await HRService(db).get_employee_leave_balances(employee_id, current.company_id, year or date.today().year)
    return ok([LeaveBalanceRead.model_validate(row).model_dump() for row in rows])


@router.post("/leave-balances/initialize")
async def initialize_leave_balances(
    payload: InitializeLeaveBalancesRequest,
    current: TokenData = Depends(require_permission("hr.attendance.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    created = await HRService(db).initialize_leave_balances(current.company_id, payload.year)
    return ok({"created": created})


@router.get("/leave-requests")
async def list_leave_requests(
    employee_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    leave_type_id: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current: TokenData = Depends(require_permission("hr.attendance.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await HRService(db).list_leave_requests(
        current.company_id,
        employee_id=employee_id,
        status=status_filter,
        leave_type_id=leave_type_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        limit=limit,
    )
    return ok([LeaveRequestRead.model_validate(row).model_dump() for row in rows], meta={"total": total, "page": page, "limit": limit})


@router.post("/leave-requests", status_code=status.HTTP_201_CREATED)
async def create_leave_request(
    payload: CreateLeaveRequestRequest,
    current: TokenData = Depends(require_permission("hr.attendance.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).create_leave_request(current.company_id, current.user_id, payload)
    return ok(LeaveRequestRead.model_validate(row).model_dump())


@router.get("/leave-requests/{request_id}")
async def get_leave_request(
    request_id: uuid.UUID,
    current: TokenData = Depends(require_permission("hr.attendance.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).get_leave_request(request_id, current.company_id)
    return ok(LeaveRequestRead.model_validate(row).model_dump())


@router.post("/leave-requests/{request_id}/review")
async def review_leave_request(
    request_id: uuid.UUID,
    payload: ReviewLeaveRequest,
    current: TokenData = Depends(require_permission("hr.attendance.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).review_leave_request(request_id, current.company_id, current.user_id, payload)
    return ok(LeaveRequestRead.model_validate(row).model_dump())


@router.post("/leave-requests/{request_id}/cancel")
async def cancel_leave_request(
    request_id: uuid.UUID,
    current: TokenData = Depends(require_permission("hr.attendance.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).cancel_leave_request(request_id, current.company_id, current.user_id)
    return ok(LeaveRequestRead.model_validate(row).model_dump())


@router.get("/payroll/runs")
async def list_payroll_runs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current: TokenData = Depends(require_permission("hr.payroll.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await HRService(db).list_payroll_runs(current.company_id, page=page, limit=limit)
    return ok([PayrollRunRead.model_validate(row).model_dump() for row in rows], meta={"total": total, "page": page, "limit": limit})


@router.post("/payroll/runs", status_code=status.HTTP_201_CREATED)
async def create_payroll_run(
    payload: CreatePayrollRunRequest,
    current: TokenData = Depends(require_permission("hr.payroll.process")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).create_payroll_run(current.company_id, current.user_id, payload)
    return ok(PayrollRunRead.model_validate(row).model_dump())


@router.get("/payroll/runs/{run_id}")
async def get_payroll_run(
    run_id: uuid.UUID,
    current: TokenData = Depends(require_permission("hr.payroll.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).get_payroll_run(run_id, current.company_id)
    return ok(PayrollRunDetailRead.model_validate(row).model_dump())


@router.post("/payroll/runs/{run_id}/process")
async def process_payroll(
    run_id: uuid.UUID,
    current: TokenData = Depends(require_permission("hr.payroll.process")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).process_payroll(run_id, current.company_id, current.user_id)
    return ok(PayrollRunRead.model_validate(row).model_dump())


@router.post("/payroll/runs/{run_id}/cancel")
async def cancel_payroll(
    run_id: uuid.UUID,
    current: TokenData = Depends(require_permission("hr.payroll.process")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await HRService(db).cancel_payroll(run_id, current.company_id, current.user_id)
    return ok(PayrollRunRead.model_validate(row).model_dump())


@router.get("/payroll/runs/{run_id}/employees/{employee_id}/payslip")
async def get_payslip(
    run_id: uuid.UUID,
    employee_id: uuid.UUID,
    current: TokenData = Depends(require_permission("hr.payroll.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    item = await HRService(db).get_employee_payslip(run_id, employee_id, current.company_id)
    return ok(PayrollItemRead.model_validate(item).model_dump())


@router.get("/payroll/runs/{run_id}/employees/{employee_id}/payslip/pdf")
async def get_payslip_pdf(
    run_id: uuid.UUID,
    employee_id: uuid.UUID,
    current: TokenData = Depends(require_permission("hr.payroll.view")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = HRService(db)
    item = await service.get_employee_payslip(run_id, employee_id, current.company_id)
    run = await service.get_payroll_run(run_id, current.company_id)
    company = await service.get_company(current.company_id)
    content, media_type = await generate_payslip_pdf(item, run, company.name, company.address or "")
    filename = f"payslip_{item.employee_code}_{run.run_number}.pdf"
    if media_type == "text/html":
        filename = filename.replace(".pdf", ".html")
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
