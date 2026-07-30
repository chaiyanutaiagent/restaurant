import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import { hrApi } from "@/lib/hrApi";
import type { BranchDetail, UserDetail } from "@/types/admin";
import type { Department, Position } from "@/types/hr";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  branches: BranchDetail[];
  departments: Department[];
  positions: Position[];
  users: UserDetail[];
  onSuccess: () => Promise<void> | void;
};

type FormState = {
  title: string;
  first_name: string;
  last_name: string;
  first_name_en: string;
  last_name_en: string;
  date_of_birth: string;
  gender: string;
  national_id: string;
  phone: string;
  email: string;
  employee_code: string;
  branch_id: string;
  department_id: string;
  position_id: string;
  hire_date: string;
  probation_end_date: string;
  employment_type: string;
  user_id: string;
  base_salary: string;
  salary_type: string;
  bank_name: string;
  bank_account: string;
  bank_account_name: string;
  tax_id: string;
  sso_number: string;
  sso_registered: boolean;
  pit_allowance_personal: string;
};

const EMPTY_FORM: FormState = {
  title: "นาย",
  first_name: "",
  last_name: "",
  first_name_en: "",
  last_name_en: "",
  date_of_birth: "",
  gender: "",
  national_id: "",
  phone: "",
  email: "",
  employee_code: "",
  branch_id: "",
  department_id: "",
  position_id: "",
  hire_date: new Date().toISOString().slice(0, 10),
  probation_end_date: "",
  employment_type: "fulltime",
  user_id: "",
  base_salary: "0",
  salary_type: "monthly",
  bank_name: "",
  bank_account: "",
  bank_account_name: "",
  tax_id: "",
  sso_number: "",
  sso_registered: true,
  pit_allowance_personal: "60000"
};

export default function CreateEmployeeDialog({
  open,
  onOpenChange,
  branches,
  departments,
  positions,
  users,
  onSuccess
}: Props): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("personal");
  const [form, setForm] = useState<FormState>(EMPTY_FORM);

  useEffect(() => {
    if (!open) {
      setForm(EMPTY_FORM);
      setTab("personal");
      return;
    }
    setForm((prev) => ({
      ...prev,
      branch_id: prev.branch_id || branches.find((branch) => branch.is_active)?.id || "",
      employee_code: prev.employee_code || `EMP-${String(Math.max(users.length + 1, 1)).padStart(3, "0")}`
    }));
  }, [open, branches, users.length]);

  const filteredPositions = useMemo(
    () => positions.filter((position) => !form.department_id || position.department_id === form.department_id),
    [positions, form.department_id]
  );

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!form.first_name.trim() || !form.last_name.trim() || !form.employee_code.trim() || !form.branch_id || !form.hire_date) {
        throw new Error("กรุณากรอกข้อมูลจำเป็นให้ครบ");
      }
      return hrApi.createEmployee({
        employee_code: form.employee_code,
        title: form.title || null,
        first_name: form.first_name,
        last_name: form.last_name,
        first_name_en: form.first_name_en || null,
        last_name_en: form.last_name_en || null,
        date_of_birth: form.date_of_birth || null,
        gender: form.gender || null,
        national_id: form.national_id || null,
        phone: form.phone || null,
        email: form.email || null,
        hire_date: form.hire_date,
        branch_id: form.branch_id,
        department_id: form.department_id || null,
        position_id: form.position_id || null,
        probation_end_date: form.probation_end_date || null,
        employment_type: form.employment_type,
        user_id: form.user_id || null,
        base_salary: Number(form.base_salary || 0),
        salary_type: form.salary_type,
        bank_name: form.bank_name || null,
        bank_account: form.bank_account || null,
        bank_account_name: form.bank_account_name || null,
        tax_id: form.tax_id || null,
        sso_number: form.sso_number || null,
        sso_registered: form.sso_registered,
        pit_allowance_personal: Number(form.pit_allowance_personal || 60000),
        is_active: true
      });
    },
    onSuccess: async (response) => {
      toast({ title: `เพิ่มพนักงานแล้ว: ${response.data.data.employee_code}` });
      onOpenChange(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["hr"] }),
        Promise.resolve(onSuccess())
      ]);
    },
    onError: (error: Error) => {
      toast({ title: "เพิ่มพนักงานไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  function updateField<K extends keyof FormState>(field: K, value: FormState[K]): void {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>เพิ่มพนักงาน</DialogTitle>
        </DialogHeader>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="personal">ข้อมูลส่วนตัว</TabsTrigger>
            <TabsTrigger value="employment">การจ้างงาน</TabsTrigger>
            <TabsTrigger value="payroll">เงินเดือนและการเงิน</TabsTrigger>
          </TabsList>

          <TabsContent value="personal" className="grid gap-4 md:grid-cols-2">
            <Field label="คำนำหน้า">
              <select className="h-10 w-full rounded-md border border-gray-300 px-3" value={form.title} onChange={(event) => updateField("title", event.target.value)}>
                <option value="นาย">นาย</option>
                <option value="นาง">นาง</option>
                <option value="นางสาว">นางสาว</option>
                <option value="อื่นๆ">อื่นๆ</option>
              </select>
            </Field>
            <Field label="เพศ">
              <select className="h-10 w-full rounded-md border border-gray-300 px-3" value={form.gender} onChange={(event) => updateField("gender", event.target.value)}>
                <option value="">-</option>
                <option value="male">ชาย</option>
                <option value="female">หญิง</option>
                <option value="other">อื่นๆ</option>
              </select>
            </Field>
            <Field label="ชื่อ *"><Input value={form.first_name} onChange={(event) => updateField("first_name", event.target.value)} /></Field>
            <Field label="นามสกุล *"><Input value={form.last_name} onChange={(event) => updateField("last_name", event.target.value)} /></Field>
            <Field label="ชื่ออังกฤษ"><Input value={form.first_name_en} onChange={(event) => updateField("first_name_en", event.target.value)} /></Field>
            <Field label="นามสกุลอังกฤษ"><Input value={form.last_name_en} onChange={(event) => updateField("last_name_en", event.target.value)} /></Field>
            <Field label="วันเกิด"><Input type="date" value={form.date_of_birth} onChange={(event) => updateField("date_of_birth", event.target.value)} /></Field>
            <Field label="เลขบัตรประชาชน">
              <Input value={form.national_id} maxLength={13} onChange={(event) => updateField("national_id", event.target.value.replace(/\D/g, ""))} />
            </Field>
            <Field label="เบอร์โทร"><Input value={form.phone} onChange={(event) => updateField("phone", event.target.value)} /></Field>
            <Field label="อีเมล"><Input value={form.email} onChange={(event) => updateField("email", event.target.value)} /></Field>
          </TabsContent>

          <TabsContent value="employment" className="grid gap-4 md:grid-cols-2">
            <Field label="รหัสพนักงาน *"><Input value={form.employee_code} onChange={(event) => updateField("employee_code", event.target.value)} /></Field>
            <Field label="ประเภทการจ้างงาน">
              <select className="h-10 w-full rounded-md border border-gray-300 px-3" value={form.employment_type} onChange={(event) => updateField("employment_type", event.target.value)}>
                <option value="fulltime">Full-time</option>
                <option value="parttime">Part-time</option>
                <option value="contract">Contract</option>
                <option value="daily">Daily</option>
              </select>
            </Field>
            <Field label="สาขา *">
              <select className="h-10 w-full rounded-md border border-gray-300 px-3" value={form.branch_id} onChange={(event) => updateField("branch_id", event.target.value)}>
                <option value="">เลือกสาขา</option>
                {branches.map((branch) => (
                  <option key={branch.id} value={branch.id}>{branch.name}</option>
                ))}
              </select>
            </Field>
            <Field label="แผนก">
              <select className="h-10 w-full rounded-md border border-gray-300 px-3" value={form.department_id} onChange={(event) => updateField("department_id", event.target.value)}>
                <option value="">-</option>
                {departments.map((department) => (
                  <option key={department.id} value={department.id}>{department.code} • {department.name}</option>
                ))}
              </select>
            </Field>
            <Field label="ตำแหน่ง">
              <select className="h-10 w-full rounded-md border border-gray-300 px-3" value={form.position_id} onChange={(event) => updateField("position_id", event.target.value)}>
                <option value="">-</option>
                {filteredPositions.map((position) => (
                  <option key={position.id} value={position.id}>{position.code} • {position.name}</option>
                ))}
              </select>
            </Field>
            <Field label="ผูกกับผู้ใช้ระบบ">
              <select className="h-10 w-full rounded-md border border-gray-300 px-3" value={form.user_id} onChange={(event) => updateField("user_id", event.target.value)}>
                <option value="">-</option>
                {users.map((user) => (
                  <option key={user.id} value={user.id}>{user.display_name || user.username}</option>
                ))}
              </select>
            </Field>
            <Field label="วันที่เข้างาน *"><Input type="date" value={form.hire_date} onChange={(event) => updateField("hire_date", event.target.value)} /></Field>
            <Field label="สิ้นสุดทดลองงาน"><Input type="date" value={form.probation_end_date} onChange={(event) => updateField("probation_end_date", event.target.value)} /></Field>
          </TabsContent>

          <TabsContent value="payroll" className="grid gap-4 md:grid-cols-2">
            <Field label="เงินเดือน *"><Input type="number" value={form.base_salary} onChange={(event) => updateField("base_salary", event.target.value)} /></Field>
            <Field label="ประเภทเงินเดือน">
              <select className="h-10 w-full rounded-md border border-gray-300 px-3" value={form.salary_type} onChange={(event) => updateField("salary_type", event.target.value)}>
                <option value="monthly">Monthly</option>
                <option value="daily">Daily</option>
                <option value="hourly">Hourly</option>
              </select>
            </Field>
            <Field label="ธนาคาร"><Input value={form.bank_name} onChange={(event) => updateField("bank_name", event.target.value)} /></Field>
            <Field label="เลขที่บัญชี"><Input value={form.bank_account} onChange={(event) => updateField("bank_account", event.target.value)} /></Field>
            <Field label="ชื่อบัญชี"><Input value={form.bank_account_name} onChange={(event) => updateField("bank_account_name", event.target.value)} /></Field>
            <Field label="Tax ID"><Input value={form.tax_id} onChange={(event) => updateField("tax_id", event.target.value)} /></Field>
            <Field label="เลขประกันสังคม"><Input value={form.sso_number} onChange={(event) => updateField("sso_number", event.target.value)} /></Field>
            <Field label="ค่าลดหย่อนส่วนตัว">
              <Input type="number" value={form.pit_allowance_personal} onChange={(event) => updateField("pit_allowance_personal", event.target.value)} />
            </Field>
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
              <input type="checkbox" checked={form.sso_registered} onChange={(event) => updateField("sso_registered", event.target.checked)} />
              ขึ้นทะเบียนประกันสังคมแล้ว
            </label>
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>ยกเลิก</Button>
          <Button onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
            {createMutation.isPending ? "กำลังบันทึก..." : "บันทึกพนักงาน"}
          </Button>
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
