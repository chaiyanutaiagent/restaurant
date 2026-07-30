import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import { usePermission } from "@/hooks/usePermission";
import { branchApi, userApi } from "@/lib/adminApi";
import { hrApi } from "@/lib/hrApi";
import type {
  AttendanceRecord,
  AttendanceSummary,
  Department,
  EmployeeListItem,
  LeaveBalance,
  LeaveRequest,
  LeaveType,
  PayrollRun,
  Position,
  PublicHoliday
} from "@/types/hr";
import CreateEmployeeDialog from "./CreateEmployeeDialog";
import CreateLeaveRequestDialog from "./CreateLeaveRequestDialog";
import CreatePayrollDialog from "./CreatePayrollDialog";
import EmployeeDetailDialog from "./EmployeeDetailDialog";
import PayrollRunDetailDialog from "./PayrollRunDetailDialog";
import RecordAttendanceDialog from "./RecordAttendanceDialog";
import ReviewLeaveDialog from "./ReviewLeaveDialog";

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(value || 0);
}

function formatThaiDate(value: string): string {
  const date = new Date(value);
  return date.toLocaleDateString("th-TH", { day: "2-digit", month: "short", year: "numeric" });
}

function formatTime(value: string | null): string {
  if (!value) return "-";
  return new Date(value).toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" });
}

function formatHours(minutes: number | null): string {
  if (!minutes) return "-";
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`;
}

function employmentBadge(type: string): string {
  if (type === "fulltime") return "bg-blue-100 text-blue-700";
  if (type === "parttime") return "bg-teal-100 text-teal-700";
  if (type === "contract") return "bg-purple-100 text-purple-700";
  return "bg-gray-100 text-gray-700";
}

function payrollStatusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "completed") return "default";
  if (status === "cancelled") return "destructive";
  if (status === "draft") return "secondary";
  return "outline";
}

function attendanceStatus(record: AttendanceRecord): { label: string; variant: "default" | "secondary" | "destructive" | "outline" } {
  if (record.is_absent) return { label: "ขาดงาน", variant: "destructive" };
  if (record.is_holiday) return { label: "วันหยุด", variant: "outline" };
  if (record.is_late) return { label: "สาย", variant: "secondary" };
  return { label: "ปกติ", variant: "default" };
}

function leaveStatusVariant(status: LeaveRequest["status"]): string {
  if (status === "approved") return "bg-green-100 text-green-700";
  if (status === "rejected") return "bg-red-100 text-red-700";
  if (status === "cancelled") return "bg-gray-100 text-gray-700";
  return "bg-yellow-100 text-yellow-800";
}

export default function HRPage(): JSX.Element {
  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonth = now.getMonth() + 1;
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const canCreateEmployee = usePermission("hr.employee.create");
  const canEditEmployee = usePermission("hr.employee.edit");
  const canProcessPayroll = usePermission("hr.payroll.process");
  const canEditAttendance = usePermission("hr.attendance.edit");

  const [branchFilter, setBranchFilter] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("active");
  const [search, setSearch] = useState("");
  const [selectedDeptId, setSelectedDeptId] = useState<string>("");
  const [createEmployeeOpen, setCreateEmployeeOpen] = useState(false);
  const [employeeDetailId, setEmployeeDetailId] = useState<string | null>(null);
  const [createPayrollOpen, setCreatePayrollOpen] = useState(false);
  const [runDetailId, setRunDetailId] = useState<string | null>(null);
  const [recordAttendanceOpen, setRecordAttendanceOpen] = useState(false);
  const [createLeaveOpen, setCreateLeaveOpen] = useState(false);
  const [reviewLeaveOpen, setReviewLeaveOpen] = useState(false);
  const [selectedLeaveRequest, setSelectedLeaveRequest] = useState<LeaveRequest | null>(null);

  const [attendanceEmployeeId, setAttendanceEmployeeId] = useState("");
  const [attendanceDateFrom, setAttendanceDateFrom] = useState("");
  const [attendanceDateTo, setAttendanceDateTo] = useState("");
  const [summaryYear, setSummaryYear] = useState(String(currentYear));
  const [summaryMonth, setSummaryMonth] = useState(String(currentMonth));
  const [holidayYear, setHolidayYear] = useState(String(currentYear));
  const [newHolidayDate, setNewHolidayDate] = useState("");
  const [newHolidayName, setNewHolidayName] = useState("");

  const [leaveEmployeeId, setLeaveEmployeeId] = useState("");
  const [leaveTypeId, setLeaveTypeId] = useState("");
  const [leaveStatus, setLeaveStatus] = useState("");
  const [leaveDateFrom, setLeaveDateFrom] = useState("");
  const [leaveDateTo, setLeaveDateTo] = useState("");
  const [balanceEmployeeId, setBalanceEmployeeId] = useState("");
  const [balanceYear, setBalanceYear] = useState(String(currentYear));

  const branchesQuery = useQuery({
    queryKey: ["hr", "branches"],
    queryFn: async () => (await branchApi.list()).data.data
  });
  const usersQuery = useQuery({
    queryKey: ["hr", "users"],
    queryFn: async () => (await userApi.list({ page: 1, limit: 100 })).data.data
  });
  const departmentsQuery = useQuery({
    queryKey: ["hr", "departments"],
    queryFn: async () => (await hrApi.listDepts()).data.data
  });
  const positionsQuery = useQuery({
    queryKey: ["hr", "positions", selectedDeptId],
    queryFn: async () => (await hrApi.listPositions(selectedDeptId || undefined)).data.data
  });
  const employeesQuery = useQuery({
    queryKey: ["hr", "employees", { branchFilter, departmentFilter, statusFilter, search }],
    queryFn: async () =>
      (await hrApi.listEmployees({
        branch_id: branchFilter || undefined,
        department_id: departmentFilter || undefined,
        is_active: statusFilter === "all" ? undefined : statusFilter === "active",
        search: search || undefined,
        page: 1,
        limit: 100
      })).data.data
  });
  const allEmployeesQuery = useQuery({
    queryKey: ["hr", "employees", "all"],
    queryFn: async () => (await hrApi.listEmployees({ page: 1, limit: 200 })).data.data
  });
  const payrollRunsQuery = useQuery({
    queryKey: ["hr", "payroll-runs"],
    queryFn: async () => (await hrApi.listPayrollRuns({ page: 1, limit: 100 })).data.data
  });
  const leaveTypesQuery = useQuery({
    queryKey: ["hr", "leave-types"],
    queryFn: async () => (await hrApi.listLeaveTypes()).data.data
  });
  const attendanceQuery = useQuery({
    queryKey: ["hr", "attendance", { attendanceEmployeeId, attendanceDateFrom, attendanceDateTo }],
    queryFn: async () =>
      (await hrApi.listAttendance({
        employee_id: attendanceEmployeeId || undefined,
        date_from: attendanceDateFrom || undefined,
        date_to: attendanceDateTo || undefined,
        page: 1,
        limit: 100
      })).data.data
  });
  const attendanceSummaryQuery = useQuery({
    queryKey: ["hr", "attendance-summary", { summaryYear, summaryMonth, branchFilter, departmentFilter }],
    queryFn: async () =>
      (await hrApi.getAttendanceSummary({
        period_year: Number(summaryYear),
        period_month: Number(summaryMonth),
        branch_id: branchFilter || undefined,
        department_id: departmentFilter || undefined
      })).data.data
  });
  const holidaysQuery = useQuery({
    queryKey: ["hr", "holidays", holidayYear],
    queryFn: async () => (await hrApi.listHolidays(Number(holidayYear))).data.data
  });
  const leaveRequestsQuery = useQuery({
    queryKey: ["hr", "leave-requests", { leaveEmployeeId, leaveTypeId, leaveStatus, leaveDateFrom, leaveDateTo }],
    queryFn: async () =>
      (await hrApi.listLeaveRequests({
        employee_id: leaveEmployeeId || undefined,
        leave_type_id: leaveTypeId || undefined,
        status: leaveStatus || undefined,
        date_from: leaveDateFrom || undefined,
        date_to: leaveDateTo || undefined,
        page: 1,
        limit: 100
      })).data.data
  });
  const leaveBalancesQuery = useQuery({
    queryKey: ["hr", "leave-balances", balanceEmployeeId, balanceYear],
    queryFn: async () => {
      if (!balanceEmployeeId) return [] as LeaveBalance[];
      return (await hrApi.listLeaveBalances(balanceEmployeeId, Number(balanceYear))).data.data;
    },
    enabled: Boolean(balanceEmployeeId)
  });

  const branches = branchesQuery.data ?? [];
  const users = usersQuery.data ?? [];
  const departments = (departmentsQuery.data ?? []) as Department[];
  const positions = (positionsQuery.data ?? []) as Position[];
  const employees = useMemo(() => {
    const rows = (employeesQuery.data ?? []) as EmployeeListItem[];
    return rows.filter((employee) => !typeFilter || employee.employment_type === typeFilter);
  }, [employeesQuery.data, typeFilter]);
  const allEmployees = (allEmployeesQuery.data ?? []) as EmployeeListItem[];
  const payrollRuns = (payrollRunsQuery.data ?? []) as PayrollRun[];
  const leaveTypes = (leaveTypesQuery.data ?? []) as LeaveType[];
  const attendanceRecords = (attendanceQuery.data ?? []) as AttendanceRecord[];
  const attendanceSummaries = (attendanceSummaryQuery.data ?? []) as AttendanceSummary[];
  const holidays = (holidaysQuery.data ?? []) as PublicHoliday[];
  const leaveRequests = (leaveRequestsQuery.data ?? []) as LeaveRequest[];
  const leaveBalances = (leaveBalancesQuery.data ?? []) as LeaveBalance[];

  const cancelPayrollMutation = useMutation({
    mutationFn: async (runId: string) => hrApi.cancelPayroll(runId),
    onSuccess: async () => {
      toast({ title: "ยกเลิกรอบเงินเดือนแล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["hr"] });
    },
    onError: (error: Error) => {
      toast({ title: "ยกเลิกไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const terminateEmployeeMutation = useMutation({
    mutationFn: async (employeeId: string) => hrApi.terminateEmployee(employeeId, new Date().toISOString().slice(0, 10)),
    onSuccess: async () => {
      toast({ title: "บันทึกการออกจากงานแล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["hr"] });
    },
    onError: (error: Error) => {
      toast({ title: "ไม่สามารถออกจากงานได้", description: error.message, variant: "destructive" });
    }
  });

  const createHolidayMutation = useMutation({
    mutationFn: async () => {
      if (!newHolidayDate || !newHolidayName.trim()) throw new Error("กรอกวันหยุดให้ครบ");
      return hrApi.createHoliday({ holiday_date: newHolidayDate, name: newHolidayName, name_en: null, is_recurring: true });
    },
    onSuccess: async () => {
      toast({ title: "เพิ่มวันหยุดแล้ว" });
      setNewHolidayDate("");
      setNewHolidayName("");
      await queryClient.invalidateQueries({ queryKey: ["hr", "holidays"] });
    },
    onError: (error: Error) => {
      toast({ title: "เพิ่มวันหยุดไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const deleteHolidayMutation = useMutation({
    mutationFn: async (holidayId: string) => hrApi.deleteHoliday(holidayId),
    onSuccess: async () => {
      toast({ title: "ลบวันหยุดแล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["hr", "holidays"] });
    },
    onError: (error: Error) => {
      toast({ title: "ลบวันหยุดไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const initializeBalancesMutation = useMutation({
    mutationFn: async () => hrApi.initLeaveBalances(Number(balanceYear)),
    onSuccess: async (response) => {
      toast({ title: `สร้างโควต้าแล้ว ${response.data.data.created} รายการ` });
      await queryClient.invalidateQueries({ queryKey: ["hr"] });
    },
    onError: (error: Error) => {
      toast({ title: "กำหนดโควต้าไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  async function quickCreateDepartment(): Promise<void> {
    const code = window.prompt("รหัสแผนก");
    const name = window.prompt("ชื่อแผนก");
    if (!code || !name) return;
    await hrApi.createDept({ code, name, parent_id: selectedDeptId || null, is_active: true });
    await queryClient.invalidateQueries({ queryKey: ["hr", "departments"] });
  }

  async function quickCreatePosition(): Promise<void> {
    const code = window.prompt("รหัสตำแหน่ง");
    const name = window.prompt("ชื่อตำแหน่ง");
    if (!code || !name) return;
    await hrApi.createPosition({ code, name, department_id: selectedDeptId || null, level: 1, is_active: true });
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["hr", "positions"] }),
      queryClient.invalidateQueries({ queryKey: ["hr", "employees"] })
    ]);
  }

  async function quickCreateLeaveType(): Promise<void> {
    const code = window.prompt("รหัสประเภทลา");
    const name = window.prompt("ชื่อประเภทลา");
    if (!code || !name) return;
    await hrApi.createLeaveType({
      code,
      name,
      name_en: null,
      days_per_year: 0,
      is_paid: true,
      carry_over: false,
      max_carry_over: 0,
      requires_doc: false,
      gender_restrict: null,
      is_active: true,
      is_system: false
    });
    await queryClient.invalidateQueries({ queryKey: ["hr", "leave-types"] });
  }

  return (
    <div className="space-y-6">
      <PageHeader title="ทรัพยากรบุคคล" subtitle="HR Management" />

      <Tabs defaultValue="employees">
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="employees">พนักงาน</TabsTrigger>
          <TabsTrigger value="org">แผนกและตำแหน่ง</TabsTrigger>
          <TabsTrigger value="payroll">เงินเดือน</TabsTrigger>
          <TabsTrigger value="attendance">การเข้างาน</TabsTrigger>
          <TabsTrigger value="leave">การลา</TabsTrigger>
        </TabsList>

        <TabsContent value="employees">
          <Card>
            <CardContent className="space-y-4 p-4">
              <div className="flex flex-col gap-3 xl:flex-row">
                <select className="h-10 rounded-md border border-gray-300 px-3" value={branchFilter} onChange={(event) => setBranchFilter(event.target.value)}>
                  <option value="">ทุกสาขา</option>
                  {branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}
                </select>
                <select className="h-10 rounded-md border border-gray-300 px-3" value={departmentFilter} onChange={(event) => setDepartmentFilter(event.target.value)}>
                  <option value="">ทุกแผนก</option>
                  {departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
                </select>
                <select className="h-10 rounded-md border border-gray-300 px-3" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
                  <option value="">ทุกประเภท</option>
                  <option value="fulltime">Full-time</option>
                  <option value="parttime">Part-time</option>
                  <option value="contract">Contract</option>
                  <option value="daily">Daily</option>
                </select>
                <select className="h-10 rounded-md border border-gray-300 px-3" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                  <option value="all">ทุกสถานะ</option>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
                <Input className="xl:max-w-sm" placeholder="ค้นหาชื่อ หรือรหัสพนักงาน" value={search} onChange={(event) => setSearch(event.target.value)} />
                {canCreateEmployee ? (
                  <Button className="xl:ml-auto" onClick={() => setCreateEmployeeOpen(true)}>
                    <Plus className="h-4 w-4" />
                    เพิ่มพนักงาน
                  </Button>
                ) : null}
              </div>

              <div className="overflow-x-auto rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>รหัส</TableHead>
                      <TableHead>ชื่อ-นามสกุล</TableHead>
                      <TableHead>แผนก / ตำแหน่ง</TableHead>
                      <TableHead>สาขา</TableHead>
                      <TableHead>ประเภท</TableHead>
                      <TableHead>เงินเดือน</TableHead>
                      <TableHead>วันที่เข้างาน</TableHead>
                      <TableHead>สถานะ</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {employees.map((employee) => (
                      <TableRow key={employee.id}>
                        <TableCell className="font-mono">{employee.employee_code}</TableCell>
                        <TableCell>{[employee.title, employee.first_name, employee.last_name].filter(Boolean).join(" ")}</TableCell>
                        <TableCell>
                          <div>{employee.department_name ?? "-"}</div>
                          <div className="text-xs text-gray-500">{employee.position_name ?? "-"}</div>
                        </TableCell>
                        <TableCell>{employee.branch_name ?? "-"}</TableCell>
                        <TableCell><span className={`rounded-full px-2 py-1 text-xs font-medium ${employmentBadge(employee.employment_type)}`}>{employee.employment_type}</span></TableCell>
                        <TableCell>{formatCurrency(employee.base_salary)}</TableCell>
                        <TableCell>{formatThaiDate(employee.hire_date)}</TableCell>
                        <TableCell><Badge variant={employee.is_active ? "default" : "destructive"}>{employee.is_active ? "active" : "inactive"}</Badge></TableCell>
                        <TableCell>
                          <div className="flex gap-2">
                            <Button variant="outline" size="sm" onClick={() => setEmployeeDetailId(employee.id)}>
                              <Pencil className="h-4 w-4" />
                              ดู/แก้ไข
                            </Button>
                            {canEditEmployee ? (
                              <Button variant="outline" size="sm" onClick={() => terminateEmployeeMutation.mutate(employee.id)}>
                                ออกจากงาน
                              </Button>
                            ) : null}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="org">
          <div className="grid gap-6 lg:grid-cols-[1.1fr,1.4fr]">
            <Card>
              <CardContent className="space-y-4 p-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold">แผนก</h3>
                  {canCreateEmployee ? <Button variant="outline" onClick={() => void quickCreateDepartment()}>เพิ่มแผนก</Button> : null}
                </div>
                <div className="space-y-2">
                  {departments.map((department) => {
                    const count = employees.filter((employee) => employee.department_name === department.name).length;
                    return (
                      <button
                        key={department.id}
                        type="button"
                        onClick={() => setSelectedDeptId(department.id)}
                        className={`w-full rounded-lg border px-4 py-3 text-left ${selectedDeptId === department.id ? "border-blue-500 bg-blue-50" : "border-gray-200"}`}
                      >
                        <div className="font-medium">{department.code} • {department.name}</div>
                        <div className="text-sm text-gray-500">{count} employees</div>
                      </button>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="space-y-4 p-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold">ตำแหน่ง</h3>
                  {canCreateEmployee ? <Button variant="outline" onClick={() => void quickCreatePosition()}>เพิ่มตำแหน่ง</Button> : null}
                </div>
                <div className="overflow-x-auto rounded-lg border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>code</TableHead>
                        <TableHead>name</TableHead>
                        <TableHead>level</TableHead>
                        <TableHead>employee count</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {positions.map((position) => {
                        const count = employees.filter((employee) => employee.position_name === position.name).length;
                        return (
                          <TableRow key={position.id}>
                            <TableCell className="font-mono">{position.code}</TableCell>
                            <TableCell>{position.name}</TableCell>
                            <TableCell>{position.level}</TableCell>
                            <TableCell>{count}</TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="payroll">
          <Card>
            <CardContent className="space-y-4 p-4">
              <div className="flex justify-end">
                {canProcessPayroll ? (
                  <Button onClick={() => setCreatePayrollOpen(true)}>
                    <Plus className="h-4 w-4" />
                    สร้างรอบเงินเดือน
                  </Button>
                ) : null}
              </div>

              <div className="overflow-x-auto rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>รอบเงินเดือน</TableHead>
                      <TableHead>งวด</TableHead>
                      <TableHead>วันจ่าย</TableHead>
                      <TableHead>จำนวนพนักงาน</TableHead>
                      <TableHead>รายได้รวม</TableHead>
                      <TableHead>รายการหัก</TableHead>
                      <TableHead>สุทธิจ่าย</TableHead>
                      <TableHead>สถานะ</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {payrollRuns.map((run) => (
                      <TableRow key={run.id}>
                        <TableCell className="font-mono">{run.run_number}</TableCell>
                        <TableCell>{run.period_month}/{run.period_year + 543}</TableCell>
                        <TableCell>{formatThaiDate(run.pay_date)}</TableCell>
                        <TableCell>{run.total_employees}</TableCell>
                        <TableCell>{formatCurrency(run.total_gross)}</TableCell>
                        <TableCell>{formatCurrency(run.total_deductions)}</TableCell>
                        <TableCell className="font-semibold text-blue-700">{formatCurrency(run.total_net)}</TableCell>
                        <TableCell><Badge variant={payrollStatusVariant(run.status)}>{run.status}</Badge></TableCell>
                        <TableCell>
                          <div className="flex gap-2">
                            {run.status === "draft" ? (
                              <>
                                <Button size="sm" onClick={() => setRunDetailId(run.id)}>ประมวลผล</Button>
                                <Button variant="outline" size="sm" onClick={() => cancelPayrollMutation.mutate(run.id)}>ยกเลิก</Button>
                              </>
                            ) : null}
                            {run.status === "completed" ? (
                              <Button variant="outline" size="sm" onClick={() => setRunDetailId(run.id)}>ดูรายละเอียด</Button>
                            ) : null}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="attendance">
          <Tabs defaultValue="records">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="records">บันทึกเข้างาน</TabsTrigger>
              <TabsTrigger value="summary">สรุปรายเดือน</TabsTrigger>
              <TabsTrigger value="holidays">วันหยุด</TabsTrigger>
            </TabsList>

            <TabsContent value="records">
              <Card>
                <CardContent className="space-y-4 p-4">
                  <div className="flex flex-col gap-3 lg:flex-row">
                    <select className="h-10 rounded-md border border-gray-300 px-3" value={attendanceEmployeeId} onChange={(event) => setAttendanceEmployeeId(event.target.value)}>
                      <option value="">ทุกพนักงาน</option>
                      {allEmployees.map((employee) => (
                        <option key={employee.id} value={employee.id}>
                          {employee.employee_code} • {[employee.first_name, employee.last_name].join(" ")}
                        </option>
                      ))}
                    </select>
                    <Input type="date" value={attendanceDateFrom} onChange={(event) => setAttendanceDateFrom(event.target.value)} />
                    <Input type="date" value={attendanceDateTo} onChange={(event) => setAttendanceDateTo(event.target.value)} />
                    {canEditAttendance ? (
                      <Button className="lg:ml-auto" onClick={() => setRecordAttendanceOpen(true)}>
                        <Plus className="h-4 w-4" />
                        บันทึกย้อนหลัง
                      </Button>
                    ) : null}
                  </div>
                  <div className="overflow-x-auto rounded-lg border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>พนักงาน</TableHead>
                          <TableHead>วันที่</TableHead>
                          <TableHead>เข้างาน</TableHead>
                          <TableHead>ออกงาน</TableHead>
                          <TableHead>ชั่วโมงทำงาน</TableHead>
                          <TableHead>OT (นาที)</TableHead>
                          <TableHead>OT (฿)</TableHead>
                          <TableHead>สถานะ</TableHead>
                          <TableHead>หมายเหตุ</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {attendanceRecords.map((record) => {
                          const statusMeta = attendanceStatus(record);
                          return (
                            <TableRow key={record.id}>
                              <TableCell>
                                <div>{record.employee_name}</div>
                                <div className="text-xs text-gray-500">{record.employee_code}</div>
                              </TableCell>
                              <TableCell>{formatThaiDate(record.work_date)}</TableCell>
                              <TableCell>{formatTime(record.clock_in)}</TableCell>
                              <TableCell>{formatTime(record.clock_out)}</TableCell>
                              <TableCell>{formatHours(record.work_minutes)}</TableCell>
                              <TableCell>{record.ot_minutes}</TableCell>
                              <TableCell>{formatCurrency(record.ot_amount)}</TableCell>
                              <TableCell><Badge variant={statusMeta.variant}>{statusMeta.label}</Badge></TableCell>
                              <TableCell>{record.note || "-"}</TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="summary">
              <Card>
                <CardContent className="space-y-4 p-4">
                  <div className="flex flex-col gap-3 lg:flex-row">
                    <Input type="number" value={summaryYear} onChange={(event) => setSummaryYear(event.target.value)} />
                    <select className="h-10 rounded-md border border-gray-300 px-3" value={summaryMonth} onChange={(event) => setSummaryMonth(event.target.value)}>
                      {Array.from({ length: 12 }, (_, index) => (
                        <option key={index + 1} value={index + 1}>{index + 1}</option>
                      ))}
                    </select>
                    <select className="h-10 rounded-md border border-gray-300 px-3" value={branchFilter} onChange={(event) => setBranchFilter(event.target.value)}>
                      <option value="">ทุกสาขา</option>
                      {branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}
                    </select>
                    <select className="h-10 rounded-md border border-gray-300 px-3" value={departmentFilter} onChange={(event) => setDepartmentFilter(event.target.value)}>
                      <option value="">ทุกแผนก</option>
                      {departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
                    </select>
                  </div>
                  <div className="overflow-x-auto rounded-lg border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>รหัส</TableHead>
                          <TableHead>ชื่อ</TableHead>
                          <TableHead>มาทำงาน</TableHead>
                          <TableHead>ขาด</TableHead>
                          <TableHead>สาย</TableHead>
                          <TableHead>OT ชม.</TableHead>
                          <TableHead>OT ฿</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {attendanceSummaries.map((row) => (
                          <TableRow key={row.employee_id}>
                            <TableCell>{row.employee_code}</TableCell>
                            <TableCell>{row.employee_name}</TableCell>
                            <TableCell>{row.present_days}</TableCell>
                            <TableCell>{row.absent_days}</TableCell>
                            <TableCell>{row.late_days}</TableCell>
                            <TableCell>{(row.total_ot_minutes / 60).toFixed(1)}</TableCell>
                            <TableCell>{formatCurrency(row.total_ot_amount)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="holidays">
              <Card>
                <CardContent className="space-y-4 p-4">
                  <div className="flex flex-col gap-3 lg:flex-row">
                    <Input type="number" value={holidayYear} onChange={(event) => setHolidayYear(event.target.value)} />
                    {canEditAttendance ? (
                      <>
                        <Input type="date" value={newHolidayDate} onChange={(event) => setNewHolidayDate(event.target.value)} />
                        <Input placeholder="ชื่อวันหยุด" value={newHolidayName} onChange={(event) => setNewHolidayName(event.target.value)} />
                        <Button onClick={() => createHolidayMutation.mutate()}>
                          <Plus className="h-4 w-4" />
                          เพิ่มวันหยุด
                        </Button>
                      </>
                    ) : null}
                  </div>
                  <div className="overflow-x-auto rounded-lg border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>วันที่</TableHead>
                          <TableHead>ชื่อวันหยุด</TableHead>
                          <TableHead>ชื่ออังกฤษ</TableHead>
                          <TableHead>Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {holidays.map((holiday) => (
                          <TableRow key={`${holiday.id}-${holiday.holiday_date}`}>
                            <TableCell>{formatThaiDate(holiday.holiday_date)}</TableCell>
                            <TableCell>{holiday.name}</TableCell>
                            <TableCell>{holiday.name_en || "-"}</TableCell>
                            <TableCell>
                              {canEditAttendance ? (
                                <Button variant="outline" size="sm" onClick={() => deleteHolidayMutation.mutate(holiday.id)}>
                                  <Trash2 className="h-4 w-4" />
                                  ลบ
                                </Button>
                              ) : "-"}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </TabsContent>

        <TabsContent value="leave">
          <Tabs defaultValue="requests">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="requests">คำขอลา</TabsTrigger>
              <TabsTrigger value="balances">วันลาคงเหลือ</TabsTrigger>
              <TabsTrigger value="types">ตั้งค่าประเภทลา</TabsTrigger>
            </TabsList>

            <TabsContent value="requests">
              <Card>
                <CardContent className="space-y-4 p-4">
                  <div className="flex flex-col gap-3 lg:flex-row">
                    <select className="h-10 rounded-md border border-gray-300 px-3" value={leaveEmployeeId} onChange={(event) => setLeaveEmployeeId(event.target.value)}>
                      <option value="">ทุกพนักงาน</option>
                      {allEmployees.map((employee) => (
                        <option key={employee.id} value={employee.id}>
                          {employee.employee_code} • {[employee.first_name, employee.last_name].join(" ")}
                        </option>
                      ))}
                    </select>
                    <select className="h-10 rounded-md border border-gray-300 px-3" value={leaveTypeId} onChange={(event) => setLeaveTypeId(event.target.value)}>
                      <option value="">ทุกประเภทลา</option>
                      {leaveTypes.map((leaveType) => <option key={leaveType.id} value={leaveType.id}>{leaveType.name}</option>)}
                    </select>
                    <select className="h-10 rounded-md border border-gray-300 px-3" value={leaveStatus} onChange={(event) => setLeaveStatus(event.target.value)}>
                      <option value="">ทุกสถานะ</option>
                      <option value="pending">pending</option>
                      <option value="approved">approved</option>
                      <option value="rejected">rejected</option>
                      <option value="cancelled">cancelled</option>
                    </select>
                    <Input type="date" value={leaveDateFrom} onChange={(event) => setLeaveDateFrom(event.target.value)} />
                    <Input type="date" value={leaveDateTo} onChange={(event) => setLeaveDateTo(event.target.value)} />
                    {canEditAttendance ? (
                      <Button className="lg:ml-auto" onClick={() => setCreateLeaveOpen(true)}>
                        <Plus className="h-4 w-4" />
                        ขอลา
                      </Button>
                    ) : null}
                  </div>
                  <div className="overflow-x-auto rounded-lg border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>เลขที่คำขอ</TableHead>
                          <TableHead>พนักงาน</TableHead>
                          <TableHead>ประเภทลา</TableHead>
                          <TableHead>วันที่ลา</TableHead>
                          <TableHead>จำนวนวัน</TableHead>
                          <TableHead>เหตุผล</TableHead>
                          <TableHead>สถานะ</TableHead>
                          <TableHead>Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {leaveRequests.map((request) => (
                          <TableRow key={request.id}>
                            <TableCell className="font-mono">{request.request_number}</TableCell>
                            <TableCell>{request.employee_name}</TableCell>
                            <TableCell>{request.leave_type_name}</TableCell>
                            <TableCell>{formatThaiDate(request.start_date)} - {formatThaiDate(request.end_date)}</TableCell>
                            <TableCell>{request.days_requested}</TableCell>
                            <TableCell>{request.reason || "-"}</TableCell>
                            <TableCell><span className={`rounded-full px-2 py-1 text-xs font-medium ${leaveStatusVariant(request.status)}`}>{request.status}</span></TableCell>
                            <TableCell>
                              <div className="flex gap-2">
                                {request.status === "pending" ? (
                                  <>
                                    <Button size="sm" onClick={() => { setSelectedLeaveRequest(request); setReviewLeaveOpen(true); }}>อนุมัติ</Button>
                                    <Button variant="outline" size="sm" onClick={() => { setSelectedLeaveRequest(request); setReviewLeaveOpen(true); }}>ปฏิเสธ</Button>
                                    <Button variant="secondary" size="sm" onClick={() => hrApi.cancelLeaveRequest(request.id).then(() => queryClient.invalidateQueries({ queryKey: ["hr"] }))}>ยกเลิก</Button>
                                  </>
                                ) : (
                                  <Button variant="outline" size="sm" onClick={() => { setSelectedLeaveRequest(request); setReviewLeaveOpen(true); }}>ดูรายละเอียด</Button>
                                )}
                              </div>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="balances">
              <Card>
                <CardContent className="space-y-4 p-4">
                  <div className="flex flex-col gap-3 lg:flex-row">
                    <select className="h-10 rounded-md border border-gray-300 px-3" value={balanceEmployeeId} onChange={(event) => setBalanceEmployeeId(event.target.value)}>
                      <option value="">เลือกพนักงาน</option>
                      {allEmployees.map((employee) => (
                        <option key={employee.id} value={employee.id}>
                          {employee.employee_code} • {[employee.first_name, employee.last_name].join(" ")}
                        </option>
                      ))}
                    </select>
                    <Input type="number" value={balanceYear} onChange={(event) => setBalanceYear(event.target.value)} />
                    {canEditAttendance ? (
                      <Button className="lg:ml-auto" onClick={() => initializeBalancesMutation.mutate()}>
                        กำหนดโควต้า
                      </Button>
                    ) : null}
                  </div>
                  <div className="overflow-x-auto rounded-lg border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>ประเภทลา</TableHead>
                          <TableHead>สิทธิ์</TableHead>
                          <TableHead>ใช้แล้ว</TableHead>
                          <TableHead>คงเหลือ</TableHead>
                          <TableHead>ยกมา</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {leaveBalances.map((balance) => (
                          <TableRow key={balance.id}>
                            <TableCell>{balance.leave_type_name}</TableCell>
                            <TableCell>{balance.entitled_days}</TableCell>
                            <TableCell>{balance.used_days}</TableCell>
                            <TableCell>{balance.remaining_days}</TableCell>
                            <TableCell>{balance.carry_over_days}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="types">
              <Card>
                <CardContent className="space-y-4 p-4">
                  <div className="flex justify-end">
                    {canEditAttendance ? (
                      <Button onClick={() => void quickCreateLeaveType()}>
                        <Plus className="h-4 w-4" />
                        เพิ่มประเภทลา
                      </Button>
                    ) : null}
                  </div>
                  <div className="overflow-x-auto rounded-lg border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Code</TableHead>
                          <TableHead>ชื่อ</TableHead>
                          <TableHead>สิทธิ์/ปี</TableHead>
                          <TableHead>คงค้าง</TableHead>
                          <TableHead>จ่ายค่าจ้าง</TableHead>
                          <TableHead>ประเภท</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {leaveTypes.map((leaveType) => (
                          <TableRow key={leaveType.id}>
                            <TableCell className="font-mono">{leaveType.code}</TableCell>
                            <TableCell>{leaveType.name}</TableCell>
                            <TableCell>{leaveType.days_per_year}</TableCell>
                            <TableCell>{leaveType.carry_over ? `ได้ (${leaveType.max_carry_over})` : "ไม่ได้"}</TableCell>
                            <TableCell>{leaveType.is_paid ? "Paid" : "Unpaid"}</TableCell>
                            <TableCell>{leaveType.is_system ? "System" : "Custom"}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </TabsContent>
      </Tabs>

      <CreateEmployeeDialog
        open={createEmployeeOpen}
        onOpenChange={setCreateEmployeeOpen}
        branches={branches}
        departments={departments}
        positions={positionsQuery.data ?? []}
        users={users}
        onSuccess={() => queryClient.invalidateQueries({ queryKey: ["hr"] })}
      />
      <EmployeeDetailDialog
        open={Boolean(employeeDetailId)}
        onOpenChange={(isOpen) => !isOpen && setEmployeeDetailId(null)}
        employeeId={employeeDetailId}
        branches={branches}
        departments={departments}
        positions={positionsQuery.data ?? []}
        users={users}
      />
      <CreatePayrollDialog
        open={createPayrollOpen}
        onOpenChange={setCreatePayrollOpen}
        branches={branches}
        onCreated={(runId) => {
          setRunDetailId(runId);
          return queryClient.invalidateQueries({ queryKey: ["hr"] });
        }}
      />
      <PayrollRunDetailDialog open={Boolean(runDetailId)} onOpenChange={(isOpen) => !isOpen && setRunDetailId(null)} runId={runDetailId} />
      <RecordAttendanceDialog open={recordAttendanceOpen} onOpenChange={setRecordAttendanceOpen} employees={allEmployees} />
      <CreateLeaveRequestDialog open={createLeaveOpen} onOpenChange={setCreateLeaveOpen} employees={allEmployees} leaveTypes={leaveTypes} year={Number(balanceYear)} />
      <ReviewLeaveDialog open={reviewLeaveOpen} onOpenChange={(isOpen) => !isOpen && setReviewLeaveOpen(false)} leaveRequest={selectedLeaveRequest} />
    </div>
  );
}
