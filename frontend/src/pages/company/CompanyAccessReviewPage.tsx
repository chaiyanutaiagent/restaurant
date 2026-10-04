import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, KeyRound, RefreshCw, ShieldCheck, UserCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import CompanyStatePanel from "@/components/company/CompanyStatePanel";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { companyAccessApi, userApi } from "@/lib/adminApi";
import { companyRequestState, formatCompanyDateTime } from "@/lib/companyPresentation";
import type { AccessReviewOutcome, CompanyAccessReviewUser } from "@/types/companyAccess";

type ReviewFilter = "all" | "due" | "stale" | "high_risk" | "inactive";

const riskLabel: Record<string, string> = {
  inactive: "ปิดใช้งาน",
  stale: "ไม่ได้ใช้งานนาน",
  high_risk: "สิทธิ์ความเสี่ยงสูง",
  segregation_conflict: "ผู้ขอและผู้อนุมัติ",
  review_due: "ถึงรอบตรวจ",
};

export default function CompanyAccessReviewPage(): JSX.Element {
  const [params] = useSearchParams();
  const [filter, setFilter] = useState<ReviewFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(params.get("user"));
  const [reason, setReason] = useState("");
  const [assignmentId, setAssignmentId] = useState("");
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const reviews = useQuery({
    queryKey: ["company-access", "reviews", filter],
    queryFn: async () => (await companyAccessApi.reviews(filter === "all" ? undefined : filter)).data.data,
    retry: false,
  });
  const selected = useMemo(
    () => reviews.data?.find((item) => item.id === selectedId) ?? null,
    [reviews.data, selectedId],
  );
  useEffect(() => {
    if (!selectedId && reviews.data?.length) setSelectedId(reviews.data[0].id);
  }, [reviews.data, selectedId]);

  const sessions = useQuery({
    queryKey: ["company-access", "sessions", selectedId],
    queryFn: async () => (await companyAccessApi.sessions(selectedId ?? "")).data.data,
    enabled: Boolean(selectedId),
    retry: false,
  });
  const assignments = useQuery({
    queryKey: ["company-access", "assignments", selectedId],
    queryFn: async () => (await userApi.listRoleAssignments(selectedId ?? "")).data.data,
    enabled: Boolean(selectedId),
    retry: false,
  });

  const refresh = async (): Promise<void> => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["company-access", "reviews"] }),
      queryClient.invalidateQueries({ queryKey: ["company-access", "sessions"] }),
      queryClient.invalidateQueries({ queryKey: ["company-access", "assignments"] }),
    ]);
  };
  const review = useMutation({
    mutationFn: async ({ user, outcome }: { user: CompanyAccessReviewUser; outcome: AccessReviewOutcome }) => {
      if (!reason.trim()) throw new Error("กรุณาระบุเหตุผล");
      if (outcome === "reduce" && !assignmentId) throw new Error("กรุณาเลือกสิทธิ์ที่จะลด");
      return companyAccessApi.review(user.id, {
        outcome,
        reason: reason.trim(),
        request_id: crypto.randomUUID(),
        expected_credential_version: user.credential_version,
        assignment_id: outcome === "reduce" ? assignmentId : undefined,
      });
    },
    onSuccess: async () => {
      setReason("");
      setAssignmentId("");
      await refresh();
      toast({ title: "บันทึกผลตรวจสิทธิ์แล้ว", description: "Server บันทึกเหตุผลและหลักฐาน Audit เรียบร้อย" });
    },
    onError: (error: Error) => toast({ title: "ดำเนินการไม่สำเร็จ", description: error.message, variant: "destructive" }),
  });
  const revokeSession = useMutation({
    mutationFn: async ({ user, sessionId }: { user: CompanyAccessReviewUser; sessionId?: string }) => {
      if (!reason.trim()) throw new Error("กรุณาระบุเหตุผล");
      const payload = {
        reason: reason.trim(),
        request_id: crypto.randomUUID(),
        expected_credential_version: user.credential_version,
      };
      return sessionId
        ? companyAccessApi.revokeSession(user.id, sessionId, payload)
        : companyAccessApi.revokeAllSessions(user.id, payload);
    },
    onSuccess: async () => {
      setReason("");
      await refresh();
      toast({ title: "ยกเลิก Session แล้ว" });
    },
    onError: (error: Error) => toast({ title: "ยกเลิก Session ไม่สำเร็จ", description: error.message, variant: "destructive" }),
  });

  if (reviews.isLoading) return <CompanyStatePanel kind="loading" />;
  if (reviews.error || !reviews.data) return <CompanyStatePanel kind={companyRequestState(reviews.error)} onRetry={() => void reviews.refetch()} />;

  return (
    <div data-testid="company-access-review-page">
      <PageHeader title="ตรวจทบทวนสิทธิ์" subtitle="ตรวจผู้ใช้ สิทธิ์ความเสี่ยง และ Session ภายในบริษัท โดยทุกการเปลี่ยนแปลงยืนยันที่ Server" />
      <div className="mb-4 flex gap-2 overflow-x-auto pb-1">
        {(["all", "due", "stale", "high_risk", "inactive"] as ReviewFilter[]).map((value) => (
          <Button key={value} variant={filter === value ? "default" : "outline"} onClick={() => { setFilter(value); setSelectedId(null); }}>
            {{ all: "ทั้งหมด", due: "ถึงรอบตรวจ", stale: "ไม่ได้ใช้นาน", high_risk: "ความเสี่ยงสูง", inactive: "ปิดใช้งาน" }[value]}
          </Button>
        ))}
      </div>
      {reviews.data.length === 0 ? (
        <CompanyStatePanel kind="empty" />
      ) : (
        <div className="grid gap-4 xl:grid-cols-[minmax(20rem,0.9fr)_minmax(30rem,1.6fr)]">
          <section className="space-y-2" aria-label="รายชื่อผู้ใช้">
            {reviews.data.map((user) => (
              <button key={user.id} type="button" onClick={() => setSelectedId(user.id)} className={`w-full rounded-2xl border bg-white p-4 text-left shadow-sm ${selectedId === user.id ? "border-blue-500 ring-2 ring-blue-100" : "border-slate-200"}`}>
                <span className="flex items-start justify-between gap-3"><span><strong className="block text-slate-950">{user.display_name}</strong><span className="text-sm text-slate-500">{user.username}</span></span><Badge variant={user.is_active ? "success" : "secondary"}>{user.is_active ? "ใช้งาน" : "ปิด"}</Badge></span>
                <span className="mt-3 flex flex-wrap gap-1">{user.risk_flags.map((flag) => <Badge key={flag} variant="outline">{riskLabel[flag] ?? flag}</Badge>)}</span>
              </button>
            ))}
          </section>
          {selected ? (
            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-4">
                <div><h2 className="text-xl font-black">{selected.display_name}</h2><p className="text-sm text-slate-500">{selected.email ?? selected.username}</p></div>
                <div className="text-right text-sm text-slate-600"><p>{selected.active_session_count} active session</p><p>เข้าสู่ระบบล่าสุด {formatCompanyDateTime(selected.last_login_at)}</p></div>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl bg-slate-50 p-4"><p className="text-xs font-bold text-slate-500">บทบาท</p><p className="mt-1 font-semibold">{selected.role_names.join(", ") || "ไม่มีบทบาท"}</p></div>
                <div className="rounded-xl bg-slate-50 p-4"><p className="text-xs font-bold text-slate-500">MFA ของผู้ใช้</p><p className="mt-1 font-semibold">{selected.mfa_state === "enabled" ? "เปิดแล้ว" : "ยังไม่ได้ตั้งค่า"}</p></div>
              </div>
              <div className="mt-5 space-y-3 border-t border-slate-100 pt-5">
                <label className="block text-sm font-bold">เหตุผลที่ตรวจสอบหรือเปลี่ยนแปลง<Input className="mt-2" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="จำเป็นสำหรับ Audit" /></label>
                <label className="block text-sm font-bold">สิทธิ์ที่จะลด (ใช้เมื่อเลือก “ลดสิทธิ์”)
                  <select className="mt-2 min-h-11 w-full rounded-md border border-slate-200 bg-white px-3" value={assignmentId} onChange={(event) => setAssignmentId(event.target.value)}>
                    <option value="">เลือกสิทธิ์</option>
                    {(assignments.data ?? []).filter((item) => !item.revoked_at).map((item) => <option key={item.id} value={item.id}>{item.role_name} · {item.scope_label}</option>)}
                  </select>
                </label>
                <div className="flex flex-wrap gap-2">
                  <Button disabled={review.isPending} onClick={() => review.mutate({ user: selected, outcome: "retain" })}><UserCheck className="mr-2 h-4 w-4" />คงสิทธิ์</Button>
                  <Button variant="outline" disabled={review.isPending} onClick={() => review.mutate({ user: selected, outcome: "investigate" })}><AlertTriangle className="mr-2 h-4 w-4" />ตรวจเพิ่ม</Button>
                  <Button variant="outline" disabled={review.isPending || !assignmentId} onClick={() => review.mutate({ user: selected, outcome: "reduce" })}><ShieldCheck className="mr-2 h-4 w-4" />ลดสิทธิ์</Button>
                  <Button variant="destructive" disabled={review.isPending || !selected.is_active} onClick={() => review.mutate({ user: selected, outcome: "revoke" })}>เพิกถอนบัญชี</Button>
                </div>
              </div>
              <div className="mt-6 border-t border-slate-100 pt-5">
                <div className="mb-3 flex items-center justify-between gap-3"><h3 className="font-black"><KeyRound className="mr-2 inline h-4 w-4" />Session ล่าสุด</h3><Button variant="outline" disabled={revokeSession.isPending || selected.active_session_count === 0} onClick={() => revokeSession.mutate({ user: selected })}>ยกเลิกทั้งหมด</Button></div>
                {sessions.isLoading ? <p className="text-sm text-slate-500"><RefreshCw className="mr-2 inline h-4 w-4 animate-spin" />กำลังโหลด Session</p> : null}
                <div className="space-y-2">{(sessions.data ?? []).map((session) => <div key={session.id} className="flex flex-col justify-between gap-2 rounded-xl border border-slate-200 p-3 sm:flex-row sm:items-center"><div><p className="text-sm font-bold">{session.state === "active" ? "ใช้งานอยู่" : session.state === "revoked" ? "ยกเลิกแล้ว" : "หมดอายุ"}</p><p className="break-all text-xs text-slate-500">{session.ip_address ?? "ไม่ทราบ IP"} · {session.user_agent ?? "ไม่ทราบอุปกรณ์"}</p></div>{session.state === "active" ? <Button size="sm" variant="outline" disabled={revokeSession.isPending} onClick={() => revokeSession.mutate({ user: selected, sessionId: session.id })}>ยกเลิก</Button> : null}</div>)}</div>
              </div>
            </section>
          ) : null}
        </div>
      )}
    </div>
  );
}
