import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, UserMinus } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import { hrApi } from "@/lib/hrApi";
import type { BranchDetail, UserDetail } from "@/types/admin";
import type { Department, Employee, PayrollItem, Position } from "@/types/hr";

type Props = {
  employeeId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  branches: BranchDetail[];
  departments: Department[];
  positions: Position[];
  users: UserDetail[];
};

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(value || 0);
}

type HistoryRow = PayrollItem & { run_id: string; run_number: string; pay_date: string };

export default function EmployeeDetailDialog({
  employeeId,
  open,
  onOpenChange,
  branches,
  departments,
  positions,
  users
}: Props): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [terminationDate, setTerminationDate] = useState(new Date().toISOString().slice(0, 10));
  const [form, setForm] = useState<Employee | null>(null);

  const employeeQuery = useQuery({
    queryKey: ["hr", "employee", employeeId],
    enabled: open && Boolean(employeeId),
    queryFn: async () => (await hrApi.getEmployee(employeeId ?? "")).data.data
  });

  const historyQuery = useQuery({
    queryKey: ["hr", "employee-history", employeeId],
    enabled: open && Boolean(employeeId),
    queryFn: async () => {
      const runsResponse = await hrApi.listPayrollRuns({ page: 1, limit: 20 });
      const detailed = await Promise.all(
        runsResponse.data.data
          .filter((run) => run.status === "completed")
          .map(async (run) => (await hrApi.getPayrollRun(run.id)).data.data)
      );
      return detailed.flatMap((run) =>
        (run.items ?? [])
          .filter((item) => item.employee_id === employeeId)
          .map((item) => ({ ...item, run_id: run.id, run_number: run.run_number, pay_date: run.pay_date }))
      ) as HistoryRow[];
    }
  });

  const employee = employeeQuery.data as Employee | undefined;

  useEffect(() => {
    setForm(employee ?? null);
  }, [employee]);

  const filteredPositions = useMemo(
    () => positions.filter((position) => !form?.department_id || position.department_id === form.department_id),
    [positions, form?.department_id]
  );

  const updateMutation = useMutation({
    mutationFn: async () =>
      hrApi.updateEmployee(employeeId ?? "", {
        title: form?.title || null,
        first_name: form?.first_name,
        last_name: form?.last_name,
        first_name_en: form?.first_name_en || null,
        last_name_en: form?.last_name_en || null,
        date_of_birth: form?.date_of_birth || null,
        gender: form?.gender || null,
        national_id: form?.national_id || null,
        phone: form?.phone || null,
        email: form?.email || null,
        branch_id: form?.branch_id,
        department_id: form?.department_id || null,
        position_id: form?.position_id || null,
        hire_date: form?.hire_date,
        employment_type: form?.employment_type,
        user_id: form?.user_id || null,
        base_salary: Number(form?.base_salary || 0),
        salary_type: form?.salary_type,
        bank_name: form?.bank_name || null,
        bank_account: form?.bank_account || null,
        tax_id: form?.national_id || null,
        sso_registered: form?.sso_registered
      }),
    onSuccess: async () => {
      toast({ title: "บันทึกข้อมูลพนักงานแล้ว" });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["hr"] }),
        queryClient.invalidateQueries({ queryKey: ["hr", "employee", employeeId] })
      ]);
    },
    onError: (error: Error) => {
      toast({ title: "บันทึกไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const terminateMutation = useMutation({
    mutationFn: async () => hrApi.terminateEmployee(employeeId ?? "", terminationDate),
    onSuccess: async () => {
      toast({ title: "บันทึกการออกจากงานแล้ว" });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["hr"] }),
        queryClient.invalidateQueries({ queryKey: ["hr", "employee", employeeId] })
      ]);
    },
    onError: (error: Error) => {
      toast({ title: "ไม่สามารถออกจากงานได้", description: error.message, variant: "destructive" });
    }
  });

  async function downloadPayslip(runId: string, empId: string, employeeCode: string): Promise<void> {
    const response = await hrApi.downloadPayslip(runId, empId);
    const blob = new Blob([response.data], { type: String(response.headers["content-type"] || "application/pdf") });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `payslip_${employeeCode}_${runId}.pdf`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function updateEmployeeField<K extends keyof Employee>(field: K, value: Employee[K]): void {
    if (!form) {
      return;
    }
    setForm({ ...form, [field]: value });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{employee ? `${employee.employee_code} • ${employee.first_name} ${employee.last_name}` : "ข้อมูลพนักงาน"}</DialogTitle>
        </DialogHeader>

        {form ? (
          <Tabs defaultValue="personal">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="personal">ข้อมูลส่วนตัว</TabsTrigger>
              <TabsTrigger value="employment">การจ้างงาน</TabsTrigger>
              <TabsTrigger value="history">ประวัติเงินเดือน</TabsTrigger>
            </TabsList>

            <TabsContent value="personal" className="grid gap-4 md:grid-cols-2">
              <Field label="คำนำหน้า"><Input value={form.title ?? ""} onChange={(event) => updateEmployeeField("title", event.target.value)} /></Field>
              <Field label="เพศ"><Input value={form.gender ?? ""} onChange={(event) => updateEmployeeField("gender", event.target.value)} /></Field>
              <Field label="ชื่อ"><Input value={form.first_name} onChange={(event) => updateEmployeeField("first_name", event.target.value)} /></Field>
              <Field label="นามสกุล"><Input value={form.last_name} onChange={(event) => updateEmployeeField("last_name", event.target.value)} /></Field>
              <Field label="วันเกิด"><Input type="date" value={form.date_of_birth ?? ""} onChange={(event) => updateEmployeeField("date_of_birth", event.target.value)} /></Field>
              <Field label="เลขบัตรประชาชน"><Input value={form.national_id ?? ""} onChange={(event) => updateEmployeeField("national_id", event.target.value)} /></Field>
              <Field label="เบอร์โทร"><Input value={form.phone ?? ""} onChange={(event) => updateEmployeeField("phone", event.target.value)} /></Field>
              <Field label="อีเมล"><Input value={form.email ?? ""} onChange={(event) => updateEmployeeField("email", event.target.value)} /></Field>
            </TabsContent>

            <TabsContent value="employment" className="space-y-5">
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="สาขา">
                  <select className="h-10 w-full rounded-md border border-gray-300 px-3" value={form.branch_id} onChange={(event) => updateEmployeeField("branch_id", event.target.value)}>
                    {branches.map((branch) => (
                      <option key={branch.id} value={branch.id}>{branch.name}</option>
                    ))}
                  </select>
                </Field>
                <Field label="แผนก">
                  <select className="h-10 w-full rounded-md border border-gray-300 px-3" value={form.department_id ?? ""} onChange={(event) => updateEmployeeField("department_id", event.target.value || null)}>
                    <option value="">-</option>
                    {departments.map((department) => (
                      <option key={department.id} value={department.id}>{department.name}</option>
                    ))}
                  </select>
                </Field>
                <Field label="ตำแหน่ง">
                  <select className="h-10 w-full rounded-md border border-gray-300 px-3" value={form.position_id ?? ""} onChange={(event) => updateEmployeeField("position_id", event.target.value || null)}>
                    <option value="">-</option>
                    {filteredPositions.map((position) => (
                      <option key={position.id} value={position.id}>{position.name}</option>
                    ))}
                  </select>
                </Field>
                <Field label="ผู้ใช้ระบบ">
                  <select className="h-10 w-full rounded-md border border-gray-300 px-3" value={form.user_id ?? ""} onChange={(event) => updateEmployeeField("user_id", event.target.value || null)}>
                    <option value="">-</option>
                    {users.map((user) => (
                      <option key={user.id} value={user.id}>{user.display_name || user.username}</option>
                    ))}
                  </select>
                </Field>
                <Field label="วันที่เข้างาน"><Input type="date" value={form.hire_date} onChange={(event) => updateEmployeeField("hire_date", event.target.value)} /></Field>
                <Field label="ประเภทการจ้างงาน"><Input value={form.employment_type} onChange={(event) => updateEmployeeField("employment_type", event.target.value as Employee["employment_type"])} /></Field>
                <Field label="เงินเดือน"><Input type="number" value={String(form.base_salary)} onChange={(event) => updateEmployeeField("base_salary", Number(event.target.value))} /></Field>
                <Field label="เลขบัญชีธนาคาร"><Input value={form.bank_account ?? ""} onChange={(event) => updateEmployeeField("bank_account", event.target.value)} /></Field>
              </div>

              <div className="rounded-lg border border-red-200 bg-red-50 p-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-end">
                  <div className="flex-1 space-y-2">
                    <Label>วันที่ออกจากงาน</Label>
                    <Input type="date" value={terminationDate} onChange={(event) => setTerminationDate(event.target.value)} />
                  </div>
                  <Button variant="destructive" onClick={() => terminateMutation.mutate()} disabled={terminateMutation.isPending}>
                    <UserMinus className="h-4 w-4" />
                    ออกจากงาน
                  </Button>
                </div>
              </div>
            </TabsContent>

            <TabsContent value="history">
              <div className="overflow-x-auto rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>งวด</TableHead>
                      <TableHead>รายได้</TableHead>
                      <TableHead>SSO</TableHead>
                      <TableHead>PIT</TableHead>
                      <TableHead>สุทธิ</TableHead>
                      <TableHead>สลิป</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(historyQuery.data ?? []).map((item) => (
                      <TableRow key={`${item.id}-${item.run_number}`}>
                        <TableCell>{item.run_number}</TableCell>
                        <TableCell>{formatCurrency(item.earnings_total)}</TableCell>
                        <TableCell>{formatCurrency(item.sso_employee)}</TableCell>
                        <TableCell>{formatCurrency(item.pit_withheld)}</TableCell>
                        <TableCell className="font-semibold text-blue-700">{formatCurrency(item.net_pay)}</TableCell>
                        <TableCell>
                          <Button variant="outline" size="sm" onClick={() => void downloadPayslip(item.run_id, item.employee_id, item.employee_code)}>
                            <Download className="h-4 w-4" />
                            Download
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </TabsContent>
          </Tabs>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>ปิด</Button>
          <Button onClick={() => updateMutation.mutate()} disabled={updateMutation.isPending}>บันทึก</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }): JSX.Element {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
