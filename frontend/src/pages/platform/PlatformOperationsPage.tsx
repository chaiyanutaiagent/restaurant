import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, AlertTriangle, ArchiveRestore, BellRing, CheckCircle2, DatabaseBackup, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { platformApi, platformErrorMessage } from "@/lib/platformApi";
import { usePlatformAuthStore } from "@/stores/platform-auth.store";

const labels: Record<string, string> = {
  legacy_database: "Legacy database",
  platform_database: "Platform database",
  restaurant_database: "Restaurant database",
  redis: "Redis",
  uploads: "Uploads",
  reference_projector: "Reference projector",
  public_api: "Public API",
};

function StateBadge({ value }: { value: string }): JSX.Element {
  const healthy = ["ok", "current", "passed", "healthy", "disabled"].includes(value);
  const unknown = ["unknown", "not_configured"].includes(value);
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${healthy ? "bg-emerald-400/15 text-emerald-300" : unknown ? "bg-slate-700 text-slate-300" : "bg-red-400/15 text-red-300"}`}>{value}</span>;
}

export default function PlatformOperationsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const permissions = usePlatformAuthStore((state) => state.operator?.permissions ?? []);
  const canManageOperations = permissions.includes("*") || permissions.includes("platform.operations.manage");
  const summary = useQuery({
    queryKey: ["platform", "operations", "summary"],
    queryFn: async () => (await platformApi.operationsSummary()).data.data,
    refetchInterval: 60_000,
  });
  const history = useQuery({
    queryKey: ["platform", "operations", "history"],
    queryFn: async () => (await platformApi.operationsHistory()).data.data,
  });
  const capture = useMutation({
    mutationFn: () => platformApi.captureOperations(),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["platform", "operations", "summary"] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "operations", "history"] }),
      ]);
    },
  });

  if (summary.isLoading) return <p className="text-slate-400" aria-label="กำลังโหลดสถานะ Operations">กำลังตรวจสอบ Operations...</p>;
  if (summary.error || !summary.data) return <section className="rounded-2xl border border-red-900 bg-red-950/40 p-6"><AlertTriangle className="h-7 w-7 text-red-300" /><h2 className="mt-3 text-xl font-semibold">โหลด Operations ไม่สำเร็จ</h2><p className="mt-2 text-sm text-red-200">{platformErrorMessage(summary.error)}</p><Button className="mt-4" variant="outline" onClick={() => void summary.refetch()}><RefreshCw className="h-4 w-4" />ลองใหม่</Button></section>;

  const data = summary.data;
  return <div className="space-y-6">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm text-emerald-300">Protected operations</p><h2 className="mt-1 text-3xl font-bold">สถานะระบบและ Recovery</h2><p className="mt-2 text-sm text-slate-400">ข้อมูลสถานะสำหรับผู้มีสิทธิ์ดู Operations โดยไม่มี connection string, path หรือ log</p></div>{canManageOperations ? <Button onClick={() => capture.mutate()} disabled={capture.isPending}><Activity className="h-4 w-4" />{capture.isPending ? "กำลังบันทึก..." : "บันทึก Runtime snapshot"}</Button> : null}</header>
    {capture.error ? <p className="rounded-xl bg-red-950/40 p-3 text-sm text-red-200">{platformErrorMessage(capture.error)}</p> : null}
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <article className="rounded-2xl border border-slate-800 bg-slate-900 p-5"><Activity className="h-5 w-5 text-sky-300" /><p className="mt-3 text-sm text-slate-400">Runtime</p><div className="mt-2"><StateBadge value={data.runtime.status} /></div><p className="mt-3 text-xs text-slate-500">Disk {data.runtime.disk_usage_percent ?? "ไม่ทราบ"}%</p></article>
      <article className="rounded-2xl border border-slate-800 bg-slate-900 p-5"><DatabaseBackup className="h-5 w-5 text-violet-300" /><p className="mt-3 text-sm text-slate-400">Backup</p><div className="mt-2"><StateBadge value={data.latest_backup?.backup_status ?? "unknown"} /></div><p className="mt-3 text-xs text-slate-500">อายุ {data.latest_backup?.backup_age_hours ?? "ไม่ทราบ"} ชั่วโมง</p></article>
      <article className="rounded-2xl border border-slate-800 bg-slate-900 p-5"><ArchiveRestore className="h-5 w-5 text-emerald-300" /><p className="mt-3 text-sm text-slate-400">Restore drill</p><div className="mt-2"><StateBadge value={data.latest_restore?.restore_status ?? "unknown"} /></div><p className="mt-3 text-xs text-slate-500">{data.latest_restore?.restore_drill_at ? new Date(data.latest_restore.restore_drill_at).toLocaleString("th-TH") : "ยังไม่มีหลักฐาน"}</p></article>
      <article className="rounded-2xl border border-slate-800 bg-slate-900 p-5"><BellRing className="h-5 w-5 text-amber-300" /><p className="mt-3 text-sm text-slate-400">Alert delivery</p><div className="mt-2"><StateBadge value={data.latest_alert?.alert_delivery_status ?? "unknown"} /></div><p className="mt-3 text-xs text-slate-500">{data.latest_alert?.alert_codes.length ?? 0} alert codes</p></article>
    </section>
    <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5"><h3 className="text-lg font-semibold">Dependency checks</h3><div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(data.runtime.component_checks).map(([key, value]) => <div key={key} className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/40 p-3"><span className="text-sm">{labels[key] ?? key}</span><StateBadge value={value} /></div>)}</div></section>
    <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5"><h3 className="text-lg font-semibold">Snapshot history</h3>{history.isLoading ? <p className="mt-3 text-sm text-slate-500">กำลังโหลด...</p> : history.data?.length ? <div className="mt-4 space-y-2">{history.data.map((item) => <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 p-3"><div className="flex items-center gap-2">{item.overall_status === "ok" ? <CheckCircle2 className="h-4 w-4 text-emerald-300" /> : <AlertTriangle className="h-4 w-4 text-red-300" />}<span className="text-sm">{new Date(item.captured_at).toLocaleString("th-TH")}</span></div><div className="flex items-center gap-2"><span className="text-xs text-slate-500">{item.source}</span><StateBadge value={item.overall_status} /></div></div>)}</div> : <p className="mt-3 text-sm text-slate-500">ยังไม่มี operational snapshot</p>}</section>
  </div>;
}
