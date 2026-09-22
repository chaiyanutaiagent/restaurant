import { liveQuery } from "dexie";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  CircleHelp,
  Clock3,
  CloudUpload,
  Loader2,
  ReceiptText,
  RefreshCw,
  ShieldCheck,
  Store,
  UserRoundCheck,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";
import { PLATFORM_BRAND } from "@/config/platformBrand";
import type { RestaurantPendingOrder, RestaurantPendingOrderStatus } from "@/lib/db";
import {
  getCachedRestaurantMenu,
  getQueuedRestaurantOrder,
  getRestaurantOutboxSummary,
  inquireRestaurantOperation,
  listRestaurantOutbox,
  retryRestaurantNeedsReview,
  syncRestaurantPendingOrders,
  type RestaurantOutboxSummary,
} from "@/lib/restaurantOffline";
import { useOnlineStatus } from "@/lib/syncService";
import type { WapMenu, WapOrder } from "@/lib/wapApi";
import { useAuthStore } from "@/stores/auth.store";
import { useDeviceStore } from "@/stores/device.store";

const EMPTY_SUMMARY: RestaurantOutboxSummary = {
  pending: 0,
  syncing: 0,
  acknowledged: 0,
  reconciled: 0,
  needsReview: 0,
  rejected: 0,
  quarantined: 0,
  unknown: 0,
};

type StatusMeta = {
  label: string;
  shortLabel: string;
  className: string;
  icon: typeof Clock3;
  explanation: string;
};

const STATUS_META: Record<RestaurantPendingOrderStatus, StatusMeta> = {
  pending_sync: {
    label: "รอส่ง",
    shortLabel: "รอส่ง",
    className: "border-blue-200 bg-blue-50 text-blue-700",
    icon: Clock3,
    explanation: "บิลเก็บในเครื่องแล้ว และกำลังรอ Server ตอบรับ",
  },
  syncing: {
    label: "กำลังส่ง",
    shortLabel: "กำลังส่ง",
    className: "border-blue-200 bg-blue-50 text-blue-700",
    icon: Loader2,
    explanation: "กำลังส่งด้วยรหัสรายการเดิม กรุณารอและไม่ทำรายการซ้ำ",
  },
  server_acknowledged: {
    label: "Server รับแล้ว",
    shortLabel: "รับแล้ว",
    className: "border-cyan-200 bg-cyan-50 text-cyan-700",
    icon: CloudUpload,
    explanation: "Server ตอบรับรายการแล้ว และกำลังรอกระทบยอดขั้นสุดท้าย",
  },
  reconciled: {
    label: "ซิงก์แล้ว",
    shortLabel: "ซิงก์แล้ว",
    className: "border-emerald-200 bg-emerald-50 text-emerald-700",
    icon: CheckCircle2,
    explanation: "รายการได้รับเลขอ้างอิงจาก Server และกระทบยอดแล้ว",
  },
  needs_review: {
    label: "ต้องตรวจสอบ",
    shortLabel: "ตรวจสอบ",
    className: "border-amber-300 bg-amber-50 text-amber-800",
    icon: AlertTriangle,
    explanation: "Server พบข้อมูลที่ต้องแก้ไขก่อนส่งใหม่ กรุณาเรียกผู้จัดการ",
  },
  rejected: {
    label: "Server ปฏิเสธ",
    shortLabel: "ปฏิเสธ",
    className: "border-red-200 bg-red-50 text-red-700",
    icon: AlertTriangle,
    explanation: "รายการถูกปฏิเสธและต้องให้ผู้จัดการตรวจหลักฐาน",
  },
  quarantined: {
    label: "พักไว้ตรวจสอบ",
    shortLabel: "พักไว้",
    className: "border-red-200 bg-red-50 text-red-700",
    icon: ShieldCheck,
    explanation: "ข้อมูลไม่ผ่านการตรวจความถูกต้อง ต้องให้ผู้ดูแลระบบตรวจสอบ",
  },
  unknown: {
    label: "ยังไม่ทราบผล",
    shortLabel: "ไม่ทราบผล",
    className: "border-violet-200 bg-violet-50 text-violet-700",
    icon: CircleHelp,
    explanation: "อาจส่งถึง Server แล้ว ระบบจะตรวจสถานะเดิมก่อนทำสิ่งอื่น",
  },
};

function money(value: string | number | undefined): string {
  return Number(value ?? 0).toLocaleString("th-TH", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function dateTime(value?: string | number | null): string {
  if (!value) return "-";
  return new Date(value).toLocaleString("th-TH", { dateStyle: "short", timeStyle: "short" });
}

function timeOnly(value?: number): string {
  if (!value) return "ยังไม่มีข้อมูล";
  return new Date(value).toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" });
}

function paymentLabel(value?: string): string {
  if (value === "cash") return "เงินสด";
  if (value === "promptpay") return "PromptPay";
  return value || "-";
}

function localLabel(row: RestaurantPendingOrder, order?: WapOrder | null): string {
  if (order?.queue_display) return order.queue_display;
  const compact = row.client_order_id.replace(/[^a-zA-Z0-9]/g, "");
  return `O${compact.slice(-5).toUpperCase()}`;
}

function supportReference(row: RestaurantPendingOrder): string {
  const source = row.client_operation_id || row.client_order_id;
  return source.length <= 12 ? source : `${source.slice(0, 6)}…${source.slice(-6)}`;
}

function staffName(user: ReturnType<typeof useAuthStore.getState>["user"]): string {
  if (!user) return "-";
  return user.display_name
    || [user.first_name, user.last_name].filter(Boolean).join(" ")
    || user.username;
}

export default function OfflineSyncCenterPage(): JSX.Element {
  const { brandSlug } = useParams<{ brandSlug?: string }>();
  const location = useLocation();
  const isOnline = useOnlineStatus();
  const { toast } = useToast();
  const user = useAuthStore((state) => state.user);
  const companyId = useAuthStore((state) => state.companyId);
  const branchId = useAuthStore((state) => state.branchId);
  const device = useDeviceStore((state) => state.device);
  const [rows, setRows] = useState<RestaurantPendingOrder[]>([]);
  const [orders, setOrders] = useState<Record<string, WapOrder | null>>({});
  const [menu, setMenu] = useState<WapMenu | null>(null);
  const [summary, setSummary] = useState<RestaurantOutboxSummary>(EMPTY_SUMMARY);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<"sync" | "inquiry" | "retry" | null>(null);
  const [lastCheckedAt, setLastCheckedAt] = useState<number>(Date.now());
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    const subscription = liveQuery(async () => {
      const nextRows = await listRestaurantOutbox(brandSlug);
      const nextOrders = await Promise.all(nextRows.map(async (row) => (
        [row.client_order_id, await getQueuedRestaurantOrder(row.client_order_id)] as const
      )));
      return {
        rows: nextRows,
        orders: Object.fromEntries(nextOrders) as Record<string, WapOrder | null>,
        summary: await getRestaurantOutboxSummary(brandSlug),
        menu: await getCachedRestaurantMenu(brandSlug),
      };
    }).subscribe({
      next: (value) => {
        setRows(value.rows);
        setOrders(value.orders);
        setSummary(value.summary);
        setMenu(value.menu);
        setSelectedId((current) => current && value.rows.some((row) => row.client_order_id === current)
          ? current
          : value.rows[0]?.client_order_id ?? null);
        setLastCheckedAt(Date.now());
        setLoadError("");
      },
      error: () => setLoadError("อ่านคิวในเครื่องไม่สำเร็จ กรุณาเปิดหน้านี้ใหม่หรือติดต่อผู้ดูแลระบบ"),
    });
    return () => subscription.unsubscribe();
  }, [brandSlug]);

  const selectedRow = rows.find((row) => row.client_order_id === selectedId) ?? null;
  const selectedOrder = selectedRow ? orders[selectedRow.client_order_id] ?? null : null;
  const selectedMeta = selectedRow ? STATUS_META[selectedRow.status] : null;
  const activeCount = summary.pending + summary.syncing + summary.acknowledged + summary.unknown;
  const reviewCount = summary.needsReview + summary.rejected + summary.quarantined;
  const backPath = brandSlug
    ? `/store/${brandSlug}/orders`
    : location.pathname.startsWith("/pos/") ? "/pos?channel=takeaway" : "/counter/orders";
  const authExpiresAt = menu?.offline_authorization_expires_at
    ? new Date(menu.offline_authorization_expires_at).getTime()
    : null;
  const offlineAuthorizationValid = Boolean(
    menu?.offline_mode_enabled
      && authExpiresAt
      && authExpiresAt > Date.now()
      && device
      && menu.offline_device_id === device.device_id,
  );
  const syncDisabled = !isOnline || busyAction !== null || summary.syncing > 0;

  const summaryCards = useMemo(() => [
    { label: "รอส่ง", value: summary.pending + summary.acknowledged + summary.unknown, className: "text-blue-700", hint: "ยังรอผลสุดท้าย" },
    { label: "กำลังส่ง", value: summary.syncing, className: "text-cyan-700", hint: "ห้ามกดซ้ำ" },
    { label: "ต้องตรวจสอบ", value: reviewCount, className: "text-amber-700", hint: "เรียกผู้จัดการ" },
    { label: "ซิงก์แล้ว", value: summary.reconciled, className: "text-emerald-700", hint: `ล่าสุด ${timeOnly(summary.lastSyncAt)}` },
  ], [reviewCount, summary]);

  async function runAction(action: "sync" | "inquiry" | "retry"): Promise<void> {
    if (!isOnline) return;
    setBusyAction(action);
    try {
      if (action === "inquiry" && selectedRow) {
        await inquireRestaurantOperation(selectedRow.client_order_id);
        toast({ title: "ตรวจสถานะกับ Server แล้ว", description: "ระบบใช้รหัสรายการเดิมเพื่อป้องกันบิลซ้ำ" });
      } else if (action === "retry") {
        await retryRestaurantNeedsReview(brandSlug);
        toast({ title: "ส่งรายการที่แก้ไขแล้วอีกครั้ง", description: "ทุกรายการยังใช้รหัสเดิม" });
      } else {
        await syncRestaurantPendingOrders(brandSlug);
        toast({ title: "ตรวจและซิงก์คิวแล้ว", description: "รายการที่ยังไม่ทราบผลจะถูก inquiry ก่อน replay" });
      }
      setLastCheckedAt(Date.now());
    } catch (error) {
      toast({
        title: "ดำเนินการไม่สำเร็จ",
        description: error instanceof Error ? error.message : "โปรดลองใหม่หรือติดต่อผู้ดูแลระบบ",
        variant: "destructive",
      });
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(37,99,235,0.12),_transparent_28%),linear-gradient(180deg,_#f8fafc_0%,_#eef2ff_100%)] text-slate-950">
      <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col gap-4 p-3 md:p-5">
        <header className="rounded-[28px] border border-white/80 bg-white/95 p-4 shadow-sm backdrop-blur">
          <div className="flex flex-wrap items-center gap-3">
            <Button asChild variant="outline" size="icon" aria-label="กลับหน้าขาย">
              <Link to={backPath}><ArrowLeft className="h-5 w-5" /></Link>
            </Button>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-blue-600 font-black text-white">F</span>
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.16em] text-blue-600">{PLATFORM_BRAND.productName}</p>
                  <h1 className="text-xl font-black md:text-2xl">ศูนย์ซิงก์รายการขาย</h1>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-xs font-semibold text-slate-600">
                <Badge variant="secondary"><Store className="mr-1 h-3.5 w-3.5" />{menu?.branch_name || branchId || "ยังไม่ระบุสาขา"}</Badge>
                <Badge variant="secondary">Counter {device?.device_code || "-"}</Badge>
                <Badge variant="secondary">กะ {menu?.shift_id ? menu.shift_id.slice(-8) : "-"}</Badge>
                <Badge variant="secondary"><UserRoundCheck className="mr-1 h-3.5 w-3.5" />{staffName(user)}</Badge>
                <Badge variant="outline">Company {companyId ? companyId.slice(-8) : "-"}</Badge>
              </div>
            </div>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <Badge className={isOnline ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-300 bg-amber-50 text-amber-800"}>
                {isOnline ? <Wifi className="mr-1 h-3.5 w-3.5" /> : <WifiOff className="mr-1 h-3.5 w-3.5" />}
                {isOnline ? "ออนไลน์" : "ออฟไลน์"}
              </Badge>
              <span className="text-xs text-slate-500">ตรวจล่าสุด {timeOnly(lastCheckedAt)}</span>
              <Button className="min-h-11" disabled={syncDisabled} onClick={() => void runAction("sync")}>
                <RefreshCw className={`h-4 w-4 ${busyAction === "sync" ? "animate-spin" : ""}`} />
                ตรวจและซิงก์
              </Button>
            </div>
          </div>
        </header>

        <section
          role="status"
          className={`rounded-[24px] border p-4 ${isOnline ? "border-blue-200 bg-blue-50 text-blue-950" : "border-amber-300 bg-amber-50 text-amber-950"}`}
        >
          <div className="flex items-start gap-3">
            {isOnline ? <Wifi className="mt-0.5 h-6 w-6 shrink-0" /> : <WifiOff className="mt-0.5 h-6 w-6 shrink-0" />}
            <div className="min-w-0">
              <h2 className="font-black">{isOnline ? "ออนไลน์ — ระบบพร้อมตรวจและส่งคิว" : "ออฟไลน์ — บิลจะเก็บในเครื่องและส่งเมื่อกลับมาออนไลน์"}</h2>
              <p className="mt-1 text-sm">
                {isOnline
                  ? "รายการที่ค้างจะใช้รหัสเดิมเสมอ เพื่อป้องกันการสร้างบิล การชำระเงิน งานครัว สต๊อก และบัญชีซ้ำ"
                  : "ออฟไลน์รับเฉพาะเงินสดสำหรับการขายรับกลับเมื่อสิทธิ์ยังใช้ได้ ส่วน Void คืนเงิน แต้ม เครดิต และช่องทาง Provider ต้องออนไลน์"}
              </p>
              {!isOnline ? (
                <p className="mt-2 text-sm font-bold">
                  สิทธิ์ขายออฟไลน์: {offlineAuthorizationValid ? "พร้อมใช้งาน" : "ไม่พร้อมรับชำระใหม่"}
                  {authExpiresAt ? ` · หมดอายุ ${dateTime(authExpiresAt)}` : " · ยังไม่มีสิทธิ์ที่บันทึกในเครื่อง"}
                </p>
              ) : null}
            </div>
          </div>
        </section>

        <section className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="สรุปสถานะการซิงก์">
          {summaryCards.map((card) => (
            <article key={card.label} className="rounded-[22px] border border-white/80 bg-white/95 p-4 shadow-sm">
              <p className="text-sm font-bold text-slate-500">{card.label}</p>
              <p className={`mt-1 text-3xl font-black ${card.className}`}>{card.value}</p>
              <p className="mt-1 text-xs text-slate-500">{card.hint}</p>
            </article>
          ))}
        </section>

        {loadError ? <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-4 font-semibold text-red-700">{loadError}</div> : null}
        {summary.unknown > 0 || reviewCount > 0 ? (
          <div role="alert" className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-amber-950">
            <p className="flex items-center gap-2 font-black"><AlertTriangle className="h-5 w-5" />มี {summary.unknown + reviewCount} รายการที่ต้องตรวจอย่างระมัดระวัง</p>
            <p className="mt-1 text-sm">สถานะ “ยังไม่ทราบผล” จะตรวจ Server ด้วย Client Operation ID เดิมก่อน ส่วนรายการผิดปกติต้องให้ผู้จัดการตรวจสาเหตุและหลักฐาน</p>
          </div>
        ) : null}

        <section className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(340px,0.9fr)_minmax(460px,1.35fr)]">
          <div className="overflow-hidden rounded-[28px] border border-white/80 bg-white/95 shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-200 p-4">
              <div><h2 className="font-black">คิวในเครื่อง</h2><p className="text-xs text-slate-500">รอผล {activeCount} · ตรวจสอบ {reviewCount}</p></div>
              <Badge variant="outline">{rows.length} รายการ</Badge>
            </div>
            {rows.length === 0 ? (
              <div className="flex min-h-64 flex-col items-center justify-center p-8 text-center text-slate-500">
                <ShieldCheck className="mb-3 h-12 w-12 text-emerald-500" />
                <p className="font-black text-slate-700">ไม่มีรายการค้างในเครื่อง</p>
                <p className="mt-1 text-sm">เมื่อมีบิลออฟไลน์ รายการจะปรากฏที่นี่อัตโนมัติ</p>
              </div>
            ) : (
              <div className="max-h-[610px] space-y-2 overflow-y-auto p-2">
                {rows.map((row) => {
                  const order = orders[row.client_order_id];
                  const meta = STATUS_META[row.status];
                  const Icon = meta.icon;
                  return (
                    <button
                      key={row.client_order_id}
                      type="button"
                      aria-pressed={selectedId === row.client_order_id}
                      className={`min-h-24 w-full rounded-2xl border p-3 text-left transition ${selectedId === row.client_order_id ? "border-blue-400 bg-blue-50 ring-2 ring-blue-100" : "border-slate-200 bg-white hover:border-blue-200 hover:bg-slate-50"}`}
                      onClick={() => setSelectedId(row.client_order_id)}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-lg font-black">{localLabel(row, order)}</span>
                            <Badge variant="outline" className={meta.className}>
                              <Icon className={`mr-1 h-3.5 w-3.5 ${row.status === "syncing" ? "animate-spin" : ""}`} />{meta.shortLabel}
                            </Badge>
                          </div>
                          <p className="mt-1 text-xs text-slate-500">รับเงิน {dateTime(row.created_at)} · ลองแล้ว {row.attempts} ครั้ง</p>
                        </div>
                        <div className="shrink-0 text-right">
                          <p className="font-black">฿{money(order?.total_amount)}</p>
                          <p className="text-xs text-slate-500">{paymentLabel(order?.payment_method)}</p>
                        </div>
                      </div>
                      {row.last_error ? <p className="mt-2 line-clamp-2 rounded-xl bg-red-50 px-2 py-1 text-xs text-red-700">{row.last_error}</p> : null}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div className="flex min-h-[420px] flex-col overflow-hidden rounded-[28px] border border-white/80 bg-white/95 shadow-sm">
            {!selectedRow || !selectedMeta ? (
              <div className="flex flex-1 flex-col items-center justify-center p-8 text-center text-slate-500">
                <ReceiptText className="mb-3 h-12 w-12" />
                <p className="font-black text-slate-700">เลือกรายการเพื่อดูรายละเอียด</p>
              </div>
            ) : (
              <>
                <div className="border-b border-slate-200 p-4 md:p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">รายละเอียดรายการ</p>
                      <h2 className="mt-1 text-2xl font-black">{localLabel(selectedRow, selectedOrder)}</h2>
                      <p className="mt-1 text-sm text-slate-500">เลขขาย Server: {selectedOrder?.sale_order_number?.startsWith("LOCAL-") ? "ยังไม่ได้รับ" : selectedOrder?.sale_order_number || "ยังไม่ได้รับ"}</p>
                    </div>
                    <Badge variant="outline" className={`${selectedMeta.className} px-3 py-1.5`}>
                      <selectedMeta.icon className={`mr-1.5 h-4 w-4 ${selectedRow.status === "syncing" ? "animate-spin" : ""}`} />
                      {selectedMeta.label}
                    </Badge>
                  </div>
                  <p className="mt-3 rounded-xl bg-slate-50 p-3 text-sm text-slate-700">{selectedMeta.explanation}</p>
                </div>

                <div className="flex-1 space-y-5 overflow-y-auto p-4 md:p-5">
                  <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
                    <div className="rounded-2xl bg-slate-50 p-3"><p className="text-xs text-slate-500">Counter</p><p className="mt-1 font-bold">{selectedRow.station_key || device?.device_code || "-"}</p></div>
                    <div className="rounded-2xl bg-slate-50 p-3"><p className="text-xs text-slate-500">กะ</p><p className="mt-1 truncate font-bold">{selectedRow.shift_id ? selectedRow.shift_id.slice(-8) : "-"}</p></div>
                    <div className="rounded-2xl bg-slate-50 p-3"><p className="text-xs text-slate-500">พนักงาน</p><p className="mt-1 truncate font-bold">{staffName(user)}</p></div>
                    <div className="rounded-2xl bg-slate-50 p-3"><p className="text-xs text-slate-500">ลองส่ง</p><p className="mt-1 font-bold">{selectedRow.attempts} ครั้ง</p></div>
                  </div>

                  <div>
                    <h3 className="font-black">รายการอาหาร</h3>
                    {selectedOrder?.items.length ? (
                      <div className="mt-2 divide-y divide-slate-100 rounded-2xl border border-slate-200">
                        {selectedOrder.items.map((item, index) => (
                          <div key={`${item.product_id}-${index}`} className="flex justify-between gap-4 p-3 text-sm">
                            <div><p className="font-bold">{item.qty} × {item.product_name}</p>{item.special_request ? <p className="text-xs text-slate-500">{item.special_request}</p> : null}</div>
                            <span className="shrink-0 font-bold">฿{money(Number(item.unit_price) * item.qty)}</span>
                          </div>
                        ))}
                      </div>
                    ) : <p className="mt-2 text-sm text-slate-500">ไม่สามารถอ่านรายละเอียดสินค้าได้ กรุณาให้ผู้ดูแลตรวจสอบ</p>}
                    <div className="mt-3 flex items-center justify-between rounded-2xl bg-blue-600 p-4 text-white">
                      <div><p className="text-xs text-blue-100">ชำระโดย {paymentLabel(selectedOrder?.payment_method)}</p><p className="font-bold">ยอดรวม</p></div>
                      <p className="text-2xl font-black">฿{money(selectedOrder?.total_amount)}</p>
                    </div>
                  </div>

                  <div className="grid gap-3 text-sm md:grid-cols-2">
                    <div className="rounded-2xl border border-slate-200 p-3">
                      <p className="font-black">เวลาและการพิมพ์</p>
                      <dl className="mt-2 space-y-1 text-slate-600">
                        <div className="flex justify-between gap-3"><dt>รับเงิน</dt><dd className="text-right">{dateTime(selectedRow.created_at)}</dd></div>
                        <div className="flex justify-between gap-3"><dt>ปรับล่าสุด</dt><dd className="text-right">{dateTime(selectedRow.updated_at)}</dd></div>
                        <div className="flex justify-between gap-3"><dt>กระทบยอด</dt><dd className="text-right">{dateTime(selectedRow.reconciled_at)}</dd></div>
                        <div className="flex justify-between gap-3"><dt>สลิปลูกค้า</dt><dd className="text-right">{selectedOrder?.customer_slip_printed_at ? "พิมพ์แล้ว" : "ยังไม่พิมพ์"}</dd></div>
                        <div className="flex justify-between gap-3"><dt>สลิปครัว</dt><dd className="text-right">{selectedOrder?.kitchen_slip_printed_at ? "พิมพ์แล้ว" : "ยังไม่พิมพ์"}</dd></div>
                      </dl>
                    </div>
                    <div className="rounded-2xl border border-slate-200 p-3">
                      <p className="font-black">ข้อมูลสำหรับ Support</p>
                      <dl className="mt-2 space-y-1 text-slate-600">
                        <div className="flex justify-between gap-3"><dt>Reference</dt><dd className="font-mono text-xs">{supportReference(selectedRow)}</dd></div>
                        <div className="flex justify-between gap-3"><dt>Sequence</dt><dd>{selectedRow.sequence_no ?? "-"}</dd></div>
                        <div className="flex justify-between gap-3"><dt>Snapshot</dt><dd className="max-w-32 truncate">{selectedRow.price_snapshot_version || "-"}</dd></div>
                        <div className="flex justify-between gap-3"><dt>รหัสปัญหา</dt><dd>{selectedRow.last_error_code || "-"}</dd></div>
                      </dl>
                    </div>
                  </div>

                  {selectedRow.last_error ? (
                    <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
                      <p className="font-black">สาเหตุล่าสุด</p><p className="mt-1">{selectedRow.last_error}</p>
                    </div>
                  ) : null}
                  <div className="rounded-2xl border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
                    การตรวจหรือส่งซ้ำจะใช้ Client Operation ID และ Idempotency Key เดิม จึงไม่สร้างบิลใหม่จากการกดซ้ำ
                  </div>
                </div>

                <div className="sticky bottom-0 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-white p-4">
                  <p className="max-w-xl text-xs text-slate-500">รายการรับเงินจริงจะคงอยู่พร้อมหลักฐานจนกว่าจะได้ผลที่ตรวจสอบได้</p>
                  <div className="flex flex-wrap gap-2">
                    <Button asChild variant="outline"><Link to={backPath}>กลับหน้าขาย</Link></Button>
                    {selectedRow.status === "unknown" ? (
                      <Button disabled={syncDisabled} onClick={() => void runAction("inquiry")}>
                        <CircleHelp className="h-4 w-4" />ตรวจสถานะเดิม
                      </Button>
                    ) : null}
                    {selectedRow.status === "needs_review" ? (
                      <Button disabled={syncDisabled} onClick={() => void runAction("retry")}>
                        <CloudUpload className="h-4 w-4" />แก้แล้ว ลองส่งใหม่
                      </Button>
                    ) : null}
                    {["pending_sync", "server_acknowledged"].includes(selectedRow.status) ? (
                      <Button disabled={syncDisabled} onClick={() => void runAction("sync")}>
                        <RefreshCw className="h-4 w-4" />ลองซิงก์อีกครั้ง
                      </Button>
                    ) : null}
                    {["needs_review", "rejected", "quarantined"].includes(selectedRow.status) ? (
                      <Button variant="outline" disabled className="border-amber-300 bg-amber-50 text-amber-800">เรียกผู้จัดการตรวจสอบ</Button>
                    ) : null}
                  </div>
                </div>
              </>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
