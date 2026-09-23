import { liveQuery } from "dexie";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock3,
  MonitorCheck,
  ReceiptText,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Store,
  UserRoundCheck,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PLATFORM_BRAND } from "@/config/platformBrand";
import { db } from "@/lib/db";
import { useOnlineStatus } from "@/lib/syncService";
import { useAuthStore } from "@/stores/auth.store";
import { useDeviceStore } from "@/stores/device.store";
import type { PendingSale } from "@/types/pos";

type RetailQueueStatus = NonNullable<PendingSale["status"]>;

const STATUS_META: Record<RetailQueueStatus, { label: string; className: string; icon: typeof Clock3 }> = {
  pending: { label: "รอส่ง", className: "border-blue-200 bg-blue-50 text-blue-700", icon: Clock3 },
  syncing: { label: "กำลังส่ง", className: "border-cyan-200 bg-cyan-50 text-cyan-700", icon: RefreshCw },
  needs_review: { label: "ต้องตรวจสอบ", className: "border-amber-300 bg-amber-50 text-amber-800", icon: AlertTriangle },
  synced: { label: "ซิงก์แล้ว", className: "border-emerald-200 bg-emerald-50 text-emerald-700", icon: CheckCircle2 },
};

function dateTime(value?: number): string {
  if (!value) return "-";
  return new Date(value).toLocaleString("th-TH", { dateStyle: "short", timeStyle: "short" });
}

function money(value: number): string {
  return value.toLocaleString("th-TH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function supportReference(value: string): string {
  const compact = value.replace(/[^a-zA-Z0-9]/g, "");
  return compact.length <= 12 ? compact : `${compact.slice(0, 6)}…${compact.slice(-6)}`;
}

export default function RetailOfflineSyncCenterPage(): JSX.Element {
  const isOnline = useOnlineStatus();
  const companyId = useAuthStore((state) => state.companyId);
  const branchId = useAuthStore((state) => state.branchId);
  const user = useAuthStore((state) => state.user);
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const device = useDeviceStore((state) => state.device);
  const hydrateDevice = useDeviceStore((state) => state.hydrate);
  const [rows, setRows] = useState<PendingSale[]>([]);
  const [legacyUnscopedCount, setLegacyUnscopedCount] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    void hydrateDevice();
  }, [hydrateDevice]);

  useEffect(() => {
    const subscription = liveQuery(async () => {
      if (!companyId || !branchId || !user?.id) {
        return { scopedRows: [], unscoped: 0 };
      }
      const scopedRows = (await db.pendingSales
        .where("[company_id+branch_id+business_type]")
        .equals([companyId, branchId, "retail_pos"])
        .filter((row) => row.user_id === user.id)
        .toArray())
        .sort((left, right) => right.created_at - left.created_at);
      const unscoped = await db.pendingSales
        .where("status")
        .equals("needs_review")
        .filter((row) => !row.company_id || !row.branch_id || !row.business_type)
        .count();
      return { scopedRows, unscoped };
    }).subscribe({
      next: ({ scopedRows, unscoped }) => {
        setRows(scopedRows);
        setLegacyUnscopedCount(unscoped);
        setSelectedId((current) => current && scopedRows.some((row) => row.client_order_id === current)
          ? current
          : scopedRows[0]?.client_order_id ?? null);
        setLoadError("");
      },
      error: () => setLoadError("อ่านคิวในเครื่องไม่สำเร็จ กรุณาเปิดหน้าใหม่หรือติดต่อผู้ดูแลระบบ"),
    });
    return () => subscription.unsubscribe();
  }, [branchId, companyId, user?.id]);

  const selected = rows.find((row) => row.client_order_id === selectedId) ?? null;
  const summary = useMemo(() => rows.reduce((result, row) => {
    const status = row.status ?? (row.synced ? "synced" : "needs_review");
    result[status] += 1;
    return result;
  }, { pending: 0, syncing: 0, needs_review: 0, synced: 0 } satisfies Record<RetailQueueStatus, number>), [rows]);

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(37,99,235,0.12),_transparent_28%),linear-gradient(180deg,_#f8fafc_0%,_#eef2ff_100%)] text-slate-950">
      <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col gap-4 p-3 md:p-5">
        <header className="rounded-[28px] border border-white/80 bg-white/95 p-4 shadow-sm">
          <div className="flex flex-wrap items-center gap-3">
            <Button asChild variant="outline" size="icon" aria-label="กลับหน้าขาย"><Link to="/retail/pos"><ArrowLeft className="h-5 w-5" /></Link></Button>
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-600 font-black text-white">F</span>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-blue-600">{PLATFORM_BRAND.productName} · Retail POS</p>
              <h1 className="text-xl font-black md:text-2xl">ศูนย์สถานะและการกู้คืนรายการขาย</h1>
              <div className="mt-2 flex flex-wrap gap-2 text-xs font-semibold text-slate-600">
                <Badge variant="secondary"><Store className="mr-1 h-3.5 w-3.5" />Branch {branchId?.slice(-8) ?? "-"}</Badge>
                <Badge variant="secondary">Counter {device?.device_code ?? "ยังไม่จับคู่"}</Badge>
                <Badge variant="secondary"><UserRoundCheck className="mr-1 h-3.5 w-3.5" />{user?.display_name || user?.username || "-"}</Badge>
                <Badge className="border-amber-200 bg-amber-50 text-amber-800">Cash Pilot · Production ใช้ Legacy</Badge>
              </div>
            </div>
            <Badge className={isOnline ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-300 bg-amber-50 text-amber-800"}>
              {isOnline ? <Wifi className="mr-1 h-4 w-4" /> : <WifiOff className="mr-1 h-4 w-4" />}{isOnline ? "ออนไลน์" : "ออฟไลน์"}
            </Badge>
            {hasPermission("system.device.view") ? <Button asChild variant="outline"><Link to="/devices/uat-readiness"><MonitorCheck className="h-4 w-4" />Counter Readiness</Link></Button> : null}
          </div>
        </header>

        <section role="status" className="rounded-[24px] border border-amber-300 bg-amber-50 p-4 text-amber-950">
          <div className="flex items-start gap-3"><ShieldAlert className="mt-0.5 h-6 w-6 shrink-0" /><div><h2 className="font-black">Retail POS ยังไม่อนุญาตให้รับชำระออฟไลน์</h2><p className="mt-1 text-sm">หน้านี้ใช้ดูคิวและหลักฐานการกู้คืนเท่านั้น เมื่อ Offline สามารถตรวจสินค้าได้ แต่ปุ่มรับชำระต้องปิดและห้ามสร้างรหัสรายการใหม่เพื่อข้ามปัญหา</p></div></div>
        </section>

        <section className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="สรุปคิว Retail">
          {([
            ["รอส่ง", summary.pending, "text-blue-700"],
            ["กำลังส่ง", summary.syncing, "text-cyan-700"],
            ["ต้องตรวจสอบ", summary.needs_review, "text-amber-700"],
            ["ซิงก์แล้ว", summary.synced, "text-emerald-700"],
          ] as const).map(([label, value, color]) => <article key={label} className="rounded-[22px] border border-white/80 bg-white/95 p-4 shadow-sm"><p className="text-sm font-bold text-slate-500">{label}</p><p className={`mt-1 text-3xl font-black ${color}`}>{value}</p></article>)}
        </section>

        {legacyUnscopedCount > 0 ? <div role="alert" className="rounded-2xl border border-slate-300 bg-slate-100 p-4 text-sm text-slate-700"><p className="font-black">กักข้อมูลเดิมที่ไม่มีบริบท {legacyUnscopedCount} รายการ</p><p className="mt-1">ระบบไม่แสดงรายละเอียดและไม่ส่งรายการเหล่านี้อัตโนมัติ เพื่อป้องกันข้อมูลข้าม Company/Branch/User</p></div> : null}
        {loadError ? <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-4 font-semibold text-red-700">{loadError}</div> : null}

        <section className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(320px,0.9fr)_minmax(460px,1.35fr)]">
          <div className="overflow-hidden rounded-[28px] border border-white/80 bg-white/95 shadow-sm">
            <div className="border-b border-slate-200 p-4"><h2 className="font-black">คิวของ Counter นี้</h2><p className="text-xs text-slate-500">แสดงเฉพาะ Company/Branch/User/Retail context ปัจจุบัน</p></div>
            {rows.length === 0 ? <div className="flex min-h-64 flex-col items-center justify-center p-8 text-center text-slate-500"><ShieldCheck className="mb-3 h-12 w-12 text-emerald-500" /><p className="font-black text-slate-700">ไม่มีรายการ Retail ค้าง</p><p className="mt-1 text-sm">การขาย Retail ปัจจุบันต้องออนไลน์และได้รับ Server acknowledgement ก่อนสำเร็จ</p></div> : <div className="max-h-[620px] space-y-2 overflow-y-auto p-2">{rows.map((row) => {
              const status = row.status ?? (row.synced ? "synced" : "needs_review");
              const meta = STATUS_META[status];
              const Icon = meta.icon;
              return <button key={row.client_order_id} type="button" aria-pressed={selectedId === row.client_order_id} className={`min-h-24 w-full rounded-2xl border p-3 text-left ${selectedId === row.client_order_id ? "border-blue-400 bg-blue-50 ring-2 ring-blue-100" : "border-slate-200 bg-white"}`} onClick={() => setSelectedId(row.client_order_id)}><div className="flex items-start justify-between gap-3"><div><p className="font-black">รายการ {supportReference(row.client_order_id)}</p><p className="mt-1 text-xs text-slate-500">{dateTime(row.created_at)} · ลอง {row.attempt_count ?? 0} ครั้ง</p></div><Badge variant="outline" className={meta.className}><Icon className={`mr-1 h-3.5 w-3.5 ${status === "syncing" ? "animate-spin" : ""}`} />{meta.label}</Badge></div><p className="mt-2 text-right font-black">฿{money(row.total_amount)}</p></button>;
            })}</div>}
          </div>

          <div className="flex min-h-[420px] flex-col overflow-hidden rounded-[28px] border border-white/80 bg-white/95 shadow-sm">
            {!selected ? <div className="flex flex-1 flex-col items-center justify-center p-8 text-center text-slate-500"><ReceiptText className="mb-3 h-12 w-12" /><p className="font-black text-slate-700">เลือกรายการเพื่อดูหลักฐาน</p></div> : <><div className="border-b border-slate-200 p-5"><p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">Support reference</p><h2 className="mt-1 text-2xl font-black">{supportReference(selected.client_order_id)}</h2><p className="mt-1 text-sm text-slate-500">เลข Server: {selected.server_order_number || "ยังไม่ได้รับ"}</p></div><div className="flex-1 space-y-4 overflow-y-auto p-5">
              <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4"><div className="rounded-2xl bg-slate-50 p-3"><p className="text-xs text-slate-500">สร้างเมื่อ</p><p className="mt-1 font-bold">{dateTime(selected.created_at)}</p></div><div className="rounded-2xl bg-slate-50 p-3"><p className="text-xs text-slate-500">ลองล่าสุด</p><p className="mt-1 font-bold">{dateTime(selected.last_attempt_at)}</p></div><div className="rounded-2xl bg-slate-50 p-3"><p className="text-xs text-slate-500">กะ</p><p className="mt-1 font-bold">{selected.shift_id.slice(-8)}</p></div><div className="rounded-2xl bg-slate-50 p-3"><p className="text-xs text-slate-500">ยอด</p><p className="mt-1 font-bold">฿{money(selected.total_amount)}</p></div></div>
              <div className="rounded-2xl border border-slate-200"><div className="border-b border-slate-200 px-4 py-3 font-black">รายการสินค้า</div>{selected.items.map((item, index) => <div key={`${item.product_id}-${index}`} className="flex justify-between gap-4 border-b border-slate-100 px-4 py-3 text-sm last:border-0"><span>{item.qty} × {item.product_name}</span><span className="font-bold">฿{money(Number(item.unit_price) * item.qty)}</span></div>)}</div>
              {selected.last_error_message ? <div role="alert" className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950"><p className="font-black">{selected.last_error_code || "ต้องตรวจสอบ"}</p><p className="mt-1">{selected.last_error_message}</p></div> : null}
              <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-950">ห้ามลบรายการรับเงินจริง ห้ามเปลี่ยน Client ID และห้าม retry แบบ blind loop ก่อนยืนยันผลจาก Server</div>
            </div><div className="border-t border-slate-200 p-4"><Button asChild variant="outline" className="min-h-11"><Link to="/retail/pos">กลับหน้าขาย</Link></Button></div></>}
          </div>
        </section>
      </div>
    </main>
  );
}
