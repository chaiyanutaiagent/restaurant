import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ClipboardCheck, Loader2, ShieldAlert, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import api from "@/lib/api";
import { physicalUatApi, type PhysicalUATCheck, type PhysicalUATSession } from "@/lib/physicalUatApi";
import type { ApiResponse } from "@/types/api";
import type { DeviceRead } from "@/types/device";

function message(error: unknown): string {
  if (error && typeof error === "object" && "response" in error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail) return JSON.stringify(detail);
  }
  return error instanceof Error ? error.message : "ทำรายการไม่สำเร็จ";
}

function CheckRow({ session, check }: { session: PhysicalUATSession; check: PhysicalUATCheck }): JSX.Element {
  const queryClient = useQueryClient();
  const [evidence, setEvidence] = useState(check.evidence_reference ?? "");
  const [reason, setReason] = useState(check.reason ?? "");
  const [defectId, setDefectId] = useState(check.defect_id ?? "");
  const [severity, setSeverity] = useState<"P0" | "P1" | "P2" | "P3">((check.defect_severity as "P0" | "P1" | "P2" | "P3") ?? "P2");
  const mutation = useMutation({
    mutationFn: (result: "pass" | "fail" | "na") => physicalUatApi.updateCheck(session.id, check.check_key, {
      result,
      evidence_reference: result === "na" ? null : evidence.trim(),
      reason: reason.trim() || null,
      defect_id: result === "fail" ? defectId.trim() : null,
      defect_severity: result === "fail" ? severity : null,
      evidence: { recorded_from: "uat_readiness_ui", recorded_at: new Date().toISOString() },
    }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["physical-uat-session", session.id] }),
  });
  if (check.source === "automatic") return (
    <div className="flex min-h-14 flex-wrap items-center justify-between gap-3 rounded-xl border p-3">
      <div><p className="font-semibold">{check.label}</p><p className="text-xs text-slate-500">ระบบตรวจอัตโนมัติ · {check.check_key}</p></div>
      <Badge className={check.result === "pass" ? "bg-emerald-600" : check.result === "fail" ? "bg-red-600" : "bg-slate-500"}>{check.result}</Badge>
    </div>
  );
  return (
    <div className="space-y-3 rounded-xl border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2"><div><p className="font-semibold">{check.label}</p><p className="text-xs text-slate-500">{check.check_key}</p></div><Badge variant="outline">{check.result}</Badge></div>
      <div className="grid gap-3 md:grid-cols-2">
        <div><Label>หลักฐานอ้างอิง (ห้ามใส่รหัส/Token)</Label><Input className="mt-1 h-11" value={evidence} onChange={(event) => setEvidence(event.target.value)} placeholder="เช่น รูป/วิดีโอ/เลขบิล UAT" /></div>
        <div><Label>เหตุผล/หมายเหตุ</Label><Input className="mt-1 h-11" value={reason} onChange={(event) => setReason(event.target.value)} /></div>
      </div>
      <div className="grid gap-3 md:grid-cols-[1fr_120px_auto]">
        <Input className="h-11" value={defectId} onChange={(event) => setDefectId(event.target.value)} placeholder="Defect ID (เมื่อ Fail)" />
        <select className="h-11 rounded-md border bg-white px-3" value={severity} onChange={(event) => setSeverity(event.target.value as typeof severity)}><option>P0</option><option>P1</option><option>P2</option><option>P3</option></select>
        <div className="flex flex-wrap gap-2">
          <Button className="h-11 bg-emerald-600" disabled={!evidence.trim() || mutation.isPending} onClick={() => mutation.mutate("pass")}>ผ่าน</Button>
          <Button className="h-11" variant="destructive" disabled={!evidence.trim() || !defectId.trim() || mutation.isPending} onClick={() => mutation.mutate("fail")}>ไม่ผ่าน</Button>
          <Button className="h-11" variant="outline" disabled={!reason.trim() || mutation.isPending} onClick={() => mutation.mutate("na")}>N/A</Button>
        </div>
      </div>
      {mutation.error && <p className="text-sm text-red-700">{message(mutation.error)}</p>}
    </div>
  );
}

export default function PhysicalUATReadinessPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [release, setRelease] = useState("");
  const [model, setModel] = useState("iPad / Tablet");
  const [os, setOs] = useState("");
  const [browser, setBrowser] = useState("");
  const [printer, setPrinter] = useState("");
  const [network, setNetwork] = useState("UAT Wi-Fi + controlled disconnect");
  const sessionsQuery = useQuery({ queryKey: ["physical-uat-sessions"], queryFn: async () => (await physicalUatApi.list()).data.data, retry: false });
  const devicesQuery = useQuery({ queryKey: ["system-devices"], queryFn: async () => (await api.get<ApiResponse<DeviceRead[]>>("/system/devices")).data.data });
  const sessionQuery = useQuery({
    queryKey: ["physical-uat-session", selectedId],
    queryFn: async () => (await physicalUatApi.get(selectedId)).data.data,
    enabled: Boolean(selectedId),
  });
  const createMutation = useMutation({
    mutationFn: () => physicalUatApi.create({ device_id: deviceId, release_commit: release, device_model: model, os_version: os, browser_version: browser, printer_model_connection: printer || null, network_profile: network }),
    onSuccess: (response) => { setSelectedId(response.data.data.id); void queryClient.invalidateQueries({ queryKey: ["physical-uat-sessions"] }); },
  });
  const submitMutation = useMutation({ mutationFn: () => physicalUatApi.submit(selectedId), onSuccess: () => void sessionQuery.refetch() });
  const signoffMutation = useMutation({ mutationFn: (role: "technical" | "business") => physicalUatApi.signoff(selectedId, role, `${role} UAT sign-off after evidence review`), onSuccess: () => void sessionQuery.refetch() });
  const counterDevices = useMemo(() => (devicesQuery.data ?? []).filter((item) => item.device_type === "counter" && item.status === "paired"), [devicesQuery.data]);
  const session = sessionQuery.data;

  return (
    <div className="space-y-6">
      <div><p className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-600">UAT only</p><h1 className="text-3xl font-black">Physical UAT Readiness</h1><p className="mt-1 text-slate-500">หลักฐานอุปกรณ์จริงต้องบันทึกโดยผู้ทดสอบ ระบบจะไม่ทำเครื่องหมายผ่านแทน</p></div>
      {sessionsQuery.error && <div className="rounded-xl border border-amber-300 bg-amber-50 p-4"><p className="font-bold">หน้านี้ปิดอยู่ใน Environment ปัจจุบัน</p><p className="text-sm">เปิดได้เฉพาะ UAT ที่ตั้งค่า Evidence flag เท่านั้น</p></div>}
      <Card><CardHeader><CardTitle>เริ่มรอบทดสอบ</CardTitle><CardDescription>Release, Counter และสภาพแวดล้อมจะถูก snapshot ลง audit</CardDescription></CardHeader><CardContent className="grid gap-3 md:grid-cols-3">
        <div><Label>Counter ที่จับคู่แล้ว</Label><select className="mt-1 h-11 w-full rounded-md border bg-white px-3" value={deviceId} onChange={(event) => setDeviceId(event.target.value)}><option value="">เลือกเครื่อง</option>{counterDevices.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.device_code}</option>)}</select></div>
        <div><Label>Release commit</Label><Input className="mt-1 h-11 font-mono" value={release} onChange={(event) => setRelease(event.target.value.trim())} placeholder="7–64 ตัวอักษร hex" /></div>
        <div><Label>Device model</Label><Input className="mt-1 h-11" value={model} onChange={(event) => setModel(event.target.value)} /></div>
        <div><Label>OS version</Label><Input className="mt-1 h-11" value={os} onChange={(event) => setOs(event.target.value)} /></div>
        <div><Label>Browser version</Label><Input className="mt-1 h-11" value={browser} onChange={(event) => setBrowser(event.target.value)} /></div>
        <div><Label>Printer / Connection</Label><Input className="mt-1 h-11" value={printer} onChange={(event) => setPrinter(event.target.value)} /></div>
        <div className="md:col-span-2"><Label>Network profile</Label><Input className="mt-1 h-11" value={network} onChange={(event) => setNetwork(event.target.value)} /></div>
        <div className="flex items-end"><Button className="h-11 w-full" disabled={!deviceId || release.length < 7 || !os || !browser || createMutation.isPending} onClick={() => createMutation.mutate()}>{createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}สร้าง UAT Session</Button></div>
        {createMutation.error && <p className="md:col-span-3 text-sm text-red-700">{message(createMutation.error)}</p>}
      </CardContent></Card>

      {(sessionsQuery.data?.length ?? 0) > 0 && <div className="flex flex-wrap gap-2">{sessionsQuery.data?.map((item) => <Button key={item.id} variant={selectedId === item.id ? "default" : "outline"} className="h-11" onClick={() => setSelectedId(item.id)}>{item.release_commit.slice(0, 10)} · {item.status}</Button>)}</div>}

      {session && <>
        <section className="grid gap-3 sm:grid-cols-3"><Card><CardContent className="pt-5"><p className="text-sm text-slate-500">ผ่าน</p><p className="text-3xl font-black text-emerald-700">{session.summary.passed ?? 0}</p></CardContent></Card><Card><CardContent className="pt-5"><p className="text-sm text-slate-500">ยังไม่ครบ</p><p className="text-3xl font-black text-amber-700">{session.summary.required_incomplete ?? 0}</p></CardContent></Card><Card><CardContent className="pt-5"><p className="text-sm text-slate-500">P0/P1</p><p className="text-3xl font-black text-red-700">{session.summary.critical_defects ?? 0}</p></CardContent></Card></section>
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><ClipboardCheck className="h-5 w-5" />Checklist · {session.status}</CardTitle><CardDescription>Pass/Fail ต้องมีหลักฐาน; N/A ต้องมีเหตุผลและสิทธิ์ Manager</CardDescription></CardHeader><CardContent className="space-y-3">{session.checks.map((check) => <CheckRow key={check.id} session={session} check={check} />)}</CardContent></Card>
        <div className="rounded-2xl border bg-white p-4">
          <div className="flex flex-wrap items-center gap-3">
            <Button className="h-11" disabled={submitMutation.isPending} onClick={() => submitMutation.mutate()}><ClipboardCheck className="mr-2 h-4 w-4" />ส่งตรวจ Gate</Button>
            <Button className="h-11" variant="outline" disabled={session.status !== "ready_for_signoff" || signoffMutation.isPending} onClick={() => signoffMutation.mutate("technical")}><CheckCircle2 className="mr-2 h-4 w-4" />Technical sign-off</Button>
            <Button className="h-11" variant="outline" disabled={session.status !== "ready_for_signoff" || signoffMutation.isPending} onClick={() => signoffMutation.mutate("business")}><CheckCircle2 className="mr-2 h-4 w-4" />Business sign-off</Button>
          </div>
          {(submitMutation.error || signoffMutation.error) && <p className="mt-3 flex items-center gap-2 text-sm text-red-700"><XCircle className="h-4 w-4" />{message(submitMutation.error ?? signoffMutation.error)}</p>}
          <p className="mt-3 flex items-center gap-2 text-xs text-slate-500"><ShieldAlert className="h-4 w-4" />ผู้ส่ง, Technical checker และ Business checker ต้องเป็นคนละบัญชี</p>
        </div>
      </>}
      {!session && !sessionsQuery.isLoading && !sessionsQuery.error && <div className="rounded-2xl border border-dashed p-12 text-center text-slate-500"><AlertTriangle className="mx-auto mb-3 h-8 w-8" />เลือกหรือสร้าง UAT Session เพื่อเริ่มบันทึกหลักฐาน</div>}
    </div>
  );
}
