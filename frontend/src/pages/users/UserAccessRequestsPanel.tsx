import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ClipboardList, Copy, RefreshCw, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { formatDateTimeTh } from "@/lib/utils";
import type {
  BranchDetail,
  UserAccessApprovalResult,
  UserAccessRequest,
  UserAccessRequestStatus
} from "@/types/admin";

const statusLabels: Record<UserAccessRequestStatus, string> = {
  pending: "รออนุมัติ",
  approved: "รอเปิดใช้งาน",
  activated: "เปิดใช้งานแล้ว",
  rejected: "ปฏิเสธ",
  cancelled: "ยกเลิก"
};

function statusVariant(status: UserAccessRequestStatus): "default" | "success" | "destructive" | "outline" {
  if (status === "activated") return "success";
  if (status === "rejected" || status === "cancelled") return "destructive";
  if (status === "approved") return "default";
  return "outline";
}

type UserAccessRequestsPanelProps = {
  branches?: BranchDetail[];
  brandSlug?: string;
};

export default function UserAccessRequestsPanel({
  branches = [],
  brandSlug
}: UserAccessRequestsPanelProps): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<UserAccessRequestStatus | "">("pending");
  const [branchFilter, setBranchFilter] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<UserAccessRequest | null>(null);
  const [approvedRoleId, setApprovedRoleId] = useState("");
  const [reviewNote, setReviewNote] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [invitationResult, setInvitationResult] = useState<UserAccessApprovalResult | null>(null);

  const requestsQuery = useQuery({
    queryKey: ["admin", "user-access-requests", brandSlug ?? "all", statusFilter, branchFilter, search],
    queryFn: async () =>
      (
        await userAccessApi.list({
          brand_slug: brandSlug,
          status: statusFilter || undefined,
          branch_id: branchFilter || undefined,
          search: search || undefined,
          limit: 100
        })
      ).data.data
  });
  const rolesQuery = useQuery({
    queryKey: ["admin", "branch-assignable-roles"],
    queryFn: async () => (await userAccessApi.assignableRoles()).data.data
  });

  const rows = requestsQuery.data ?? [];
  const roles = rolesQuery.data ?? [];
  const branchOptions = useMemo(() => {
    if (branches.length) return branches.map((branch) => ({ id: branch.id, name: branch.name }));
    return Array.from(
      new Map(rows.map((row) => [row.branch_id, { id: row.branch_id, name: row.branch_name }])).values()
    );
  }, [branches, rows]);
  const acceptUrl = useMemo(() => {
    if (!invitationResult?.invitation_id) return "";
    const params = new URLSearchParams({
      company_id: invitationResult.company_id,
      invitation_id: invitationResult.invitation_id
    });
    return `${window.location.origin}/accept-invitation?${params.toString()}`;
  }, [invitationResult]);

  useEffect(() => {
    if (!selected) return;
    setApprovedRoleId(selected.approved_role_id ?? selected.requested_role_id);
    setReviewNote(selected.review_note ?? "");
    setRejectReason("");
    setInvitationResult(null);
  }, [selected]);

  const refresh = async (): Promise<void> => {
    await queryClient.invalidateQueries({ queryKey: ["admin", "user-access-requests"] });
  };

  const approveMutation = useMutation({
    mutationFn: async () => {
      if (!selected || !approvedRoleId) throw new Error("กรุณาเลือกบทบาท");
      return (await userAccessApi.approve(selected.id, {
        approved_role_id: approvedRoleId,
        review_note: reviewNote || null
      })).data.data;
    },
    onSuccess: async (result) => {
      setInvitationResult(result);
      setSelected(result.request);
      await refresh();
      toast({ title: "อนุมัติและสร้างคำเชิญแล้ว" });
    },
    onError: (error: Error) => {
      toast({ title: "อนุมัติไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const rejectMutation = useMutation({
    mutationFn: async () => {
      if (!selected) throw new Error("ไม่พบคำขอ");
      if (!rejectReason.trim()) throw new Error("กรุณากรอกเหตุผลที่ปฏิเสธ");
      return (await userAccessApi.reject(selected.id, rejectReason.trim())).data.data;
    },
    onSuccess: async () => {
      setSelected(null);
      await refresh();
      toast({ title: "ปฏิเสธคำขอแล้ว" });
    },
    onError: (error: Error) => {
      toast({ title: "ปฏิเสธไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const resendMutation = useMutation({
    mutationFn: async () => {
      if (!selected) throw new Error("ไม่พบคำขอ");
      return (await userAccessApi.resend(selected.id)).data.data;
    },
    onSuccess: async (result) => {
      setInvitationResult(result);
      setSelected(result.request);
      await refresh();
      toast({ title: "ออกคำเชิญใหม่แล้ว" });
    },
    onError: (error: Error) => {
      toast({ title: "ส่งคำเชิญใหม่ไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const copyInvitation = async (): Promise<void> => {
    if (!invitationResult?.otp_code) return;
    await navigator.clipboard.writeText(`ลิงก์เปิดบัญชี: ${acceptUrl}\nOTP: ${invitationResult.otp_code}`);
    toast({ title: "คัดลอกลิงก์และ OTP แล้ว" });
  };

  return (
    <>
      <Card>
        <CardContent className="space-y-4 p-5">
          <div className="grid gap-3 md:grid-cols-[1.5fr_1fr_1fr_auto]">
            <Input
              placeholder="ค้นหาชื่อ email เบอร์โทร หรือรหัสพนักงาน"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <select
              className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm"
              value={branchFilter}
              onChange={(event) => setBranchFilter(event.target.value)}
            >
              <option value="">ทุกสาขา</option>
              {branchOptions.map((branch) => (
                <option key={branch.id} value={branch.id}>{branch.name}</option>
              ))}
            </select>
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
            <Button variant="outline" onClick={() => void refresh()}>
              <RefreshCw className="mr-2 h-4 w-4" /> รีเฟรช
            </Button>
          </div>

          {requestsQuery.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : rows.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>พนักงาน</TableHead>
                  <TableHead>สาขา</TableHead>
                  <TableHead>บทบาท</TableHead>
                  <TableHead>ผู้ขอ</TableHead>
                  <TableHead>วันที่ขอ</TableHead>
                  <TableHead>สถานะ</TableHead>
                  <TableHead className="text-right">จัดการ</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell>
                      <p className="font-medium text-gray-900">{row.first_name} {row.last_name}</p>
                      <p className="text-xs text-gray-500">{row.email || row.phone || row.employee_code || "-"}</p>
                    </TableCell>
                    <TableCell>
                      <p>{row.branch_name}</p>
                      {!brandSlug && row.brand_name ? (
                        <p className="text-xs text-gray-500">{row.brand_name}</p>
                      ) : null}
                    </TableCell>
                    <TableCell>{row.approved_role_name || row.requested_role_name}</TableCell>
                    <TableCell>{row.requester_name}</TableCell>
                    <TableCell>{formatDateTimeTh(row.requested_at)}</TableCell>
                    <TableCell>
                      <Badge variant={statusVariant(row.status)}>{statusLabels[row.status]}</Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="outline" size="sm" onClick={() => setSelected(row)}>
                        ตรวจสอบ
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="flex flex-col items-center py-14 text-center text-gray-500">
              <ClipboardList className="mb-3 h-9 w-9" />
              <p className="font-medium">ไม่มีคำขอที่ตรงกับเงื่อนไข</p>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>ตรวจสอบคำขอผู้ใช้สาขา</DialogTitle>
            <DialogDescription>
              {selected ? `${selected.first_name} ${selected.last_name} — ${selected.branch_name}` : ""}
            </DialogDescription>
          </DialogHeader>
          {selected ? (
            <div className="space-y-4">
              <div className="grid gap-3 rounded-xl bg-gray-50 p-4 text-sm md:grid-cols-2">
                <p><span className="text-gray-500">Email:</span> {selected.email || "-"}</p>
                <p><span className="text-gray-500">โทร:</span> {selected.phone || "-"}</p>
                <p><span className="text-gray-500">รหัสพนักงาน:</span> {selected.employee_code || "-"}</p>
                <p><span className="text-gray-500">บทบาทที่ขอ:</span> {selected.requested_role_name}</p>
                <p><span className="text-gray-500">Username:</span> {selected.requested_username || selected.activated_username || "-"}</p>
                <p className="md:col-span-2"><span className="text-gray-500">หมายเหตุ:</span> {selected.request_note || "-"}</p>
              </div>

              {selected.status === "pending" ? (
                <>
                  <div className="grid gap-2">
                    <Label>บทบาทที่อนุมัติ</Label>
                    <select
                      className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm"
                      value={approvedRoleId}
                      onChange={(event) => setApprovedRoleId(event.target.value)}
                    >
                      <option value="">เลือกบทบาท</option>
                      {roles.map((role) => (
                        <option key={role.id} value={role.id}>{role.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="grid gap-2">
                    <Label>หมายเหตุผู้ตรวจ</Label>
                    <Input value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} />
                  </div>
                  <div className="grid gap-2 rounded-xl border border-red-100 bg-red-50 p-4">
                    <Label>เหตุผลกรณีปฏิเสธ</Label>
                    <Input value={rejectReason} onChange={(event) => setRejectReason(event.target.value)} />
                  </div>
                </>
              ) : (
                <div className="rounded-xl border p-4 text-sm">
                  <p>สถานะ: <strong>{statusLabels[selected.status]}</strong></p>
                  <p>ผู้ตรวจ: {selected.reviewer_name || "-"}</p>
                  <p>หมายเหตุ: {selected.review_note || "-"}</p>
                  {selected.activated_username ? <p>บัญชี: {selected.activated_username}</p> : null}
                </div>
              )}

              {invitationResult?.activation_mode === "activated" ? (
                <div className="space-y-2 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                  <p className="font-medium text-emerald-900">อนุมัติและเปิดใช้งานบัญชีแล้ว</p>
                  <p className="text-sm text-emerald-800">
                    Username: <strong>{invitationResult.created_username || selected.requested_username}</strong>
                  </p>
                  <p className="text-xs text-emerald-700">พนักงานสามารถล็อกอินด้วย Password ที่กำหนดไว้ตอนส่งคำขอได้ทันที</p>
                </div>
              ) : null}

              {invitationResult?.activation_mode === "invitation" ? (
                <div className="space-y-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                  <p className="font-medium text-emerald-900">คำขอเดิมไม่มีข้อมูลเข้าสู่ระบบ กรุณาส่งคำเชิญให้พนักงาน</p>
                  <Input readOnly value={acceptUrl} />
                  <div className="flex items-center justify-between rounded-lg bg-white px-4 py-3">
                    <code className="text-xl font-bold tracking-[0.2em] text-emerald-700">
                      {invitationResult.otp_code || "-"}
                    </code>
                    <Button variant="outline" size="sm" onClick={() => void copyInvitation()}>
                      <Copy className="mr-2 h-4 w-4" /> คัดลอก
                    </Button>
                  </div>
                  {invitationResult.expires_at ? (
                    <p className="text-xs text-emerald-800">หมดอายุ {formatDateTimeTh(invitationResult.expires_at)}</p>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}
          <DialogFooter className="gap-2">
            {selected?.status === "pending" ? (
              <>
                <Button
                  variant="destructive"
                  onClick={() => rejectMutation.mutate()}
                  disabled={rejectMutation.isPending}
                >
                  <XCircle className="mr-2 h-4 w-4" /> ปฏิเสธ
                </Button>
                <Button onClick={() => approveMutation.mutate()} disabled={approveMutation.isPending}>
                  <CheckCircle2 className="mr-2 h-4 w-4" /> อนุมัติ
                </Button>
              </>
            ) : null}
            {selected?.status === "approved" ? (
              <Button onClick={() => resendMutation.mutate()} disabled={resendMutation.isPending}>
                <RefreshCw className="mr-2 h-4 w-4" /> ออกคำเชิญใหม่
              </Button>
            ) : null}
            <Button variant="outline" onClick={() => setSelected(null)}>ปิด</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
