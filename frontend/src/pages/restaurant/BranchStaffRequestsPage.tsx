import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardList, Plus, UserPlus } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/ui/use-toast";
import { userAccessApi } from "@/lib/adminApi";
import { authApi } from "@/lib/api";
import { formatDateTimeTh } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth.store";
import type { UserAccessRequestStatus } from "@/types/admin";

const statusLabels: Record<UserAccessRequestStatus, string> = {
  pending: "รออนุมัติ",
  approved: "อนุมัติแล้ว รอเปิดบัญชี",
  activated: "เปิดใช้งานแล้ว",
  rejected: "ปฏิเสธ",
  cancelled: "ยกเลิก"
};

const emptyForm = {
  first_name: "",
  last_name: "",
  username: "",
  password: "",
  confirm_password: "",
  employee_code: "",
  email: "",
  phone: "",
  requested_role_id: "",
  request_note: ""
};

export default function BranchStaffRequestsPage(): JSX.Element {
  const { brandSlug = "", branchCode } = useParams<{ brandSlug?: string; branchCode?: string }>();
  const branchId = useAuthStore((state) => state.branchId);
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<UserAccessRequestStatus | "">("");
  const [form, setForm] = useState(emptyForm);

  const branchesQuery = useQuery({
    queryKey: ["system", "my-branches"],
    queryFn: async () => (await authApi.myBranches()).data.data
  });
  const rolesQuery = useQuery({
    queryKey: ["branch", "branch-assignable-roles"],
    queryFn: async () => (await userAccessApi.assignableRoles()).data.data
  });
  const requestsQuery = useQuery({
    queryKey: ["branch", "user-access-requests", brandSlug, branchId, statusFilter],
    queryFn: async () =>
      (
        await userAccessApi.mine({
          brand_slug: brandSlug,
          status: statusFilter || undefined,
          limit: 100
        })
      ).data.data,
    enabled: Boolean(branchId)
  });

  const currentBranch = branchesQuery.data?.find((branch) => branch.branch_id === branchId) ?? null;
  const routeBranchMismatch = Boolean(
    branchCode && currentBranch && currentBranch.branch_code.toLowerCase() !== branchCode.toLowerCase()
  );
  const rows = requestsQuery.data ?? [];
  const roles = rolesQuery.data ?? [];

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!form.first_name.trim() || !form.last_name.trim()) {
        throw new Error("กรุณากรอกชื่อและนามสกุล");
      }
      if (!form.email.trim() && !form.phone.trim()) {
        throw new Error("กรุณากรอก email หรือเบอร์โทรศัพท์อย่างน้อยหนึ่งรายการ");
      }
      if (form.username.trim().length < 3) {
        throw new Error("Username ต้องมีอย่างน้อย 3 ตัวอักษร");
      }
      if (form.password.length < 8 && form.password !== "123456") {
        throw new Error("Password ต้องมีอย่างน้อย 8 ตัวอักษร (ช่วงพัฒนาใช้ 123456 ได้)");
      }
      if (form.password !== form.confirm_password) {
        throw new Error("กรุณายืนยัน Password ให้ตรงกัน");
      }
      if (!form.requested_role_id) throw new Error("กรุณาเลือกบทบาท");
      return userAccessApi.create({
        brand_slug: brandSlug,
        username: form.username.trim(),
        password: form.password,
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        employee_code: form.employee_code.trim() || null,
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
        requested_role_id: form.requested_role_id,
        request_note: form.request_note.trim() || null
      });
    },
    onSuccess: async () => {
      setDialogOpen(false);
      setForm(emptyForm);
      await queryClient.invalidateQueries({ queryKey: ["branch", "user-access-requests"] });
      toast({ title: "ส่งคำขอให้แอดมินแล้ว" });
    },
    onError: (error: Error) => {
      toast({ title: "ส่งคำขอไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const cancelMutation = useMutation({
    mutationFn: async (requestId: string) => userAccessApi.cancel(requestId, brandSlug),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["branch", "user-access-requests"] });
      toast({ title: "ยกเลิกคำขอแล้ว" });
    },
    onError: (error: Error) => {
      toast({ title: "ยกเลิกไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  if (routeBranchMismatch) {
    return (
      <Card className="mx-auto mt-10 max-w-xl border-red-200">
        <CardContent className="space-y-3 p-6 text-center">
          <p className="font-semibold text-red-700">สาขาใน URL ไม่ตรงกับสาขาที่เข้าสู่ระบบ</p>
          <p className="text-sm text-gray-500">กรุณาสลับสาขาหรือกลับไปหน้าร้านของสาขาปัจจุบัน</p>
          <Button asChild><Link to={`/store/${brandSlug}/staff`}>เปิดหน้าสาขาปัจจุบัน</Link></Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium uppercase tracking-wide text-slate-500">{brandSlug}</p>
          <h1 className="text-2xl font-bold text-slate-950">พนักงานประจำสาขา</h1>
          <p className="text-sm text-slate-500">
            {currentBranch ? `${currentBranch.branch_name} (${currentBranch.branch_code})` : "กำลังโหลดข้อมูลสาขา"}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" asChild><Link to={`/store/${brandSlug}/orders`}>กลับหน้าขาย</Link></Button>
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="mr-2 h-4 w-4" /> ขอเพิ่มพนักงาน
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>คำขอของสาขา</CardTitle>
          <select
            className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as UserAccessRequestStatus | "")}
          >
            <option value="">ทุกสถานะ</option>
            {Object.entries(statusLabels).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </CardHeader>
        <CardContent>
          {requestsQuery.isLoading ? (
            <div className="space-y-3"><Skeleton className="h-12" /><Skeleton className="h-12" /></div>
          ) : rows.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>พนักงาน</TableHead>
                  <TableHead>ติดต่อ</TableHead>
                  <TableHead>บทบาท</TableHead>
                  <TableHead>วันที่ส่ง</TableHead>
                  <TableHead>สถานะ</TableHead>
                  <TableHead>หมายเหตุแอดมิน</TableHead>
                  <TableHead className="text-right">จัดการ</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell>
                      <p className="font-medium">{row.first_name} {row.last_name}</p>
                      <p className="text-xs text-gray-500">
                        {row.requested_username || row.activated_username || row.employee_code || "-"}
                      </p>
                    </TableCell>
                    <TableCell>{row.email || row.phone || "-"}</TableCell>
                    <TableCell>{row.approved_role_name || row.requested_role_name}</TableCell>
                    <TableCell>{formatDateTimeTh(row.requested_at)}</TableCell>
                    <TableCell><Badge variant={row.status === "activated" ? "success" : "outline"}>{statusLabels[row.status]}</Badge></TableCell>
                    <TableCell>{row.review_note || "-"}</TableCell>
                    <TableCell className="text-right">
                      {row.status === "pending" ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            if (window.confirm("ยืนยันยกเลิกคำขอนี้หรือไม่")) cancelMutation.mutate(row.id);
                          }}
                        >
                          ยกเลิก
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="flex flex-col items-center py-14 text-gray-500">
              <ClipboardList className="mb-3 h-9 w-9" />
              <p>ยังไม่มีคำขอเพิ่มพนักงาน</p>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><UserPlus className="h-5 w-5" /> ขอเพิ่มพนักงาน</DialogTitle>
            <DialogDescription>บัญชีจะยังใช้งานไม่ได้จนกว่าแอดมินกลางจะอนุมัติ</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4">
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="ชื่อ *"><Input value={form.first_name} onChange={(event) => setForm((prev) => ({ ...prev, first_name: event.target.value }))} /></Field>
              <Field label="นามสกุล *"><Input value={form.last_name} onChange={(event) => setForm((prev) => ({ ...prev, last_name: event.target.value }))} /></Field>
            </div>
            <div className="rounded-xl border border-blue-100 bg-blue-50 p-4">
              <p className="mb-3 text-sm font-medium text-blue-950">ข้อมูลสำหรับเข้าสู่ระบบ</p>
              <div className="grid gap-4 md:grid-cols-3">
                <Field label="Username *"><Input autoComplete="off" value={form.username} onChange={(event) => setForm((prev) => ({ ...prev, username: event.target.value }))} /></Field>
                <Field label="Password *"><Input type="password" autoComplete="new-password" value={form.password} onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))} /></Field>
                <Field label="ยืนยัน Password *"><Input type="password" autoComplete="new-password" value={form.confirm_password} onChange={(event) => setForm((prev) => ({ ...prev, confirm_password: event.target.value }))} /></Field>
              </div>
              <p className="mt-2 text-xs text-blue-700">ระบบเก็บเฉพาะรหัสที่เข้ารหัสแล้ว พนักงานใช้ล็อกอินได้หลัง Center อนุมัติ (ช่วงพัฒนาใช้ 123456 ได้)</p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Email"><Input value={form.email} onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))} /></Field>
              <Field label="เบอร์โทรศัพท์"><Input value={form.phone} onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))} /></Field>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="รหัสพนักงาน"><Input value={form.employee_code} onChange={(event) => setForm((prev) => ({ ...prev, employee_code: event.target.value }))} /></Field>
              <Field label="บทบาท *">
                <select className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm" value={form.requested_role_id} onChange={(event) => setForm((prev) => ({ ...prev, requested_role_id: event.target.value }))}>
                  <option value="">เลือกบทบาท</option>
                  {roles.map((role) => <option key={role.id} value={role.id}>{role.name}</option>)}
                </select>
              </Field>
            </div>
            <Field label="หมายเหตุ">
              <textarea className="min-h-24 rounded-md border border-gray-200 px-3 py-2 text-sm" value={form.request_note} onChange={(event) => setForm((prev) => ({ ...prev, request_note: event.target.value }))} />
            </Field>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>ยกเลิก</Button>
            <Button onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>ส่งคำขอ</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }): JSX.Element {
  return <div className="grid gap-2"><Label>{label}</Label>{children}</div>;
}
