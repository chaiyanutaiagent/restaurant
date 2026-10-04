import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ChefHat,
  Clock3,
  Loader2,
  ReceiptText,
  RefreshCw,
  Search,
  ShoppingBag,
  Users,
  UtensilsCrossed,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { authApi } from "@/lib/api";
import { formatThaiCurrency } from "@/lib/cartUtils";
import { useOnlineStatus } from "@/lib/syncService";
import { useAuthStore } from "@/stores/auth.store";

type SessionRow = {
  id: string;
  status: "open" | "bill_requested" | "closed";
  source_type?: "dine_in" | "quick_service";
  table_name: string | null;
  queue_number: number | null;
  customer_name: string | null;
  customer_phone: string | null;
  note: string | null;
  order_numbers: string[];
  latest_order_number: string | null;
  opened_at: string;
  updated_at: string;
  closed_at: string | null;
  item_count: number;
  pending_count: number;
  cooking_count: number;
  ready_count: number;
  served_count: number;
  total_amount: number;
  sale_order_id: string | null;
};

type SessionDetail = {
  id: string;
  status: SessionRow["status"];
  queue_number: number | null;
  table_name: string | null;
  customer_name: string | null;
  customer_phone: string | null;
  opened_at: string | null;
  closed_at: string | null;
  pending_count: number;
  cooking_count: number;
  ready_count: number;
  served_count: number;
  qr_pending_count: number;
  orders: Array<{
    id: string;
    order_number: string;
    status: string;
    source: string;
    note: string | null;
    created_at: string | null;
    items: Array<{
      id: string;
      product_name: string;
      qty: number;
      unit_price: number;
      special_request: string | null;
      status: string;
    }>;
  }>;
};

type StatusFilter = "active" | "open" | "bill_requested" | "closed" | "all";
type SourceFilter = "all" | "dine_in" | "quick_service";

const STATUS_CONFIG: Record<SessionRow["status"], { label: string; color: string; dot: string }> = {
  open: { label: "กำลังสั่ง", color: "border-blue-200 bg-blue-50 text-blue-800", dot: "bg-blue-500" },
  bill_requested: { label: "เรียกบิลแล้ว", color: "border-amber-300 bg-amber-50 text-amber-900", dot: "bg-amber-500" },
  closed: { label: "ปิดแล้ว", color: "border-slate-200 bg-slate-50 text-slate-600", dot: "bg-slate-400" },
};

const ITEM_STATUS_LABELS: Record<string, string> = {
  pending: "ส่งครัว",
  cooking: "กำลังทำ",
  done: "พร้อม",
  served: "เสิร์ฟแล้ว",
  cancelled: "ยกเลิก",
};

function elapsed(openedAt: string): string {
  const minutes = Math.max(Math.floor((Date.now() - new Date(openedAt).getTime()) / 60_000), 0);
  if (minutes < 60) return `${minutes} นาที`;
  return `${Math.floor(minutes / 60)} ชม. ${minutes % 60} นาที`;
}

function todayStr(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

function sourceOf(session: SessionRow): "dine_in" | "quick_service" {
  return session.source_type === "dine_in" || Boolean(session.table_name) ? "dine_in" : "quick_service";
}

function titleOf(session: SessionRow): string {
  if (session.table_name) return `โต๊ะ ${session.table_name}`;
  if (session.queue_number) return `คิว ${String(session.queue_number).padStart(3, "0")}`;
  return "รับเอง / กลับบ้าน";
}

function isReady(session: SessionRow): boolean {
  return sourceOf(session) === "quick_service"
    && session.status !== "closed"
    && session.pending_count + session.cooking_count === 0
    && session.ready_count > 0;
}

function isHandedOff(session: SessionRow): boolean {
  return sourceOf(session) === "quick_service"
    && session.status !== "closed"
    && session.pending_count + session.cooking_count + session.ready_count === 0
    && session.served_count > 0;
}

export default function FBOrdersPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const isOnline = useOnlineStatus();
  const branchId = useAuthStore((state) => state.branchId);
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const canView = hasPermission("fb.menu.view");
  const canCreateOrder = hasPermission("fb.order.create");
  const canHandoff = canCreateOrder || hasPermission("fb.kitchen.manage");
  const [filterStatus, setFilterStatus] = useState<StatusFilter>("active");
  const [filterSource, setFilterSource] = useState<SourceFilter>("all");
  const [filterDate, setFilterDate] = useState(todayStr());
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const sessionsQuery = useQuery({
    queryKey: ["fb-sessions", branchId, filterDate],
    queryFn: async () => {
      const params = new URLSearchParams({ date: filterDate });
      const response = await authApi.get(`/restaurant/sessions?${params}`);
      return response.data.data as SessionRow[];
    },
    enabled: Boolean(branchId && canView && isOnline),
    refetchInterval: isOnline ? 15_000 : false,
  });

  const allSessions = sessionsQuery.data ?? [];
  const normalizedSearch = search.trim().toLowerCase();
  const sessions = useMemo(() => allSessions.filter((session) => {
    if (filterStatus === "active" && !["open", "bill_requested"].includes(session.status)) return false;
    if (filterStatus !== "active" && filterStatus !== "all" && session.status !== filterStatus) return false;
    if (filterSource !== "all" && sourceOf(session) !== filterSource) return false;
    if (!normalizedSearch) return true;
    const haystack = [
      session.table_name,
      session.queue_number ? String(session.queue_number).padStart(3, "0") : null,
      session.customer_name,
      session.customer_phone,
      session.latest_order_number,
      ...(session.order_numbers ?? []),
    ].filter(Boolean).join(" ").toLowerCase();
    return haystack.includes(normalizedSearch);
  }), [allSessions, filterSource, filterStatus, normalizedSearch]);

  useEffect(() => {
    if (selectedId && sessions.some((session) => session.id === selectedId)) return;
    setSelectedId(sessions[0]?.id ?? null);
  }, [selectedId, sessions]);

  const selected = sessions.find((session) => session.id === selectedId) ?? null;
  const detailQuery = useQuery({
    queryKey: ["fb-session-detail", selected?.id],
    queryFn: async () => (await authApi.get(`/restaurant/sessions/${selected?.id}/detail`)).data.data as SessionDetail,
    enabled: Boolean(selected?.id && isOnline && canView),
    refetchInterval: selected?.status !== "closed" && isOnline ? 15_000 : false,
  });

  const handoffMutation = useMutation({
    mutationFn: async (sessionId: string) => {
      if (!isOnline) throw new Error("ต้องเชื่อมต่อ Server ก่อนส่งมอบ");
      await authApi.post(`/restaurant/pickup-queue/${sessionId}/served`);
      return sessionId;
    },
    onSuccess: async (sessionId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["fb-sessions"] }),
        queryClient.invalidateQueries({ queryKey: ["pickup-queue"] }),
        queryClient.invalidateQueries({ queryKey: ["kitchen-tickets"] }),
      ]);
      toast({ title: "ยืนยันส่งมอบแล้ว", description: "กำลังเปิดบิลพร้อม QR ชำระเงิน" });
      navigate(`/restaurant/session/${sessionId}/checkout?printBill=1`);
    },
    onError: (error: Error) => toast({ title: "ยืนยันส่งมอบไม่สำเร็จ", description: error.message, variant: "destructive" }),
  });

  const stats = useMemo(() => ({
    open: allSessions.filter((session) => session.status === "open").length,
    billRequested: allSessions.filter((session) => session.status === "bill_requested").length,
    ready: allSessions.filter(isReady).length,
    closed: allSessions.filter((session) => session.status === "closed").length,
    dineIn: allSessions.filter((session) => sourceOf(session) === "dine_in").length,
    quickService: allSessions.filter((session) => sourceOf(session) === "quick_service").length,
  }), [allSessions]);

  const isStale = Boolean(sessionsQuery.dataUpdatedAt && Date.now() - sessionsQuery.dataUpdatedAt > 30_000);

  return (
    <div>
      <PageHeader
        title="ศูนย์ออเดอร์"
        subtitle="ออเดอร์ที่ส่งเข้าระบบแล้ว · แยกจากบิลพักก่อนส่งครัว"
        actions={
          <div className="flex items-center gap-2">
            <span className={`inline-flex min-h-11 items-center gap-2 rounded-xl px-3 text-sm font-semibold ${isOnline ? isStale ? "bg-amber-100 text-amber-900" : "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"}`}>
              {isOnline ? <Wifi className="h-4 w-4" /> : <WifiOff className="h-4 w-4" />}
              {isOnline ? isStale ? "ข้อมูลอาจเก่า" : "ออนไลน์" : "ออฟไลน์"}
            </span>
            <Button className="h-11 w-11" variant="outline" size="icon" disabled={!isOnline} onClick={() => void sessionsQuery.refetch()} aria-label="โหลดออเดอร์ใหม่">
              <RefreshCw className={`h-4 w-4 ${sessionsQuery.isFetching ? "animate-spin" : ""}`} />
            </Button>
          </div>
        }
      />

      {!canView ? (
        <StatePanel icon={<AlertCircle className="h-8 w-8" />} title="ไม่มีสิทธิ์ดูศูนย์ออเดอร์" detail="ให้ผู้ดูแลกำหนดสิทธิ์ Restaurant menu view สำหรับสาขานี้" />
      ) : !isOnline && allSessions.length === 0 ? (
        <StatePanel icon={<WifiOff className="h-8 w-8" />} title="ออฟไลน์และไม่มีข้อมูลล่าสุดในหน้านี้" detail="ศูนย์ออเดอร์ไม่สร้าง Action แบบออฟไลน์ กรุณาเชื่อมต่อก่อนดำเนินการ" />
      ) : (
        <div className="space-y-4 rounded-[28px] border border-white/80 bg-white/90 p-4 shadow-[0_18px_60px_rgba(15,23,42,0.08)] backdrop-blur lg:p-5">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label="กำลังสั่ง" value={stats.open} icon={<UtensilsCrossed className="h-5 w-5 text-blue-600" />} />
            <StatCard label="เรียกบิล" value={stats.billRequested} icon={<ReceiptText className="h-5 w-5 text-amber-600" />} urgent={stats.billRequested > 0} />
            <StatCard label="พร้อมส่งมอบ" value={stats.ready} icon={<ChefHat className="h-5 w-5 text-emerald-600" />} />
            <StatCard label="ปิดแล้ว" value={stats.closed} icon={<CheckCircle2 className="h-5 w-5 text-slate-600" />} />
          </div>

          <div className="grid gap-3 xl:grid-cols-[1fr_auto]">
            <label className="relative">
              <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
              <Input className="h-12 pl-11" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="ค้นหาโต๊ะ คิว ลูกค้า เบอร์โทร หรือเลขออเดอร์" />
            </label>
            <input type="date" value={filterDate} max={todayStr()} onChange={(event) => setFilterDate(event.target.value)} className="h-12 rounded-xl border border-slate-200 bg-white px-3 text-sm" aria-label="วันที่ออเดอร์" />
          </div>

          <div className="flex flex-col gap-2 border-b border-slate-200 pb-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex gap-2 overflow-x-auto" role="tablist" aria-label="สถานะออเดอร์">
              {([
                ["active", `กำลังทำงาน ${stats.open + stats.billRequested}`],
                ["open", `กำลังสั่ง ${stats.open}`],
                ["bill_requested", `เรียกบิล ${stats.billRequested}`],
                ["closed", `ปิดแล้ว ${stats.closed}`],
                ["all", `ทั้งหมด ${allSessions.length}`],
              ] as const).map(([key, label]) => (
                <FilterButton key={key} active={filterStatus === key} onClick={() => setFilterStatus(key)}>{label}</FilterButton>
              ))}
            </div>
            <div className="flex gap-2" role="tablist" aria-label="ช่องทางออเดอร์">
              <FilterButton active={filterSource === "all"} onClick={() => setFilterSource("all")}>ทุกช่องทาง</FilterButton>
              <FilterButton active={filterSource === "dine_in"} onClick={() => setFilterSource("dine_in")}>โต๊ะ {stats.dineIn}</FilterButton>
              <FilterButton active={filterSource === "quick_service"} onClick={() => setFilterSource("quick_service")}>รับเอง {stats.quickService}</FilterButton>
            </div>
          </div>

          {sessionsQuery.isLoading ? (
            <div className="grid gap-3 lg:grid-cols-2">{[1, 2, 3, 4].map((item) => <div key={item} className="h-36 animate-pulse rounded-2xl bg-slate-100" />)}</div>
          ) : sessionsQuery.isError ? (
            <StatePanel icon={<AlertCircle className="h-8 w-8" />} title="โหลดออเดอร์ไม่สำเร็จ" detail="ตะกร้าและออเดอร์เดิมไม่ถูกเปลี่ยน" action={<Button className="h-11" variant="outline" onClick={() => void sessionsQuery.refetch()}><RefreshCw className="h-4 w-4" />ลองใหม่</Button>} />
          ) : sessions.length === 0 ? (
            <StatePanel icon={<Search className="h-8 w-8" />} title={normalizedSearch ? "ไม่พบออเดอร์ที่ค้นหา" : "ไม่มีออเดอร์ในเงื่อนไขนี้"} detail="เปลี่ยนตัวกรอง วันที่ หรือคำค้นหาเพื่อดูรายการอื่น" />
          ) : (
            <div className="grid min-h-[34rem] gap-4 lg:grid-cols-[minmax(320px,0.9fr)_minmax(420px,1.1fr)]">
              <div className="max-h-[68vh] space-y-2 overflow-y-auto pr-1" aria-label="รายการออเดอร์">
                {sessions.map((session) => {
                  const config = STATUS_CONFIG[session.status];
                  const ready = isReady(session);
                  return (
                    <button key={session.id} type="button" onClick={() => setSelectedId(session.id)} className={`min-h-32 w-full rounded-2xl border-2 p-4 text-left transition ${selected?.id === session.id ? "border-blue-500 bg-blue-50 ring-2 ring-blue-100" : "border-slate-200 bg-white hover:border-slate-300"}`}>
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={`h-2.5 w-2.5 rounded-full ${config.dot}`} />
                            <span className="text-lg font-black text-slate-950">{titleOf(session)}</span>
                            <span className={`rounded-full border px-2 py-1 text-xs font-bold ${config.color}`}>{config.label}</span>
                            {ready ? <span className="rounded-full bg-emerald-100 px-2 py-1 text-xs font-bold text-emerald-800">พร้อมรับ</span> : null}
                          </div>
                          <div className="mt-2 text-sm text-slate-600">{session.latest_order_number ?? "ยังไม่มีเลขออเดอร์"} · {session.customer_name ?? "ลูกค้าทั่วไป"}</div>
                        </div>
                        <span className="text-lg font-black">{formatThaiCurrency(session.total_amount)}</span>
                      </div>
                      <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-500">
                        <span className="inline-flex items-center gap-1"><Clock3 className="h-3.5 w-3.5" />{session.status === "closed" ? "ปิดแล้ว" : `รอ ${elapsed(session.opened_at)}`}</span>
                        <span className="text-right">{session.item_count} รายการ</span>
                        <span>ส่งครัว {session.pending_count} · ทำ {session.cooking_count}</span>
                        <span className="text-right">พร้อม {session.ready_count} · เสิร์ฟ {session.served_count}</span>
                      </div>
                    </button>
                  );
                })}
              </div>

              <OrderDetailPanel
                session={selected}
                detail={detailQuery.data ?? null}
                loading={detailQuery.isLoading}
                error={detailQuery.isError}
                online={isOnline}
                canCreateOrder={canCreateOrder}
                canHandoff={canHandoff}
                handoffPending={handoffMutation.isPending}
                onRetry={() => void detailQuery.refetch()}
                onOpenDetail={() => selected && navigate(`/restaurant/session/${selected.id}/detail`)}
                onCheckout={() => selected && navigate(`/restaurant/session/${selected.id}/checkout${isHandedOff(selected) ? "?printBill=1" : ""}`)}
                onHandoff={() => selected && handoffMutation.mutate(selected.id)}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function OrderDetailPanel({
  session,
  detail,
  loading,
  error,
  online,
  canCreateOrder,
  canHandoff,
  handoffPending,
  onRetry,
  onOpenDetail,
  onCheckout,
  onHandoff,
}: {
  session: SessionRow | null;
  detail: SessionDetail | null;
  loading: boolean;
  error: boolean;
  online: boolean;
  canCreateOrder: boolean;
  canHandoff: boolean;
  handoffPending: boolean;
  onRetry: () => void;
  onOpenDetail: () => void;
  onCheckout: () => void;
  onHandoff: () => void;
}): JSX.Element {
  if (!session) return <StatePanel icon={<ShoppingBag className="h-8 w-8" />} title="เลือกออเดอร์" detail="รายละเอียดและ Action ที่รองรับจะแสดงด้านนี้" />;
  if (loading) return <div className="min-h-96 animate-pulse rounded-3xl bg-slate-100" />;
  if (error) return <StatePanel icon={<AlertCircle className="h-8 w-8" />} title="โหลดรายละเอียดไม่สำเร็จ" detail="รายการฝั่งซ้ายยังคงเดิม" action={<Button className="h-11" variant="outline" onClick={onRetry}>ลองใหม่</Button>} />;

  const config = STATUS_CONFIG[session.status];
  const ready = isReady(session);
  const handedOff = isHandedOff(session);
  const detailItems = detail?.orders.flatMap((order) => order.items.map((item) => ({ ...item, orderNumber: order.order_number }))) ?? [];
  const canAdd = session.status === "open" && canCreateOrder && online;
  const canCheckout = session.status !== "closed" && canCreateOrder && online;

  return (
    <section className="max-h-[68vh] overflow-y-auto rounded-3xl border border-slate-200 bg-white p-5" aria-label={`รายละเอียด ${titleOf(session)}`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">{sourceOf(session) === "dine_in" ? "Dine in" : "Quick service"}</div>
          <h2 className="mt-1 text-2xl font-black text-slate-950">{titleOf(session)}</h2>
          <div className="mt-2 flex flex-wrap gap-2">
            <span className={`rounded-full border px-3 py-1 text-xs font-bold ${config.color}`}>{config.label}</span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-700">{session.latest_order_number ?? "ไม่มีเลขออเดอร์"}</span>
          </div>
        </div>
        <div className="text-left sm:text-right"><div className="text-2xl font-black">{formatThaiCurrency(session.total_amount)}</div><div className="text-xs text-slate-500">{session.item_count} รายการ · {elapsed(session.opened_at)}</div></div>
      </div>

      {(session.customer_name || session.customer_phone || session.note) ? (
        <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
          <div className="flex items-center gap-2 font-bold"><Users className="h-4 w-4" />{session.customer_name ?? "ลูกค้าทั่วไป"}</div>
          {session.customer_phone ? <div className="mt-1">{session.customer_phone}</div> : null}
          {session.note ? <div className="mt-1 text-slate-500">{session.note}</div> : null}
        </div>
      ) : null}

      <div className="mt-4">
        <h3 className="font-bold text-slate-900">สถานะครัว</h3>
        <div className="mt-2 grid grid-cols-4 gap-2">
          <KitchenStep label="ส่งครัว" value={session.pending_count} active={session.pending_count > 0} />
          <KitchenStep label="กำลังทำ" value={session.cooking_count} active={session.cooking_count > 0} />
          <KitchenStep label="พร้อม" value={session.ready_count} active={session.ready_count > 0} />
          <KitchenStep label="เสิร์ฟแล้ว" value={session.served_count} active={session.served_count > 0} />
        </div>
      </div>

      <div className="mt-4">
        <h3 className="font-bold text-slate-900">รายการอาหาร</h3>
        <div className="mt-2 max-h-64 space-y-2 overflow-y-auto rounded-2xl border border-slate-200 p-3">
          {detailItems.length === 0 ? <p className="py-8 text-center text-sm text-slate-500">ยังไม่มีรายการอาหาร</p> : detailItems.map((item) => (
            <div key={item.id} className="flex items-start justify-between gap-3 rounded-xl bg-slate-50 p-3 text-sm">
              <div>
                <div className="font-semibold text-slate-900">{item.product_name}</div>
                <div className="text-xs text-slate-500">{item.orderNumber} · {ITEM_STATUS_LABELS[item.status] ?? item.status}{item.special_request ? ` · ${item.special_request}` : ""}</div>
              </div>
              <div className="text-right font-bold">×{item.qty}<div>{formatThaiCurrency(item.unit_price * item.qty)}</div></div>
            </div>
          ))}
        </div>
      </div>

      {!online ? <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">ออฟไลน์: ปิด Action ที่เปลี่ยนสถานะทั้งหมด ข้อมูลนี้ใช้ดูเท่านั้น</div> : null}
      {session.status === "bill_requested" ? <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm font-bold text-amber-900">ลูกค้าเรียกบิลแล้ว กรุณาตรวจรายการและดำเนินการชำระเงิน</div> : null}
      {session.status === "closed" ? <div className="mt-4 rounded-xl bg-slate-100 p-3 text-sm text-slate-600">ออเดอร์ปิดแล้ว หน้านี้เป็นข้อมูลอ่านอย่างเดียว</div> : null}

      <div className="mt-5 grid gap-2 sm:grid-cols-2">
        {ready ? <Button className="h-12 bg-emerald-600 hover:bg-emerald-700" disabled={!canHandoff || !online || handoffPending} onClick={onHandoff}>{handoffPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}ลูกค้ารับแล้ว + ออกบิล</Button> : null}
        {handedOff || session.status === "bill_requested" || sourceOf(session) === "dine_in" ? <Button className="h-12" disabled={!canCheckout} onClick={onCheckout}><ReceiptText className="h-4 w-4" />{session.status === "bill_requested" || handedOff ? "ออกบิล / รับเงิน" : "ไปหน้า Checkout"}</Button> : null}
        <Button className="h-12" variant="outline" disabled={!canAdd && session.status !== "closed"} onClick={onOpenDetail}>{session.status === "closed" ? "ดูรายละเอียด" : "เปิดออเดอร์ / สั่งเพิ่ม"}<ArrowRight className="h-4 w-4" /></Button>
      </div>
      {!canAdd && session.status === "bill_requested" ? <p className="mt-2 text-xs text-slate-500">ลูกค้าเรียกบิลแล้ว Contract ไม่อนุญาตให้สั่งเพิ่ม</p> : null}
    </section>
  );
}

function FilterButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }): JSX.Element {
  return <button type="button" onClick={onClick} className={`min-h-11 shrink-0 rounded-xl px-3 text-sm font-semibold transition ${active ? "bg-slate-950 text-white" : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"}`}>{children}</button>;
}

function KitchenStep({ label, value, active }: { label: string; value: number; active: boolean }): JSX.Element {
  return <div className={`rounded-xl border p-2 text-center ${active ? "border-blue-300 bg-blue-50 text-blue-800" : "border-slate-200 bg-slate-50 text-slate-500"}`}><div className="text-lg font-black">{value}</div><div className="text-[11px] font-semibold">{label}</div></div>;
}

function StatCard({ label, value, icon, urgent = false }: { label: string; value: number; icon: React.ReactNode; urgent?: boolean }): JSX.Element {
  return <div className={`rounded-2xl border bg-white p-4 ${urgent ? "border-amber-400 shadow-md" : "border-slate-200"}`}><div className="flex items-center justify-between">{icon}{urgent ? <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-amber-500" /> : null}</div><p className="mt-2 text-3xl font-black text-slate-950">{value}</p><p className="text-xs text-slate-500">{label}</p></div>;
}

function StatePanel({ icon, title, detail, action }: { icon: JSX.Element; title: string; detail: string; action?: JSX.Element }): JSX.Element {
  return <div className="flex min-h-64 flex-col items-center justify-center gap-3 rounded-3xl border border-dashed border-slate-300 bg-white/80 p-6 text-center text-slate-500">{icon}<div><div className="font-bold text-slate-800">{title}</div><div className="mt-1 text-sm">{detail}</div></div>{action}</div>;
}
