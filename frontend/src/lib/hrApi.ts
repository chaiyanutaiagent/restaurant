import type { ApiResponse } from "@/types/api";
import type {
  AttendanceRecord,
  AttendanceSummary,
  Department,
  Employee,
  EmployeeListItem,
  LeaveBalance,
  LeaveRequest,
  LeaveType,
  PayrollItem,
  PayrollRun,
  Position,
  PublicHoliday,
  SalaryComponent,
  WorkSchedule
} from "@/types/hr";
import api from "./api";

export const hrApi = {
  listDepts: () => api.get<ApiResponse<Department[]>>("/hr/departments"),
  createDept: (data: object) => api.post<ApiResponse<Department>>("/hr/departments", data),
  updateDept: (id: string, data: object) => api.patch<ApiResponse<Department>>(`/hr/departments/${id}`, data),

  listPositions: (deptId?: string) =>
    api.get<ApiResponse<Position[]>>("/hr/positions", { params: { department_id: deptId } }),
  createPosition: (data: object) => api.post<ApiResponse<Position>>("/hr/positions", data),
  updatePosition: (id: string, data: object) => api.patch<ApiResponse<Position>>(`/hr/positions/${id}`, data),

  listEmployees: (params?: {
    branch_id?: string;
    department_id?: string;
    is_active?: boolean;
    search?: string;
    page?: number;
    limit?: number;
  }) => api.get<ApiResponse<EmployeeListItem[]>>("/hr/employees", { params }),
  getEmployee: (id: string) => api.get<ApiResponse<Employee>>(`/hr/employees/${id}`),
  createEmployee: (data: object) => api.post<ApiResponse<Employee>>("/hr/employees", data),
  updateEmployee: (id: string, data: object) => api.patch<ApiResponse<Employee>>(`/hr/employees/${id}`, data),
  terminateEmployee: (id: string, date: string) => api.post<ApiResponse<Employee>>(`/hr/employees/${id}/terminate`, { termination_date: date }),

  listComponents: () => api.get<ApiResponse<SalaryComponent[]>>("/hr/components"),

  listSchedules: () => api.get<ApiResponse<WorkSchedule[]>>("/hr/schedules"),
  createSchedule: (data: object) => api.post<ApiResponse<WorkSchedule>>("/hr/schedules", data),

  listHolidays: (year?: number) =>
    api.get<ApiResponse<PublicHoliday[]>>("/hr/holidays", { params: { year } }),
  createHoliday: (data: object) => api.post<ApiResponse<PublicHoliday>>("/hr/holidays", data),
  deleteHoliday: (id: string) => api.delete(`/hr/holidays/${id}`),

  clockIn: (data: object) => api.post<ApiResponse<AttendanceRecord>>("/hr/attendance/clock-in", data),
  clockOut: (data: object) => api.post<ApiResponse<AttendanceRecord>>("/hr/attendance/clock-out", data),
  recordAttendance: (data: object) => api.post<ApiResponse<AttendanceRecord>>("/hr/attendance/record", data),
  listAttendance: (params?: object) => api.get<ApiResponse<AttendanceRecord[]>>("/hr/attendance", { params }),
  getAttendanceSummary: (params: object) =>
    api.get<ApiResponse<AttendanceSummary[]>>("/hr/attendance/summary", { params }),

  listLeaveTypes: () => api.get<ApiResponse<LeaveType[]>>("/hr/leave-types"),
  createLeaveType: (data: object) => api.post<ApiResponse<LeaveType>>("/hr/leave-types", data),
  listLeaveBalances: (employeeId: string, year?: number) =>
    api.get<ApiResponse<LeaveBalance[]>>(`/hr/employees/${employeeId}/leave-balances`, { params: { year } }),
  initLeaveBalances: (year: number) => api.post<ApiResponse<{ created: number }>>("/hr/leave-balances/initialize", { year }),
  listLeaveRequests: (params?: object) =>
    api.get<ApiResponse<LeaveRequest[]>>("/hr/leave-requests", { params }),
  getLeaveRequest: (id: string) => api.get<ApiResponse<LeaveRequest>>(`/hr/leave-requests/${id}`),
  createLeaveRequest: (data: object) => api.post<ApiResponse<LeaveRequest>>("/hr/leave-requests", data),
  reviewLeaveRequest: (id: string, data: object) =>
    api.post<ApiResponse<LeaveRequest>>(`/hr/leave-requests/${id}/review`, data),
  cancelLeaveRequest: (id: string) =>
    api.post<ApiResponse<LeaveRequest>>(`/hr/leave-requests/${id}/cancel`),

  listPayrollRuns: (params?: { page?: number; limit?: number }) =>
    api.get<ApiResponse<PayrollRun[]>>("/hr/payroll/runs", { params }),
  createPayrollRun: (data: object) => api.post<ApiResponse<PayrollRun>>("/hr/payroll/runs", data),
  getPayrollRun: (id: string) => api.get<ApiResponse<PayrollRun>>(`/hr/payroll/runs/${id}`),
  processPayroll: (id: string) => api.post<ApiResponse<PayrollRun>>(`/hr/payroll/runs/${id}/process`),
  cancelPayroll: (id: string) => api.post<ApiResponse<PayrollRun>>(`/hr/payroll/runs/${id}/cancel`),
  getPayslip: (runId: string, employeeId: string) =>
    api.get<ApiResponse<PayrollItem>>(`/hr/payroll/runs/${runId}/employees/${employeeId}/payslip`),
  downloadPayslip: (runId: string, employeeId: string) =>
    api.get(`/hr/payroll/runs/${runId}/employees/${employeeId}/payslip/pdf`, { responseType: "blob" })
};
