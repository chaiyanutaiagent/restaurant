export type EmploymentType = "fulltime" | "parttime" | "contract" | "daily";
export type PayrollStatus = "draft" | "processing" | "completed" | "cancelled";

export interface Department {
  id: string;
  company_id: string;
  code: string;
  name: string;
  name_en: string | null;
  parent_id: string | null;
  is_active: boolean;
}

export interface Position {
  id: string;
  company_id: string;
  department_id: string | null;
  code: string;
  name: string;
  name_en: string | null;
  level: number;
  is_active: boolean;
}

export interface Employee {
  id: string;
  company_id: string;
  branch_id: string;
  user_id: string | null;
  employee_code: string;
  department_id: string | null;
  position_id: string | null;
  title: string | null;
  first_name: string;
  last_name: string;
  first_name_en: string | null;
  last_name_en: string | null;
  date_of_birth: string | null;
  gender: string | null;
  national_id: string | null;
  phone: string | null;
  email: string | null;
  hire_date: string;
  employment_type: EmploymentType;
  base_salary: number;
  salary_type: string;
  bank_name: string | null;
  bank_account: string | null;
  sso_registered: boolean;
  is_active: boolean;
  department_name: string | null;
  position_name: string | null;
  branch_name: string | null;
  created_at: string;
}

export interface EmployeeListItem {
  id: string;
  employee_code: string;
  title: string | null;
  first_name: string;
  last_name: string;
  department_name: string | null;
  position_name: string | null;
  branch_name: string | null;
  employment_type: EmploymentType;
  base_salary: number;
  is_active: boolean;
  hire_date: string;
}

export interface SalaryComponent {
  id: string;
  code: string;
  name: string;
  component_type: "earning" | "deduction";
  is_taxable: boolean;
  is_sso_base: boolean;
  is_fixed: boolean;
  is_system: boolean;
  sort_order: number;
  is_active: boolean;
}

export interface PayrollItemLine {
  component_name: string;
  component_type: string;
  amount: number;
  note: string | null;
}

export interface PayrollItem {
  id: string;
  employee_id: string;
  employee_name: string;
  employee_code: string;
  position_name: string | null;
  department_name: string | null;
  bank_account: string | null;
  base_salary: number;
  earnings_total: number;
  sso_employee: number;
  sso_employer: number;
  pit_withheld: number;
  other_deductions: number;
  total_deductions: number;
  net_pay: number;
  ytd_gross: number;
  ytd_pit: number;
  lines: PayrollItemLine[];
}

export interface PayrollRun {
  id: string;
  run_number: string;
  period_year: number;
  period_month: number;
  pay_date: string;
  status: PayrollStatus;
  branch_id: string | null;
  total_employees: number;
  total_gross: number;
  total_deductions: number;
  total_net: number;
  total_sso_employee: number;
  total_sso_employer: number;
  total_pit: number;
  note: string | null;
  created_at: string;
  processed_at: string | null;
  items?: PayrollItem[];
}

export interface WorkSchedule {
  id: string;
  name: string;
  work_days: number[];
  start_time: string;
  end_time: string;
  break_minutes: number;
  is_default: boolean;
  is_active: boolean;
}

export interface PublicHoliday {
  id: string;
  holiday_date: string;
  name: string;
  name_en: string | null;
  is_recurring: boolean;
}

export interface AttendanceRecord {
  id: string;
  employee_id: string;
  employee_name: string;
  employee_code: string;
  work_date: string;
  clock_in: string | null;
  clock_out: string | null;
  work_minutes: number | null;
  ot_minutes: number;
  ot_rate: number;
  ot_amount: number;
  is_absent: boolean;
  is_late: boolean;
  late_minutes: number;
  is_holiday: boolean;
  note: string | null;
  entry_type: string;
}

export interface AttendanceSummary {
  employee_id: string;
  employee_name: string;
  employee_code: string;
  period_year: number;
  period_month: number;
  total_days: number;
  present_days: number;
  absent_days: number;
  late_days: number;
  total_late_minutes: number;
  ot_days: number;
  total_ot_minutes: number;
  total_ot_amount: number;
}

export interface LeaveType {
  id: string;
  code: string;
  name: string;
  name_en: string | null;
  days_per_year: number;
  is_paid: boolean;
  carry_over: boolean;
  max_carry_over: number;
  requires_doc: boolean;
  gender_restrict: string | null;
  is_active: boolean;
  is_system: boolean;
}

export interface LeaveBalance {
  id: string;
  employee_id: string;
  leave_type_id: string;
  leave_type_name: string;
  year: number;
  entitled_days: number;
  used_days: number;
  remaining_days: number;
  carry_over_days: number;
}

export interface LeaveRequest {
  id: string;
  request_number: string;
  employee_id: string;
  employee_name: string;
  leave_type_id: string;
  leave_type_name: string;
  status: "pending" | "approved" | "rejected" | "cancelled";
  start_date: string;
  end_date: string;
  days_requested: number;
  reason: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  created_at: string;
}
