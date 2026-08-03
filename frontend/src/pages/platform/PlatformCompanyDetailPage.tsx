import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, CheckCircle2, Circle, Download, KeyRound, Save, ShieldOff, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { platformApi, platformErrorMessage } from "@/lib/platformApi";

export default function PlatformCompanyDetailPage(): JSX.Element {
  const { companyId = "" } = useParams();
  const queryClient = useQueryClient();
  const company = useQuery({
    queryKey: ["platform", "company", companyId],
    queryFn: async () => (await platformApi.company(companyId)).data.data,
    enabled: Boolean(companyId)
  });
  const usage = useQuery({
    queryKey: ["platform", "company", companyId, "usage"],
    queryFn: async () => (await platformApi.companyUsage(companyId)).data.data,
    enabled: Boolean(companyId),
  });
  const usageHistory = useQuery({
    queryKey: ["platform", "company", companyId, "usage", "history"],
    queryFn: async () => (await platformApi.companyUsageHistory(companyId)).data.data,
    enabled: Boolean(companyId),
  });
  const [reason, setReason] = useState("");
  const [planCode, setPlanCode] = useState("starter");
  const [features, setFeatures] = useState<Record<string, boolean>>({});
  const [limits, setLimits] = useState<Record<string, number>>({});

  useEffect(() => {
    if (!company.data) return;
    setPlanCode(company.data.controls.plan_code);
    setFeatures(company.data.controls.feature_flags);
    setLimits(company.data.controls.plan_limits);
  }, [company.data]);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["platform", "company", companyId] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "companies"] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "company", companyId, "usage"] }),
    ]);
  };
  const lifecycle = useMutation({
    mutationFn: async (active: boolean) => {
      if (!reason.trim()) throw new Error("กรุณาระบุเหตุผลเพื่อบันทึก Audit Log");
      return active
        ? platformApi.suspendCompany(companyId, reason)
        : platformApi.reactivateCompany(companyId, reason);
    },
    onSuccess: () => {
      setReason("");
      void refresh();
    }
  });
  const saveControls = useMutation({
    mutationFn: async () => {
      if (!reason.trim()) throw new Error("กรุณาระบุเหตุผลเพื่อบันทึก Audit Log");
      return platformApi.updateControls(companyId, {
        plan_code: planCode,
        feature_flags: features,
        plan_limits: limits,
        reason
      });
    },
    onSuccess: () => {
      setReason("");
      void refresh();
    }
  });
  const exportCompany = useMutation({
    mutationFn: async () => {
      if (!reason.trim()) throw new Error("กรุณาระบุเหตุผลเพื่อบันทึก Audit Log");
      return (await platformApi.exportCompany(companyId, reason)).data.data;
    },
    onSuccess: (artifact) => {
      const blob = new Blob([JSON.stringify(artifact, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `tenant-export-${artifact.company_id}-${artifact.generated_at.slice(0, 10)}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      setReason("");
    }
  });

  if (company.isLoading) return <p className="text-slate-400">กำลังโหลด Company...</p>;
  if (company.error || !company.data) return <p className="text-red-300">{platformErrorMessage(company.error)}</p>;
  const data = company.data;
  const mutationError = lifecycle.error ?? saveControls.error ?? exportCompany.error;

  return (
    <div className="space-y-6">
      <Link to="/platform/companies" className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-emerald-300"><ArrowLeft className="h-4 w-4" />กลับไปรายชื่อบริษัท</Link>
      <section className="rounded-2xl border border-slate-700 bg-slate-900 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm text-emerald-300">Company ID: {data.id}</p>
            <h2 className="mt-2 text-3xl font-bold">{data.name}</h2>
            <p className="mt-2 text-sm text-slate-400">{data.email || "ยังไม่มีอีเมลบริษัท"} · {data.timezone} · {data.currency}</p>
          </div>
          <span className={`rounded-full px-3 py-1.5 text-sm font-semibold ${data.is_active ? "bg-emerald-400/15 text-emerald-300" : "bg-red-400/15 text-red-300"}`}>{data.is_active ? "ACTIVE" : "SUSPENDED"}</span>
        </div>
        {!data.is_active ? (
          <div className="mt-5 rounded-xl border border-red-900 bg-red-950/40 p-4 text-sm text-red-200">
            <p className="font-semibold">Company ถูกระงับและ credential รุ่นก่อนถูกเพิกถอนแล้ว</p>
            <p className="mt-1">เหตุผล: {data.suspension_reason || "ไม่ระบุ"} เมื่อเปิดใหม่ user ต้อง login ใหม่ และ tablet ต้องจับคู่ใหม่</p>
          </div>
        ) : null}
      </section>

      <section className="rounded-2xl border border-slate-700 bg-slate-900 p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><p className="text-sm text-sky-300">Aggregate usage</p><h3 className="mt-1 text-xl font-semibold">การใช้ทรัพยากรตาม Plan</h3><p className="mt-1 text-xs text-slate-400">ไม่รวมรายละเอียดออเดอร์ ลูกค้า หรือข้อมูลพนักงาน</p></div>
          {usage.data?.last_activity_at ? <p className="text-xs text-slate-500">กิจกรรมล่าสุด {new Date(usage.data.last_activity_at).toLocaleString("th-TH")}</p> : null}
        </div>
        {usage.isLoading ? <p className="mt-5 text-sm text-slate-400">กำลังคำนวณ usage...</p> : null}
        {usage.error ? <p className="mt-5 text-sm text-red-300">{platformErrorMessage(usage.error)}</p> : null}
        {usage.data ? (
          <>
            <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {Object.entries(usage.data.limit_state).map(([key, state]) => (
                <article key={key} className={`rounded-xl border p-4 ${state.exceeded ? "border-red-800 bg-red-950/25" : "border-slate-700 bg-slate-950/40"}`}>
                  <p className="text-xs uppercase tracking-wide text-slate-500">{key}</p>
                  <p className="mt-2 text-2xl font-bold">{state.current} <span className="text-sm font-normal text-slate-500">/ {state.unlimited ? "ไม่จำกัด" : state.limit}</span></p>
                  <p className={`mt-2 text-xs ${state.exceeded ? "text-red-300" : "text-slate-400"}`}>{state.exceeded ? "เกิน Plan limit" : state.unlimited ? "Unlimited" : `คงเหลือ ${state.remaining}`}</p>
                </article>
              ))}
            </div>
            {usage.data.attention_codes.length ? <div className="mt-4 flex flex-wrap gap-2">{usage.data.attention_codes.map((code) => <span key={code} className="rounded-full bg-amber-400/10 px-3 py-1 text-xs text-amber-300">{code}</span>)}</div> : null}
          </>
        ) : null}
        <div className="mt-6 border-t border-slate-800 pt-4">
          <p className="text-sm font-semibold">Snapshot history</p>
          {usageHistory.isLoading ? <p className="mt-2 text-xs text-slate-500">กำลังโหลด...</p> : null}
          {usageHistory.data?.length ? <div className="mt-3 flex flex-wrap gap-2">{usageHistory.data.map((snapshot) => <span key={snapshot.id} className="rounded-lg bg-slate-800 px-3 py-2 text-xs text-slate-300">{new Date(snapshot.captured_on).toLocaleDateString("th-TH")} · {snapshot.attention_codes.length} จุดติดตาม</span>)}</div> : !usageHistory.isLoading ? <p className="mt-2 text-xs text-slate-500">ยังไม่มี snapshot — บันทึกได้จากหน้า Dashboard</p> : null}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-700 bg-slate-900 p-6">
        <div className="flex items-center justify-between gap-3">
          <div><p className="text-sm text-emerald-300">Onboarding checklist</p><h3 className="mt-1 text-xl font-semibold">{data.onboarding.completed_steps}/{data.onboarding.total_steps} ขั้นตอน</h3></div>
          {data.onboarding.complete ? <CheckCircle2 className="h-8 w-8 text-emerald-300" /> : <Circle className="h-8 w-8 text-slate-600" />}
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {data.onboarding.steps.map((step) => (
            <div key={step.key} className={`rounded-xl border p-4 ${step.complete ? "border-emerald-800 bg-emerald-950/25" : "border-slate-700 bg-slate-950/40"}`}>
              <div className="flex items-center gap-2">{step.complete ? <CheckCircle2 className="h-5 w-5 text-emerald-300" /> : <Circle className="h-5 w-5 text-slate-500" />}<span className="font-medium">{step.label}</span></div>
              <p className="mt-2 text-xs text-slate-400">พบ {step.count} รายการ</p>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-700 bg-slate-900 p-6">
        <div className="flex items-center gap-3"><KeyRound className="h-6 w-6 text-emerald-300" /><div><h3 className="text-xl font-semibold">Plan และ feature controls</h3><p className="text-sm text-slate-400">ปรับแบบ manual ทุกครั้งต้องมีเหตุผล</p></div></div>
        <div className="mt-6 grid gap-5 md:grid-cols-2">
          <div className="space-y-2"><Label className="text-slate-300">Plan code</Label><Input value={planCode} onChange={(event) => setPlanCode(event.target.value)} /></div>
          <div className="space-y-2"><Label className="text-slate-300">เหตุผลของการเปลี่ยนแปลง/สถานะ</Label><Input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="จำเป็นสำหรับ Audit Log" /></div>
        </div>
        <div className="mt-6 grid gap-6 md:grid-cols-2">
          <div>
            <p className="mb-3 text-sm font-semibold text-slate-300">Feature flags</p>
            <div className="space-y-3">
              {Object.entries(features).map(([key, enabled]) => (
                <label key={key} className="flex items-center justify-between rounded-lg border border-slate-700 px-4 py-3"><span>{key}</span><input type="checkbox" checked={enabled} onChange={(event) => setFeatures({ ...features, [key]: event.target.checked })} /></label>
              ))}
            </div>
          </div>
          <div>
            <p className="mb-1 text-sm font-semibold text-slate-300">Plan limits</p>
            <p className="mb-3 text-xs text-slate-500">0 = ไม่จำกัด (ใช้กับ Company เดิมเพื่อไม่เปลี่ยนพฤติกรรมโดยไม่ตั้งใจ)</p>
            <div className="grid grid-cols-2 gap-3">
              {Object.entries(limits).map(([key, value]) => (
                <div key={key} className="space-y-2"><Label className="text-slate-400">{key}</Label><Input type="number" min={0} value={value} onChange={(event) => setLimits({ ...limits, [key]: Math.max(Number(event.target.value) || 0, 0) })} /></div>
              ))}
            </div>
          </div>
        </div>
        {mutationError ? <p className="mt-4 text-sm text-red-300">{platformErrorMessage(mutationError)}</p> : null}
        <div className="mt-6 flex flex-wrap gap-3 border-t border-slate-700 pt-5">
          <Button className="bg-emerald-400 text-slate-950 hover:bg-emerald-300" onClick={() => saveControls.mutate()} disabled={saveControls.isPending}><Save className="h-4 w-4" />บันทึก controls</Button>
          <Button variant="outline" onClick={() => exportCompany.mutate()} disabled={exportCompany.isPending}><Download className="h-4 w-4" />{exportCompany.isPending ? "กำลังจัด export..." : "ดาวน์โหลด tenant export"}</Button>
          {data.is_active ? (
            <Button variant="destructive" onClick={() => lifecycle.mutate(true)} disabled={lifecycle.isPending}><ShieldOff className="h-4 w-4" />ระงับ Company</Button>
          ) : (
            <Button className="bg-amber-400 text-slate-950 hover:bg-amber-300" onClick={() => lifecycle.mutate(false)} disabled={lifecycle.isPending}><ShieldCheck className="h-4 w-4" />เปิด Company ใหม่</Button>
          )}
        </div>
        <div className="mt-4 flex gap-2 text-xs text-amber-300"><AlertTriangle className="h-4 w-4 shrink-0" /><p>การระงับจะเพิ่ม credential generation, revoke refresh sessions และยกเลิก credential ของ tablet ทุกเครื่องทันที</p></div>
        <p className="mt-2 text-xs text-slate-500">Tenant export มีข้อมูลธุรกิจ/ข้อมูลส่วนบุคคล แต่แทนค่า password, hash, token และ secret ทั้งหมดก่อนดาวน์โหลด พร้อมบันทึก checksum ใน Audit Log</p>
      </section>
    </div>
  );
}
