import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  CircleDashed,
  ClipboardCheck,
  Clock3,
  ExternalLink,
  Info,
  Loader2,
  MonitorCheck,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  TabletSmartphone,
  UserRoundCheck,
  Wifi,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import api from "@/lib/api";
import { physicalUatApi, type PhysicalUATCheck, type PhysicalUATResult, type PhysicalUATSession } from "@/lib/physicalUatApi";
import { useAuthStore } from "@/stores/auth.store";
import type { ApiResponse } from "@/types/api";
import type { DeviceRead } from "@/types/device";

const CATEGORY_ORDER = ["system", "hardware", "payment", "flow", "network", "reconciliation", "recovery"];
const CATEGORY_LABEL: Record<string, string> = {
  system: "A · ระบบและตัวตน",
  hardware: "B · อุปกรณ์จริง",
  payment: "C · การชำระเงิน",
  flow: "D · Flow หน้าร้าน",
  network: "E · Network และการกู้คืน",
  reconciliation: "F · การกระทบยอด",
  recovery: "G · Rollback และ Recovery",
};

const RESULT_META: Record<PhysicalUATResult, { label: string; className: string; icon: typeof Clock3 }> = {
  pending: { label: "ยังไม่ยืนยัน", className: "border-amber-300 bg-amber-50 text-amber-800", icon: Clock3 },
  pass: { label: "ผ่านพร้อมหลักฐาน", className: "border-emerald-200 bg-emerald-50 text-emerald-700", icon: CheckCircle2 },
  fail: { label: "ไม่ผ่าน", className: "border-red-200 bg-red-50 text-red-700", icon: XCircle },
  na: { label: "ไม่ใช้กับสาขานี้", className: "border-slate-300 bg-slate-100 text-slate-700", icon: Info },
};

const ACTION_LINK: Record<string, { label: string; path: string }> = {
  counter_pairing: { label: "ดูอุปกรณ์", path: "/devices" },
  sync_queue_zero: { label: "เปิดศูนย์ซิงก์", path: "/restaurant/offline-sync" },
  product_barcode: { label: "เปิดหน้าขาย", path: "/restaurant/pos" },
  table_qr: { label: "เปิดโต๊ะ + QR", path: "/restaurant/tables" },
  customer_receipt: { label: "เปิดหน้าขาย", path: "/restaurant/pos" },
  kitchen_slip: { label: "เปิด KDS", path: "/restaurant/kitchen" },
  dine_in_e2e: { label: "เริ่ม Dine-in", path: "/restaurant/tables" },
  takeaway_e2e: { label: "เริ่ม Takeaway", path: "/restaurant/pos?channel=takeaway" },
  offline_cash_reconnect: { label: "เปิดหน้าขายรับกลับ", path: "/restaurant/pos?channel=takeaway" },
  lost_ack: { label: "เปิดศูนย์ซิงก์", path: "/restaurant/offline-sync" },
};

const NA_ALLOWED_CHECKS = new Set(["cash_drawer"]);

function message(error: unknown): string {
  if (error && typeof error === "object" && "response" in error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const record = detail as { blockers?: string[]; critical_defects?: string[] };
      if (record.blockers?.length) return `ยังไม่ครบ: ${record.blockers.join(", ")}`;
      return JSON.stringify(detail);
    }
  }
  return error instanceof Error ? error.message : "ทำรายการไม่สำเร็จ";
}

function dateTime(value?: string | null): string {
  if (!value) return "ยังไม่มี";
  return new Date(value).toLocaleString("th-TH", { dateStyle: "short", timeStyle: "short" });
}

function safeValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "boolean") return value ? "เปิด" : "ปิด";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function snapshotRows(snapshot: Record<string, unknown>): Array<[string, string]> {
  return Object.entries(snapshot).map(([key, value]) => [key, safeValue(value)]);
}

function CheckStatus({ result }: { result: PhysicalUATResult }): JSX.Element {
  const meta = RESULT_META[result];
  const Icon = meta.icon;
  return <Badge variant="outline" className={`${meta.className} min-h-7`}><Icon className="mr-1 h-3.5 w-3.5" />{meta.label}</Badge>;
}

function CheckRow({ session, check, canManage }: { session: PhysicalUATSession; check: PhysicalUATCheck; canManage: boolean }): JSX.Element {
  const queryClient = useQueryClient();
  const [evidence, setEvidence] = useState(check.evidence_reference ?? "");
  const [reason, setReason] = useState(check.reason ?? "");
  const [defectId, setDefectId] = useState(check.defect_id ?? "");
  const [severity, setSeverity] = useState<"P0" | "P1" | "P2" | "P3">((check.defect_severity as "P0" | "P1" | "P2" | "P3") ?? "P2");
  const action = ACTION_LINK[check.check_key];
  const mutation = useMutation({
    mutationFn: (result: "pass" | "fail" | "na") => physicalUatApi.updateCheck(session.id, check.check_key, {
      result,
      evidence_reference: result === "na" ? null : evidence.trim(),
      reason: reason.trim() || null,
      defect_id: result === "fail" ? defectId.trim() : null,
      defect_severity: result === "fail" ? severity : null,
      evidence: {
        recorded_from: "uat_readiness_ui",
        recorded_at: new Date().toISOString(),
        evidence_kind: result === "na" ? "approved_exception" : "physical_observation",
      },
    }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["physical-uat-session", session.id] }),
  });

  if (check.source === "automatic") {
    return (
      <article className="rounded-2xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2"><p className="font-black text-slate-900">{check.label}</p><Badge variant="secondary">ระบบตรวจ ณ เวลานี้</Badge></div>
            <p className="mt-1 text-xs text-slate-500">{check.check_key} · ตรวจล่าสุด {dateTime(check.tested_at)}</p>
          </div>
          <CheckStatus result={check.result} />
        </div>
        {check.reason ? <p className="mt-3 rounded-xl bg-red-50 p-3 text-sm text-red-700">{check.reason}</p> : null}
        {Object.keys(check.evidence ?? {}).length ? (
          <dl className="mt-3 grid gap-2 text-xs text-slate-600 sm:grid-cols-2">
            {snapshotRows(check.evidence).map(([key, value]) => <div key={key} className="rounded-xl bg-slate-50 p-2"><dt className="font-semibold text-slate-400">{key}</dt><dd className="mt-0.5 break-all font-medium text-slate-700">{value}</dd></div>)}
          </dl>
        ) : null}
        {action ? <Button asChild variant="outline" size="sm" className="mt-3 min-h-11"><Link to={action.path}>{action.label}<ExternalLink className="h-4 w-4" /></Link></Button> : null}
      </article>
    );
  }

  return (
    <article className={`rounded-2xl border p-4 ${check.result === "fail" ? "border-red-300 bg-red-50/50" : "border-slate-200 bg-white"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-black text-slate-900">{check.label}</p>
            {check.required ? <Badge variant="outline" className="border-red-200 text-red-700">บังคับ</Badge> : <Badge variant="outline">ไม่บังคับ</Badge>}
            <Badge variant="secondary">ต้องทดสอบบนอุปกรณ์จริง</Badge>
          </div>
          <p className="mt-1 text-xs text-slate-500">{check.check_key} · ผู้ทดสอบ {check.tested_by ? check.tested_by.slice(-8) : "ยังไม่มี"} · {dateTime(check.tested_at)}</p>
        </div>
        <CheckStatus result={check.result} />
      </div>

      {!canManage ? (
        <div className="mt-3 rounded-xl bg-slate-50 p-3 text-sm text-slate-600">คุณดูผลได้ แต่ต้องใช้สิทธิ์ผู้จัดการอุปกรณ์เพื่อบันทึกหลักฐาน</div>
      ) : (
        <div className="mt-4 space-y-3">
          <div className="grid gap-3 md:grid-cols-2">
            <div><Label htmlFor={`evidence-${check.id}`}>หลักฐานอ้างอิง <span className="text-red-600">*</span></Label><Input id={`evidence-${check.id}`} className="mt-1 h-11" value={evidence} onChange={(event) => setEvidence(event.target.value)} placeholder="เช่น รูป/วิดีโอ/เลขบิล UAT (ห้ามใส่รหัสลับ)" /></div>
            <div><Label htmlFor={`reason-${check.id}`}>เหตุผล/หมายเหตุ</Label><Input id={`reason-${check.id}`} className="mt-1 h-11" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="สิ่งที่ทดสอบและผลที่สังเกต" /></div>
          </div>
          <div className="grid gap-3 md:grid-cols-[minmax(180px,1fr)_120px_auto]">
            <Input aria-label={`Defect ID สำหรับ ${check.label}`} className="h-11" value={defectId} onChange={(event) => setDefectId(event.target.value)} placeholder="Defect ID (เมื่อไม่ผ่าน)" />
            <select aria-label={`ระดับความรุนแรงสำหรับ ${check.label}`} className="h-11 rounded-xl border border-slate-200 bg-white px-3" value={severity} onChange={(event) => setSeverity(event.target.value as typeof severity)}><option>P0</option><option>P1</option><option>P2</option><option>P3</option></select>
            <div className="flex flex-wrap gap-2">
              <Button className="min-h-11 bg-emerald-600 hover:bg-emerald-700" disabled={!evidence.trim() || mutation.isPending} onClick={() => mutation.mutate("pass")}>ยืนยันผ่าน</Button>
              <Button className="min-h-11" variant="destructive" disabled={!evidence.trim() || !defectId.trim() || mutation.isPending} onClick={() => mutation.mutate("fail")}>บันทึกไม่ผ่าน</Button>
              {NA_ALLOWED_CHECKS.has(check.check_key) ? <Button className="min-h-11" variant="outline" disabled={!reason.trim() || mutation.isPending} onClick={() => mutation.mutate("na")}>อนุมัติ N/A</Button> : null}
            </div>
          </div>
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        {action ? <Button asChild variant="outline" size="sm" className="min-h-11"><Link to={action.path}>{action.label}<ChevronRight className="h-4 w-4" /></Link></Button> : <span />}
        {mutation.error ? <p role="alert" className="text-sm font-semibold text-red-700">{message(mutation.error)}</p> : null}
      </div>
    </article>
  );
}

function SessionStatus({ session }: { session: PhysicalUATSession }): JSX.Element {
  const status = session.status;
  if (status === "uat_approved") return <Badge className="bg-emerald-600 text-white"><ShieldCheck className="mr-1 h-4 w-4" />อนุมัติ UAT แล้ว</Badge>;
  if (status === "ready_for_signoff") return <Badge className="bg-blue-600 text-white"><ClipboardCheck className="mr-1 h-4 w-4" />พร้อมเสนอ Sign-off</Badge>;
  if (status === "not_ready") return <Badge className="bg-red-600 text-white"><ShieldAlert className="mr-1 h-4 w-4" />ยังไม่พร้อมเปิดร้าน</Badge>;
  return <Badge className="bg-amber-500 text-white"><CircleDashed className="mr-1 h-4 w-4" />กำลังตรวจ</Badge>;
}

export default function PhysicalUATReadinessPage(): JSX.Element {
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user);
  const branchId = useAuthStore((state) => state.branchId);
  const businessType = useAuthStore((state) => state.businessType);
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const isRetail = businessType === "retail_pos";
  const canManage = hasPermission("system.device.manage");
  const [selectedId, setSelectedId] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [release, setRelease] = useState("");
  const [model, setModel] = useState("iPad / Tablet");
  const [os, setOs] = useState("");
  const [browser, setBrowser] = useState("");
  const [printer, setPrinter] = useState("");
  const [network, setNetwork] = useState("UAT Wi-Fi + controlled disconnect");

  const sessionsQuery = useQuery({ queryKey: ["physical-uat-sessions", branchId], queryFn: async () => (await physicalUatApi.list()).data.data, retry: false });
  const devicesQuery = useQuery({ queryKey: ["system-devices", branchId], queryFn: async () => (await api.get<ApiResponse<DeviceRead[]>>("/system/devices")).data.data, retry: false });
  const sessionQuery = useQuery({
    queryKey: ["physical-uat-session", selectedId],
    queryFn: async () => (await physicalUatApi.get(selectedId)).data.data,
    enabled: Boolean(selectedId),
    retry: false,
  });
  const counterDevices = useMemo(() => (devicesQuery.data ?? []).filter((item) => item.device_type === "counter" && item.status === "paired"), [devicesQuery.data]);
  const session = sessionQuery.data;

  useEffect(() => {
    if (!selectedId && sessionsQuery.data?.[0]?.id) setSelectedId(sessionsQuery.data[0].id);
  }, [selectedId, sessionsQuery.data]);
  useEffect(() => {
    if (!deviceId && counterDevices.length === 1) setDeviceId(counterDevices[0].id);
  }, [counterDevices, deviceId]);

  const createMutation = useMutation({
    mutationFn: () => physicalUatApi.create({ device_id: deviceId, release_commit: release, device_model: model, os_version: os, browser_version: browser, printer_model_connection: printer || null, network_profile: network }),
    onSuccess: (response) => {
      setSelectedId(response.data.data.id);
      void queryClient.invalidateQueries({ queryKey: ["physical-uat-sessions", branchId] });
    },
  });
  const submitMutation = useMutation({ mutationFn: () => physicalUatApi.submit(selectedId), onSuccess: () => void sessionQuery.refetch() });
  const signoffMutation = useMutation({ mutationFn: (role: "technical" | "business") => physicalUatApi.signoff(selectedId, role, `${role} UAT sign-off after evidence review`), onSuccess: () => void sessionQuery.refetch() });

  const groupedChecks = useMemo(() => {
    const groups = new Map<string, PhysicalUATCheck[]>();
    for (const check of session?.checks ?? []) groups.set(check.category, [...(groups.get(check.category) ?? []), check]);
    return CATEGORY_ORDER.map((category) => ({ category, checks: groups.get(category) ?? [] })).filter((group) => group.checks.length > 0);
  }, [session?.checks]);
  const blockers = useMemo(() => (session?.checks ?? []).filter((check) => check.required && !["pass", "na"].includes(check.result)), [session?.checks]);
  const failed = useMemo(() => (session?.checks ?? []).filter((check) => check.result === "fail"), [session?.checks]);
  const physicalPending = useMemo(() => (session?.checks ?? []).filter((check) => check.source === "manual" && check.result === "pending").length, [session?.checks]);
  const canSubmit = Boolean(session && blockers.length === 0 && Number(session.summary.critical_defects ?? 0) === 0 && session.status !== "uat_approved");
  const currentUserIsMaker = Boolean(session?.submitted_by && session.submitted_by === user?.id);

  const pageBlocked = Boolean(sessionsQuery.error);
  const selectedDevice = counterDevices.find((item) => item.id === deviceId);

  return (
    <div className="space-y-5 pb-12">
      <header className="rounded-[28px] border border-blue-100 bg-[linear-gradient(135deg,#eff6ff_0%,#ffffff_55%,#f0fdf4_100%)] p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2"><Badge className="bg-blue-600 text-white">UAT ONLY</Badge><Badge variant="outline">{isRetail ? "Retail Cash Pilot" : "Restaurant Pilot"}</Badge>{isRetail ? <Badge className="border-amber-200 bg-amber-50 text-amber-800">Production ใช้ Legacy</Badge> : null}</div>
            <h1 className="mt-3 text-2xl font-black text-slate-950 md:text-3xl">ตรวจความพร้อมก่อนเปิดร้าน</h1>
            <p className="mt-1 max-w-3xl text-sm text-slate-600">{isRetail ? "ตรวจ Retail Counter โดยแยก Server policy, คิวกู้คืน และอุปกรณ์จริง; Retail Offline payment ยังถูกปิด" : "รวมผลที่ระบบตรวจได้กับหลักฐานจากอุปกรณ์จริง"} โดยไม่ถือว่า Browser smoke, Last seen หรือภาพหน้าจอแทน Physical UAT</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {session ? <SessionStatus session={session} /> : <Badge variant="outline">ยังไม่เลือกรอบทดสอบ</Badge>}
            <Button variant="outline" className="min-h-11" disabled={!selectedId || sessionQuery.isFetching} onClick={() => void sessionQuery.refetch()}><RefreshCw className={`h-4 w-4 ${sessionQuery.isFetching ? "animate-spin" : ""}`} />ตรวจสถานะล่าสุด</Button>
          </div>
        </div>
      </header>

      {pageBlocked ? (
        <div role="alert" className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-amber-950">
          <p className="font-black">หน้านี้ปิดอยู่ใน Environment ปัจจุบัน</p>
          <p className="mt-1 text-sm">Physical UAT Evidence เปิดได้เฉพาะ UAT ที่ตั้งค่าไว้เท่านั้น และจะไม่เปิด Production flag จากหน้านี้</p>
        </div>
      ) : null}

      {!pageBlocked && canManage ? (
        <Card className="overflow-hidden rounded-[24px] border-slate-200">
          <CardHeader className="bg-slate-50"><CardTitle>เริ่มรอบทดสอบอุปกรณ์จริง</CardTitle><CardDescription>Release, Branch, Counter และสภาพแวดล้อมจะถูก snapshot ลง Audit เมื่อสร้าง Session</CardDescription></CardHeader>
          <CardContent className="grid gap-3 pt-5 md:grid-cols-2 xl:grid-cols-4">
            <div><Label htmlFor="uat-counter">Counter ที่จับคู่แล้ว</Label><select id="uat-counter" className="mt-1 h-11 w-full rounded-xl border border-slate-200 bg-white px-3" value={deviceId} onChange={(event) => setDeviceId(event.target.value)}><option value="">เลือกเครื่อง</option>{counterDevices.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.device_code}</option>)}</select></div>
            <div><Label htmlFor="uat-release">Release commit</Label><Input id="uat-release" className="mt-1 h-11 font-mono" value={release} onChange={(event) => setRelease(event.target.value.trim())} placeholder="7–64 ตัวอักษร hex" /></div>
            <div><Label htmlFor="uat-model">Device model</Label><Input id="uat-model" className="mt-1 h-11" value={model} onChange={(event) => setModel(event.target.value)} /></div>
            <div><Label htmlFor="uat-os">OS version</Label><Input id="uat-os" className="mt-1 h-11" value={os} onChange={(event) => setOs(event.target.value)} placeholder="เช่น iPadOS 26.0" /></div>
            <div><Label htmlFor="uat-browser">Browser/App version</Label><Input id="uat-browser" className="mt-1 h-11" value={browser} onChange={(event) => setBrowser(event.target.value)} placeholder="เช่น Safari 26.0" /></div>
            <div><Label htmlFor="uat-printer">Printer / Connection</Label><Input id="uat-printer" className="mt-1 h-11" value={printer} onChange={(event) => setPrinter(event.target.value)} placeholder="เว้นว่างได้จนมีเครื่องจริง" /></div>
            <div><Label htmlFor="uat-network">Network profile</Label><Input id="uat-network" className="mt-1 h-11" value={network} onChange={(event) => setNetwork(event.target.value)} /></div>
            <div className="flex items-end"><Button className="min-h-11 w-full" disabled={!deviceId || release.length < 7 || !os || !browser || createMutation.isPending} onClick={() => createMutation.mutate()}>{createMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ClipboardCheck className="h-4 w-4" />}สร้าง UAT Session</Button></div>
            {selectedDevice ? <p className="text-xs text-slate-500 md:col-span-2 xl:col-span-4">จะสร้างสำหรับ {selectedDevice.name} · {selectedDevice.device_code} · Branch {selectedDevice.branch_id.slice(-8)}</p> : null}
            {createMutation.error ? <p role="alert" className="text-sm font-semibold text-red-700 md:col-span-2 xl:col-span-4">{message(createMutation.error)}</p> : null}
          </CardContent>
        </Card>
      ) : null}

      {(sessionsQuery.data?.length ?? 0) > 0 ? (
        <section aria-label="รอบทดสอบ UAT" className="flex gap-2 overflow-x-auto pb-1">
          {sessionsQuery.data?.map((item) => <Button key={item.id} variant={selectedId === item.id ? "default" : "outline"} className="min-h-11 shrink-0" onClick={() => setSelectedId(item.id)}>{item.release_commit.slice(0, 10)} · {item.status}</Button>)}
        </section>
      ) : null}

      {session ? (
        <>
          <section className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="สรุป Physical UAT">
            {[
              { label: "ผ่านพร้อมหลักฐาน", value: session.summary.passed ?? 0, className: "text-emerald-700", hint: "Auto + Physical evidence" },
              { label: "ต้องทดสอบจริง", value: physicalPending, className: "text-amber-700", hint: "ห้ามอนุมานจาก Browser" },
              { label: "ไม่ผ่าน", value: session.summary.failed ?? 0, className: "text-red-700", hint: "ต้องมี Defect ID" },
              { label: "รายการบังคับยังไม่ครบ", value: session.summary.required_incomplete ?? 0, className: "text-blue-700", hint: "บล็อก Sign-off" },
            ].map((item) => <Card key={item.label} className="rounded-[22px]"><CardContent className="pt-5"><p className="text-sm font-bold text-slate-500">{item.label}</p><p className={`mt-1 text-3xl font-black ${item.className}`}>{item.value}</p><p className="mt-1 text-xs text-slate-500">{item.hint}</p></CardContent></Card>)}
          </section>

          {(blockers.length > 0 || failed.length > 0) ? (
            <section role="alert" className="rounded-[22px] border border-amber-300 bg-amber-50 p-4 text-amber-950">
              <p className="flex items-center gap-2 font-black"><ShieldAlert className="h-5 w-5" />ยังไม่พร้อมเสนอ Sign-off</p>
              <p className="mt-1 text-sm">รายการบังคับที่ยังไม่ผ่าน {blockers.length} รายการ{Number(session.summary.critical_defects ?? 0) > 0 ? ` · มี P0/P1 ${session.summary.critical_defects} รายการ` : ""}</p>
              <div className="mt-3 flex flex-wrap gap-2">{blockers.slice(0, 8).map((check) => <Badge key={check.id} variant="outline" className="border-amber-300 bg-white text-amber-900">{check.label}</Badge>)}</div>
            </section>
          ) : null}

          <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
            <div className="space-y-4">
              {groupedChecks.map((group) => (
                <section key={group.category} className="overflow-hidden rounded-[24px] border border-slate-200 bg-slate-50/70">
                  <div className="border-b border-slate-200 bg-white px-4 py-3"><h2 className="font-black">{CATEGORY_LABEL[group.category] ?? group.category}</h2><p className="text-xs text-slate-500">{group.checks.filter((check) => check.source === "automatic").length} ระบบตรวจ · {group.checks.filter((check) => check.source === "manual").length} ต้องทดสอบจริง</p></div>
                  <div className="space-y-3 p-3">{group.checks.map((check) => <CheckRow key={check.id} session={session} check={check} canManage={canManage} />)}</div>
                </section>
              ))}
            </div>

            <aside className="space-y-4 xl:sticky xl:top-4">
              <Card className="rounded-[24px]"><CardHeader><CardTitle className="flex items-center gap-2"><TabletSmartphone className="h-5 w-5" />Evidence Snapshot</CardTitle><CardDescription>บันทึกเมื่อสร้าง Session และแก้ย้อนหลังไม่ได้</CardDescription></CardHeader><CardContent className="space-y-4 text-sm">
                <div><p className="text-xs font-bold uppercase tracking-wide text-slate-400">Release / Scope</p><dl className="mt-2 space-y-2"><div className="flex justify-between gap-3"><dt>Environment</dt><dd className="font-bold uppercase text-blue-700">{session.environment}</dd></div><div className="flex justify-between gap-3"><dt>Release</dt><dd className="font-mono font-bold">{session.release_commit}</dd></div><div className="flex justify-between gap-3"><dt>Branch</dt><dd className="font-mono">{session.branch_id.slice(-8)}</dd></div><div className="flex justify-between gap-3"><dt>สร้างโดย</dt><dd className="font-mono">{session.created_by.slice(-8)}</dd></div></dl></div>
                <div><p className="text-xs font-bold uppercase tracking-wide text-slate-400">Counter / Hardware</p><dl className="mt-2 space-y-2">{snapshotRows(session.device_snapshot).map(([key, value]) => <div key={key} className="flex justify-between gap-3"><dt className="text-slate-500">{key}</dt><dd className="max-w-48 break-all text-right font-medium">{value}</dd></div>)}</dl></div>
                <div><p className="text-xs font-bold uppercase tracking-wide text-slate-400">Runtime</p><dl className="mt-2 space-y-2">{snapshotRows(session.environment_snapshot).map(([key, value]) => <div key={key} className="flex justify-between gap-3"><dt className="text-slate-500">{key}</dt><dd className="max-w-48 break-all text-right font-medium">{value}</dd></div>)}</dl></div>
              </CardContent></Card>

              <Card className="rounded-[24px]"><CardHeader><CardTitle className="flex items-center gap-2"><UserRoundCheck className="h-5 w-5" />Sign-off</CardTitle><CardDescription>ผู้ส่งตรวจ, Technical และ Business ต้องเป็นคนละบัญชี</CardDescription></CardHeader><CardContent className="space-y-3 text-sm">
                <div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">Submitter</p><p className="mt-1 font-mono font-bold">{session.submitted_by?.slice(-8) ?? "ยังไม่มี"}</p><p className="text-xs text-slate-500">{dateTime(session.submitted_at)}</p></div>
                <div className="grid grid-cols-2 gap-2"><div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">Technical</p><p className="mt-1 font-mono font-bold">{session.technical_approved_by?.slice(-8) ?? "รอ"}</p></div><div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">Business</p><p className="mt-1 font-mono font-bold">{session.business_approved_by?.slice(-8) ?? "รอ"}</p></div></div>
                {canManage ? <div className="space-y-2"><Button className="min-h-11 w-full" disabled={!canSubmit || submitMutation.isPending} onClick={() => submitMutation.mutate()}><ClipboardCheck className="h-4 w-4" />{canSubmit ? "ส่งตรวจ Gate" : `ยังส่งไม่ได้ · ค้าง ${blockers.length}`}</Button><div className="grid grid-cols-2 gap-2"><Button className="min-h-11" variant="outline" disabled={session.status !== "ready_for_signoff" || currentUserIsMaker || signoffMutation.isPending} onClick={() => signoffMutation.mutate("technical")}>Technical</Button><Button className="min-h-11" variant="outline" disabled={session.status !== "ready_for_signoff" || currentUserIsMaker || signoffMutation.isPending} onClick={() => signoffMutation.mutate("business")}>Business</Button></div></div> : null}
                {currentUserIsMaker ? <p className="rounded-xl bg-amber-50 p-3 text-xs font-semibold text-amber-800">บัญชีนี้เป็นผู้ส่งตรวจ ต้องใช้ผู้ตรวจคนอื่นสำหรับ Sign-off</p> : null}
                {(submitMutation.error || signoffMutation.error) ? <p role="alert" className="flex items-start gap-2 text-sm text-red-700"><XCircle className="mt-0.5 h-4 w-4 shrink-0" />{message(submitMutation.error ?? signoffMutation.error)}</p> : null}
              </CardContent></Card>

              <div className="rounded-[22px] border border-blue-200 bg-blue-50 p-4 text-sm text-blue-950">
                <p className="flex items-center gap-2 font-black"><MonitorCheck className="h-5 w-5" />ขอบเขตหน้านี้</p>
                <ul className="mt-2 space-y-1 text-xs"><li>• ไม่เปิด Production flag</li>{isRetail ? <li>• ไม่เปิด Retail Offline/Provider และไม่เปลี่ยน Production Legacy source</li> : null}<li>• ไม่ยืนยัน Printer/Drawer/Scanner จาก Browser</li><li>• ไม่สร้างเอกสารภาษีหรือธุรกรรมเงินจริง</li><li>• ห้ามแนบรหัสผ่าน PIN Token หรือ QR secret</li></ul>
              </div>
            </aside>
          </div>
        </>
      ) : null}

      {!session && !sessionsQuery.isLoading && !pageBlocked ? <div className="rounded-[24px] border border-dashed border-slate-300 bg-white p-12 text-center text-slate-500"><Wifi className="mx-auto mb-3 h-10 w-10" /><p className="font-black text-slate-700">ยังไม่มี UAT Session ที่เลือก</p><p className="mt-1 text-sm">สร้างรอบทดสอบเมื่อมี Release, Counter และผู้ทดสอบอุปกรณ์จริงพร้อม</p></div> : null}
      {sessionQuery.error ? <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-4 text-red-700"><p className="font-black">โหลด UAT Session ไม่สำเร็จ</p><p className="text-sm">{message(sessionQuery.error)}</p></div> : null}
      {sessionQuery.isLoading ? <div className="flex min-h-48 items-center justify-center gap-3 text-slate-600"><Loader2 className="h-6 w-6 animate-spin" />กำลังโหลดหลักฐาน UAT</div> : null}
    </div>
  );
}
