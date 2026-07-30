import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, BarChart3, CheckCircle2, ClipboardCheck, History, Loader2, LogOut, Minus, PackagePlus, Plus, ReceiptText, RotateCcw, Send, Warehouse } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { useLogout } from "@/hooks/useAuth";
import { hasUnsyncedRestaurantOrders, syncRestaurantPendingOrders } from "@/lib/restaurantOffline";
import { useOnlineStatus } from "@/lib/syncService";
import {
  wapApi,
  type CentralOrder,
  type CentralOrderItem,
  type DailyCentralOrderSummary,
  type ReplenishmentSuggestionItem,
  type WapShiftCloseProduct,
  type WapShiftCloseSummary,
} from "@/lib/wapApi";

type ViewMode = "summary" | "purchase" | "history";
type PurchaseItem = {
  key: string;
  product_id: string | null;
  name: string;
  sku: string;
  system_qty: number;
  order_qty: number;
  unit: string;
  source?: string | null;
  store_on_hand_qty: number;
  received_today_qty: number;
  yesterday_usage_qty: number;
  average_7_day_qty: number;
  forecast_qty: number;
  confirmed_incoming_qty: number;
  safety_stock_qty: number;
  safety_stock_percent: number;
  pack_size: number;
  forecast_method: string | null;
  target_date: string | null;
  has_calculation: boolean;
};

function money(value: number | string): string {
  return Number(value || 0).toLocaleString("th-TH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatQty(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toLocaleString("th-TH", { maximumFractionDigits: 2 });
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  return new Date(value).toLocaleString("th-TH", { dateStyle: "medium", timeStyle: "short" });
}

function getErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "response" in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response;
    if (response?.data?.detail) return response.data.detail;
  }
  return error instanceof Error ? error.message : "ทำรายการไม่สำเร็จ";
}

function normalizeProducts(products: WapShiftCloseProduct[]): WapShiftCloseProduct[] {
  return products;
}

function toPurchaseItems(products: WapShiftCloseProduct[]): PurchaseItem[] {
  return products.map((item) => ({
    key: `${item.product_id}:${item.unit ?? "ชิ้น"}`,
    product_id: item.product_id,
    name: item.product_name,
    sku: item.sku,
    system_qty: Math.ceil(item.qty),
    order_qty: Math.ceil(item.qty),
    unit: item.unit ?? "ชิ้น",
    source: item.source,
    store_on_hand_qty: 0,
    received_today_qty: 0,
    yesterday_usage_qty: item.qty,
    average_7_day_qty: 0,
    forecast_qty: item.qty,
    confirmed_incoming_qty: 0,
    safety_stock_qty: 0,
    safety_stock_percent: 0,
    pack_size: 1,
    forecast_method: null,
    target_date: null,
    has_calculation: false,
  }));
}

function toSuggestedPurchaseItems(items: ReplenishmentSuggestionItem[]): PurchaseItem[] {
  return items.map((item) => ({
    key: `${item.product_id}:${item.unit}`,
    product_id: item.product_id,
    name: item.product_name,
    sku: item.sku,
    system_qty: item.suggested_qty,
    order_qty: item.suggested_qty,
    unit: item.unit,
    source: item.source,
    store_on_hand_qty: item.store_on_hand_qty,
    received_today_qty: item.received_today_qty,
    yesterday_usage_qty: item.yesterday_usage_qty,
    average_7_day_qty: item.average_7_day_qty,
    forecast_qty: item.forecast_qty,
    confirmed_incoming_qty: item.confirmed_incoming_qty,
    safety_stock_qty: item.safety_stock_qty,
    safety_stock_percent: item.safety_stock_percent,
    pack_size: item.pack_size,
    forecast_method: item.forecast_method,
    target_date: item.target_date,
    has_calculation: true,
  }));
}

function toExistingOrderItems(items: CentralOrderItem[]): PurchaseItem[] {
  return items.map((item) => ({
    key: `${item.product_id ?? item.sku}:${item.unit}`,
    product_id: item.product_id,
    name: item.product_name,
    sku: item.sku,
    system_qty: item.system_qty,
    order_qty: item.requested_qty,
    unit: item.unit,
    source: item.source,
    store_on_hand_qty: 0,
    received_today_qty: 0,
    yesterday_usage_qty: 0,
    average_7_day_qty: 0,
    forecast_qty: 0,
    confirmed_incoming_qty: item.in_transit_qty ?? 0,
    safety_stock_qty: 0,
    safety_stock_percent: 0,
    pack_size: 1,
    forecast_method: null,
    target_date: null,
    has_calculation: false,
  }));
}

export default function WapShiftClosePage(): JSX.Element {
  const { brandSlug } = useParams<{ brandSlug?: string }>();
  const { toast } = useToast();
  const logout = useLogout();
  const isOnline = useOnlineStatus();
  const [mode, setMode] = useState<ViewMode>("summary");
  const [purchaseItems, setPurchaseItems] = useState<PurchaseItem[]>([]);
  const [closedSummary, setClosedSummary] = useState<WapShiftCloseSummary | null>(null);
  const [closedAt, setClosedAt] = useState<string | null>(null);
  const [centralOrder, setCentralOrder] = useState<CentralOrder | null>(null);
  const [isSubmittingOrder, setIsSubmittingOrder] = useState(false);

  const summaryQuery = useQuery({
    queryKey: ["wap-shift-close-summary", brandSlug ?? "legacy"],
    queryFn: async () => (await wapApi.shiftCloseSummary(undefined, brandSlug)).data.data,
  });
  const historyQuery = useQuery({
    queryKey: ["wap-shift-closures", brandSlug ?? "legacy"],
    queryFn: async () => (await wapApi.shiftClosures(brandSlug)).data.data,
  });
  const storeBase = brandSlug ? `/store/${brandSlug}` : "/restaurant";

  const summary = closedSummary ?? summaryQuery.data;
  const dailyOrderQuery = useQuery({
    queryKey: ["wap-daily-central-order-summary", brandSlug ?? "legacy", summary?.date ?? "today"],
    queryFn: async () => (await wapApi.dailyCentralOrderSummary(summary?.date, brandSlug)).data.data,
  });
  const dailySummary = dailyOrderQuery.data as DailyCentralOrderSummary | undefined;
  const replenishmentQuery = useQuery({
    queryKey: ["wap-replenishment-suggestion", brandSlug ?? "legacy", summary?.date ?? "today"],
    queryFn: async () => (await wapApi.replenishmentSuggestion(brandSlug ?? "", summary?.date)).data.data,
    enabled: Boolean(brandSlug && summary?.date),
  });
  const storeStockQuery = useQuery({
    queryKey: ["wap-store-stock-close-summary", brandSlug ?? "legacy", summary?.date ?? "today"],
    queryFn: async () => (await wapApi.storeStockDaily(brandSlug ?? "", summary?.date)).data.data,
    enabled: Boolean(brandSlug && summary?.date),
  });
  const storeStockItems = storeStockQuery.data?.items ?? [];
  const products = useMemo(() => normalizeProducts(summary?.products ?? []), [summary?.products]);
  const cashierSales = summary?.cashier_sales ?? [];
  const displayedClosedAt = closedAt ?? (summary?.closed_at ? formatDateTime(summary.closed_at) : null);
  const hasClosedShift = Boolean(summary?.closure_id);
  const existingCentralOrderNumber = dailySummary?.existing_order?.order_number ?? summary?.existing_closure?.central_order_number ?? null;
  const submittedCentralOrderNumber = centralOrder?.order_number ?? existingCentralOrderNumber;
  const submittedCentralOrderLabel = submittedCentralOrderNumber ?? "ส่งแล้ว";
  const hasSubmittedCentralOrder = Boolean(centralOrder || dailySummary?.existing_order || summary?.existing_closure?.central_order_id);
  const totalRequestedQty = purchaseItems.reduce((sum, item) => sum + item.order_qty, 0);
  const changedRequestCount = purchaseItems.filter((item) => item.order_qty !== item.system_qty).length;
  const activePurchaseCount = purchaseItems.filter((item) => item.order_qty > 0).length;
  const hasCurrentRoundSales = (summary?.total_orders ?? 0) > 0 || products.length > 0;
  const hasLaterSalesAfterDailyOrder = hasSubmittedCentralOrder && !hasClosedShift && hasCurrentRoundSales;

  useEffect(() => {
    if (dailySummary?.existing_order?.items) {
      setPurchaseItems(toExistingOrderItems(dailySummary.existing_order.items));
      return;
    }
    if (brandSlug) {
      setPurchaseItems(toSuggestedPurchaseItems(replenishmentQuery.data?.items ?? []));
      return;
    }
    setPurchaseItems(toPurchaseItems(dailySummary?.purchase_items ?? []));
  }, [brandSlug, dailySummary?.existing_order, dailySummary?.purchase_items, replenishmentQuery.data?.items]);

  async function handleCloseShift(): Promise<void> {
    if (!isOnline) {
      toast({
        title: "ยังปิดกะแบบออฟไลน์ไม่ได้",
        description: "ต่ออินเทอร์เน็ตเพื่อซิงก์ยอดขายและปิดกะให้ยอดตรงกันก่อน",
        variant: "destructive",
      });
      return;
    }
    await syncRestaurantPendingOrders(brandSlug);
    if (await hasUnsyncedRestaurantOrders(brandSlug)) {
      toast({
        title: "ยังมีรายการขายที่ส่งไม่สำเร็จ",
        description: "กลับไปหน้าขายและตรวจรายการรอส่ง/ต้องตรวจสอบก่อนปิดกะ",
        variant: "destructive",
      });
      return;
    }
    const confirmed = window.confirm("ยืนยันปิดกะตอนนี้หรือไม่? ระบบจะสรุปยอดขายล่าสุด ณ เวลาที่กดปิดกะ");
    if (!confirmed) return;
    try {
      const response = await wapApi.closeShift(brandSlug);
      const latest = response.data.data;
      setClosedSummary(latest);
      setCentralOrder(null);
      setClosedAt(formatDateTime(latest.closed_at ?? new Date().toISOString()));
      setMode("purchase");
      await historyQuery.refetch();
      await summaryQuery.refetch();
      await dailyOrderQuery.refetch();
      if (brandSlug) await replenishmentQuery.refetch();
      if (brandSlug) await storeStockQuery.refetch();
    } catch (error) {
      toast({ title: "ปิดกะไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
    }
  }

  async function handleSubmitCentralOrder(): Promise<void> {
    if (!dailySummary || dailySummary.closure_count === 0) {
      toast({
        title: "ยังไม่มีรอบปิดกะ",
        description: "ระบบจะสร้างใบสั่งรวมวันนี้ได้หลังมีอย่างน้อยหนึ่งรอบปิดกะ",
        variant: "destructive",
      });
      return;
    }
    const activeItems = purchaseItems.filter((item) => item.order_qty > 0);
    if (activeItems.length === 0) {
      toast({ title: "ไม่มีรายการสั่งสินค้า", variant: "destructive" });
      return;
    }
    const confirmed = window.confirm("ยืนยันส่งรายการสั่งสินค้าให้ครัวกลางหรือไม่? หลังส่งแล้วจำนวนจะเข้าสู่ขั้นตอนอนุมัติของครัวกลาง");
    if (!confirmed) return;
    setIsSubmittingOrder(true);
    try {
      const response = await wapApi.submitDailyCentralOrder({
        items: activeItems.map((item) => ({
          product_id: item.product_id,
          sku: item.sku,
          product_name: item.name,
          unit: item.unit,
          system_qty: item.system_qty,
          requested_qty: item.order_qty,
          source: item.source,
        })),
      }, brandSlug);
      setCentralOrder(response.data.data);
      toast({ title: `ส่งใบสั่งสินค้าแล้ว: ${response.data.data.order_number}` });
      await dailyOrderQuery.refetch();
      await historyQuery.refetch();
    } catch (error) {
      toast({ title: "ส่งใบสั่งสินค้าไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
    } finally {
      setIsSubmittingOrder(false);
    }
  }

  function updateOrderQty(key: string, delta: number): void {
    setPurchaseItems((prev) =>
      prev.map((item) => item.key === key ? { ...item, order_qty: Math.max(item.order_qty + delta, 0) } : item)
    );
  }

  function setOrderQty(key: string, value: string): void {
    const nextQty = Math.max(Number(value || 0), 0);
    setPurchaseItems((prev) =>
      prev.map((item) => item.key === key ? { ...item, order_qty: Number.isFinite(nextQty) ? nextQty : 0 } : item)
    );
  }

  function resetOrderQty(key: string): void {
    setPurchaseItems((prev) =>
      prev.map((item) => item.key === key ? { ...item, order_qty: item.system_qty } : item)
    );
  }

  const totalSoldQty = products.reduce((sum, item) => sum + item.qty, 0);
  return (
    <div className="mx-auto flex min-h-full max-w-4xl flex-col gap-4">
      <header className="rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 p-4">
          <div className="flex min-w-0 items-center gap-3">
            <Button asChild variant="outline" size="icon" className="h-10 w-10 shrink-0">
              <Link to={`${storeBase}/orders`} aria-label="กลับหน้ารับออเดอร์">
                <ArrowLeft className="h-5 w-5" />
              </Link>
            </Button>
            <div className="min-w-0">
              <h1 className="truncate text-xl font-black text-slate-950">ปิดกะ</h1>
              <p className="truncate text-sm text-slate-500">สรุปงานขายประจำวันและรายการสั่งสินค้า</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className="hidden rounded-full bg-slate-100 px-3 py-1.5 text-sm font-semibold text-slate-700 sm:inline-flex">
              {displayedClosedAt ? `ปิดกะรอบ ${summary?.current_round_no ?? "-"} · ${displayedClosedAt}` : `รอบ ${summary?.current_round_no ?? 1} · ${summary?.date ?? "-"}`}
            </span>
            <Button
              type="button"
              className="h-10 bg-emerald-600 hover:bg-emerald-700"
              disabled={summaryQuery.isFetching || hasClosedShift}
              onClick={() => void handleCloseShift()}
            >
              {summaryQuery.isFetching ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-2 h-4 w-4" />}
              {hasClosedShift ? "ปิดกะแล้ว" : "ปิดกะ"}
            </Button>
          </div>
        </div>
        <div className="grid gap-2 border-b border-slate-200 bg-slate-50 p-3 sm:grid-cols-3">
          <div className={`rounded-md border px-3 py-2 ${hasClosedShift ? "border-emerald-200 bg-emerald-50" : "border-slate-200 bg-white"}`}>
            <p className="text-xs font-semibold text-slate-500">1. ปิดกะรอบ {summary?.current_round_no ?? 1}</p>
            <p className={`mt-1 font-black ${hasClosedShift ? "text-emerald-700" : "text-slate-700"}`}>{hasClosedShift ? "เสร็จแล้ว" : "รอดำเนินการ"}</p>
          </div>
          <div className={`rounded-md border px-3 py-2 ${hasClosedShift && !hasSubmittedCentralOrder ? "border-orange-200 bg-orange-50" : "border-slate-200 bg-white"}`}>
            <p className="text-xs font-semibold text-slate-500">2. รวมยอดสั่งวันนี้</p>
            <p className={`mt-1 font-black ${hasClosedShift && !hasSubmittedCentralOrder ? "text-orange-700" : "text-slate-700"}`}>
              {hasSubmittedCentralOrder ? "ล็อกแล้ว" : (dailySummary?.closure_count ?? 0) > 0 ? "พร้อมปรับ" : "รอปิดกะ"}
            </p>
          </div>
          <div className={`rounded-md border px-3 py-2 ${hasSubmittedCentralOrder ? "border-blue-200 bg-blue-50" : "border-slate-200 bg-white"}`}>
            <p className="text-xs font-semibold text-slate-500">3. ส่งครัวกลาง</p>
            <p className={`mt-1 font-black ${hasSubmittedCentralOrder ? "text-blue-700" : "text-slate-700"}`}>
              {hasSubmittedCentralOrder ? submittedCentralOrderLabel : "ยังไม่ส่ง"}
            </p>
          </div>
        </div>
        {displayedClosedAt ? (
          <div className="flex flex-col gap-3 border-b border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-800 sm:flex-row sm:items-center sm:justify-between">
            <span>ปิดกะรอบ {summary?.current_round_no ?? "-"} แล้ว ระบบล็อกสรุปยอดขาย ณ {displayedClosedAt}</span>
            <Button type="button" variant="outline" className="h-9 border-emerald-300 bg-white text-emerald-800 hover:bg-emerald-100" onClick={logout}>
              <LogOut className="h-4 w-4" />
              ออกจากระบบ
            </Button>
          </div>
        ) : null}
        {hasSubmittedCentralOrder ? (
          <div className={`flex items-start gap-3 border-b px-4 py-3 text-sm ${hasLaterSalesAfterDailyOrder ? "border-amber-200 bg-amber-50 text-amber-900" : "border-blue-200 bg-blue-50 text-blue-900"}`}>
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div className="space-y-1">
              <p className="font-black">ส่งใบสั่งรวมวันนี้แล้ว: {submittedCentralOrderLabel}</p>
              <p className="font-semibold">
                {hasLaterSalesAfterDailyOrder
                  ? `รอบ ${summary?.current_round_no ?? "-"} ยังปิดยอดขายได้ตามปกติ แต่รายการเติมของวันนี้ถูกล็อกแล้ว หากต้องเติมเพิ่มให้รอขั้นตอน correction order จากผู้ดูแล`
                  : "จำนวนสั่งถูกล็อกเพื่อกันส่งซ้ำ พนักงานยังขายและปิดรอบถัดไปได้ตามปกติ"}
              </p>
            </div>
          </div>
        ) : null}
        <div className="grid grid-cols-3 gap-2 p-3">
          <Button
            type="button"
            variant={mode === "summary" ? "default" : "outline"}
            className={`h-12 ${mode === "summary" ? "bg-slate-950 hover:bg-slate-800" : ""}`}
            onClick={() => setMode("summary")}
          >
            <ClipboardCheck className="mr-2 h-4 w-4" />
            สรุปยอดขาย
          </Button>
          <Button
            type="button"
            variant={mode === "purchase" ? "default" : "outline"}
            className={`h-12 ${mode === "purchase" ? "bg-orange-600 hover:bg-orange-700" : ""}`}
            onClick={() => setMode("purchase")}
          >
            <PackagePlus className="mr-2 h-4 w-4" />
            สั่งสินค้า
          </Button>
          <Button
            type="button"
            variant={mode === "history" ? "default" : "outline"}
            className={`h-12 ${mode === "history" ? "bg-emerald-600 hover:bg-emerald-700" : ""}`}
            onClick={() => setMode("history")}
          >
            <History className="mr-2 h-4 w-4" />
            ประวัติ
          </Button>
        </div>
      </header>

      {summaryQuery.isLoading ? (
        <div className="flex h-72 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          โหลดสรุปปิดกะ
        </div>
      ) : summaryQuery.isError ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-6 text-center font-semibold text-rose-700">
          โหลดสรุปปิดกะไม่สำเร็จ
        </div>
      ) : mode === "summary" ? (
        <section className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-500">ยอดขายรอบนี้</p>
              <p className="mt-2 text-3xl font-black text-emerald-700">฿{money(summary?.total_amount ?? 0)}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-500">จำนวนบิล</p>
              <p className="mt-2 text-3xl font-black text-slate-950">{summary?.total_orders ?? 0}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-500">จำนวนสินค้าที่ขายรอบนี้</p>
              <p className="mt-2 text-3xl font-black text-slate-950">{formatQty(totalSoldQty)}</p>
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white">
            <div className="flex items-center gap-2 border-b border-slate-200 p-4">
              <ReceiptText className="h-5 w-5 text-slate-700" />
              <h2 className="font-bold text-slate-950">สินค้าที่ขายรอบนี้</h2>
            </div>
            <div className="space-y-2 p-4">
              {products.length > 0 ? products.map((item) => (
                <div key={item.product_id} className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-4 py-3">
                  <div className="min-w-0">
                    <p className="font-bold text-slate-950">{item.product_name}</p>
                    <p className="text-sm text-slate-500">{formatQty(item.qty)} {item.unit ?? "ชิ้น"}</p>
                  </div>
                  <p className="shrink-0 text-lg font-black text-emerald-700">฿{money(item.amount)}</p>
                </div>
              )) : (
                <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-slate-500">ยังไม่มียอดขายรอบนี้</div>
              )}
            </div>
          </div>

          {brandSlug ? (
            <div className="rounded-lg border border-slate-200 bg-white">
              <div className="flex items-center justify-between gap-3 border-b border-slate-200 p-4">
                <div className="flex items-center gap-2">
                  <Warehouse className="h-5 w-5 text-slate-700" />
                  <div><h2 className="font-bold text-slate-950">สรุป STORE-STOCK วันนี้</h2><p className="text-sm text-slate-500">รับเข้า · ใช้ตามยอดขาย · ของเสีย · ยอดคงเหลือ</p></div>
                </div>
                <Button asChild size="sm" variant="outline"><Link to={`${storeBase}/stock`}>ตรวจนับ / ดูทั้งหมด</Link></Button>
              </div>
              {storeStockQuery.isLoading ? <div className="flex h-28 items-center justify-center text-slate-500"><Loader2 className="mr-2 h-4 w-4 animate-spin" />โหลด stock</div> : storeStockItems.length === 0 ? <div className="p-6 text-center text-slate-500">ยังไม่มีรายการใน STORE-STOCK</div> : (
                <div className="divide-y divide-slate-100">
                  {storeStockItems.map((item) => <div key={item.product_id} className={`grid grid-cols-[1fr_repeat(4,auto)] items-center gap-3 px-4 py-3 text-sm ${item.is_negative ? "bg-red-50" : ""}`}><div className="min-w-0"><p className="truncate font-bold text-slate-950">{item.product_name}</p><p className="text-xs text-slate-500">{item.unit_code ?? "หน่วย"}</p></div><div className="text-right"><p className="text-xs text-slate-500">รับ</p><p className="font-bold text-emerald-700">{formatQty(item.received_qty)}</p></div><div className="text-right"><p className="text-xs text-slate-500">ขาย</p><p className="font-bold text-blue-700">{formatQty(item.used_sales_qty)}</p></div><div className="text-right"><p className="text-xs text-slate-500">เสีย</p><p className="font-bold text-amber-700">{formatQty(item.waste_qty)}</p></div><div className="text-right"><p className="text-xs text-slate-500">เหลือ</p><p className={`font-black ${item.is_negative ? "text-red-700" : "text-slate-950"}`}>{formatQty(item.current_qty)}</p></div></div>)}
                </div>
              )}
            </div>
          ) : null}

          <div className="rounded-lg border border-slate-200 bg-white">
            <div className="flex items-center gap-2 border-b border-slate-200 p-4">
              <BarChart3 className="h-5 w-5 text-slate-700" />
              <h2 className="font-bold text-slate-950">ยอดขายตามพนักงาน</h2>
            </div>
            <div className="divide-y divide-slate-100">
              {cashierSales.length > 0 ? cashierSales.map((row) => (
                <div key={row.user_id} className="grid gap-2 px-4 py-3 sm:grid-cols-[1fr_auto] sm:items-center">
                  <div className="min-w-0">
                    <p className="font-bold text-slate-950">{row.employee_name}</p>
                    <p className="text-sm text-slate-500">{row.username} · {row.order_count} บิล</p>
                  </div>
                  <p className="text-lg font-black text-emerald-700">฿{money(row.total_amount)}</p>
                </div>
              )) : (
                <div className="p-8 text-center text-slate-500">ยังไม่มียอดขายตามพนักงาน</div>
              )}
            </div>
          </div>
        </section>
      ) : mode === "history" ? (
        <section className="rounded-lg border border-slate-200 bg-white">
          <div className="flex items-center gap-2 border-b border-slate-200 p-4">
            <History className="h-5 w-5 text-slate-700" />
            <h2 className="font-bold text-slate-950">ประวัติปิดกะ</h2>
          </div>
          {historyQuery.isLoading ? (
            <div className="flex h-56 items-center justify-center text-slate-500">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              โหลดประวัติปิดกะ
            </div>
          ) : (historyQuery.data ?? []).length > 0 ? (
            <div className="divide-y divide-slate-100">
              {historyQuery.data?.map((closure) => (
                <div key={closure.id} className="space-y-3 px-4 py-4">
                  <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-center">
                    <div className="min-w-0">
                      <p className="font-bold text-slate-950">{closure.business_date} · รอบ {closure.round_no ?? "-"}</p>
                      <p className="text-sm text-slate-500">
                        ปิดโดย {closure.closed_by_name ?? "พนักงาน"} · {formatDateTime(closure.closed_at)}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-lg font-black text-emerald-700">฿{money(closure.total_amount)}</p>
                      <p className="text-sm text-slate-500">{closure.total_orders} บิล</p>
                    </div>
                  </div>
                  <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
                    {closure.central_order_number ? (
                      <span>ใบสั่งสินค้า {closure.central_order_number} · {closure.central_order_status}</span>
                    ) : (
                      <span>ยังไม่ส่งใบสั่งสินค้า</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-8 text-center text-slate-500">ยังไม่มีประวัติปิดกะ</div>
          )}
        </section>
      ) : (
        <section className="rounded-lg border border-slate-200 bg-white">
          <div className="flex items-center justify-between gap-3 border-b border-slate-200 p-4">
            <div>
              <h2 className="font-bold text-slate-950">รายการสั่งสินค้า</h2>
              <p className="text-sm text-slate-500">
                {hasSubmittedCentralOrder
                  ? "ใบสั่งรวมวันนี้ถูกส่งแล้ว รายการนี้ใช้ตรวจสอบย้อนหลังเท่านั้น"
                  : brandSlug
                    ? `ระบบคำนวณสำหรับรับวันที่ ${replenishmentQuery.data?.default_target_date ?? "วันถัดไป"} และให้ร้านแก้จำนวนก่อนส่งได้`
                    : "รวมจากทุกกะที่ปิดแล้วของวันนี้ ส่งครัวกลางได้วันละครั้ง"}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span className="hidden rounded-full bg-orange-100 px-3 py-1.5 text-sm font-black text-orange-700 sm:inline-flex">
                {activePurchaseCount} รายการ / {formatQty(totalRequestedQty)} หน่วย
              </span>
              <Button
                type="button"
                className="h-10 bg-orange-600 hover:bg-orange-700"
                disabled={(dailySummary?.closure_count ?? 0) === 0 || purchaseItems.length === 0 || isSubmittingOrder || hasSubmittedCentralOrder}
                onClick={() => void handleSubmitCentralOrder()}
              >
                {isSubmittingOrder ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
                {hasSubmittedCentralOrder ? "ส่งแล้ว" : "ส่งรวมวันนี้"}
              </Button>
            </div>
          </div>
          {(dailySummary?.closure_count ?? 0) === 0 ? (
            <div className="border-b border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-800">
              กดปิดกะอย่างน้อยหนึ่งรอบก่อน เพื่อสร้างยอดรวมสำหรับส่งครัวกลาง
            </div>
          ) : null}
          {(dailySummary?.closure_count ?? 0) > 0 && !hasSubmittedCentralOrder ? (
            <div className="border-b border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-800">
              มี {dailySummary?.closure_count ?? 0} รอบปิดกะในวันนี้ ระบบใช้ยอดคงเหลือจริงและพฤติกรรมใช้ของเพื่อแนะนำใบสั่งเดียว
            </div>
          ) : null}
          {brandSlug && replenishmentQuery.isLoading ? (
            <div className="flex items-center border-b border-slate-200 px-4 py-3 text-sm font-semibold text-slate-600">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              กำลังคำนวณยอดแนะนำจาก STORE-STOCK
            </div>
          ) : null}
          {brandSlug && replenishmentQuery.isError ? (
            <div className="border-b border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-800">
              คำนวณยอดแนะนำไม่สำเร็จ: {getErrorMessage(replenishmentQuery.error)}
            </div>
          ) : null}
          {hasSubmittedCentralOrder ? (
            <div className="border-b border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
              <p className="font-black">ล็อกใบสั่งรวมวันนี้แล้ว: {submittedCentralOrderLabel}</p>
              <p className="mt-1 font-semibold">
                {hasLaterSalesAfterDailyOrder
                  ? "มีขายรอบใหม่หลังส่งใบสั่งรวมวันนี้ ให้ปิดรอบขายตามปกติเพื่อเก็บยอดพนักงาน แต่ยังไม่ต้องส่งเติมของซ้ำ"
                  : "ถ้ามีขายเพิ่มหลังจากนี้ ให้กลับไปขายต่อและปิดรอบใหม่ได้ ระบบจะเก็บประวัติรอบขาย แต่ยังไม่เปิดส่งเติมของซ้ำในวันเดียวกัน"}
              </p>
            </div>
          ) : null}
          {(dailySummary?.closure_count ?? 0) > 0 && changedRequestCount > 0 && !hasSubmittedCentralOrder ? (
            <div className="border-b border-blue-200 bg-blue-50 px-4 py-3 text-sm font-semibold text-blue-800">
              มี {changedRequestCount} รายการที่ปรับจากจำนวนแนะนำ ตรวจทานก่อนกดยืนยันสั่ง
            </div>
          ) : null}
          <div className="space-y-3 p-4">
            {purchaseItems.length > 0 ? purchaseItems.map((item) => (
              <div key={item.key} className="rounded-lg border border-slate-200 p-4">
                <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
                  <div className="min-w-0">
                    <p className="font-bold text-slate-950">{item.name}</p>
                    <p className="text-sm text-slate-500">
                      ระบบแนะนำ <span className="font-black text-orange-700">{formatQty(item.system_qty)} {item.unit}</span>
                      {item.target_date ? ` · รับวันที่ ${item.target_date}` : ""}
                    </p>
                    {item.has_calculation ? (
                      <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                        <div className="rounded-md bg-slate-50 px-2 py-2">
                          <p className="text-slate-500">ใช้วันล่าสุด</p>
                          <p className="font-black text-slate-800">{formatQty(item.yesterday_usage_qty)} {item.unit}</p>
                        </div>
                        <div className="rounded-md bg-slate-50 px-2 py-2">
                          <p className="text-slate-500">เฉลี่ย 7 วันเปิด</p>
                          <p className="font-black text-slate-800">{formatQty(item.average_7_day_qty)} {item.unit}</p>
                        </div>
                        <div className="rounded-md bg-slate-50 px-2 py-2">
                          <p className="text-slate-500">คงเหลือร้าน</p>
                          <p className={`font-black ${item.store_on_hand_qty < 0 ? "text-red-700" : "text-slate-800"}`}>{formatQty(item.store_on_hand_qty)} {item.unit}</p>
                        </div>
                        <div className="rounded-md bg-slate-50 px-2 py-2">
                          <p className="text-slate-500">กำลังส่งมา</p>
                          <p className="font-black text-blue-700">{formatQty(item.confirmed_incoming_qty)} {item.unit}</p>
                        </div>
                        <p className="col-span-2 text-slate-500 sm:col-span-4">
                          Forecast {formatQty(item.forecast_qty)} + Safety {formatQty(item.safety_stock_qty)} ({formatQty(item.safety_stock_percent)}%) − คงเหลือ {formatQty(item.store_on_hand_qty)} − ระหว่างทาง {formatQty(item.confirmed_incoming_qty)} · ปัดแพ็ก {formatQty(item.pack_size)}
                        </p>
                      </div>
                    ) : (
                      <p className="mt-1 text-xs text-slate-500">จำนวนแนะนำที่บันทึกไว้ตอนส่งใบสั่ง</p>
                    )}
                  </div>
                  <div className="grid grid-cols-[40px_minmax(96px,128px)_40px_40px] items-center gap-2">
                    <Button variant="outline" size="icon" className="h-10 w-10" disabled={hasSubmittedCentralOrder} onClick={() => updateOrderQty(item.key, -1)}>
                      <Minus className="h-4 w-4" />
                    </Button>
                    <div className="relative">
                      <Input
                        aria-label={`จำนวนสั่ง ${item.name}`}
                        className="h-10 pr-10 text-center text-base font-black text-slate-950"
                        disabled={hasSubmittedCentralOrder}
                        min={0}
                        step="0.01"
                        type="number"
                        value={item.order_qty}
                        onChange={(event) => setOrderQty(item.key, event.target.value)}
                      />
                      <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-xs font-semibold text-slate-500">{item.unit}</span>
                    </div>
                    <Button size="icon" className="h-10 w-10 bg-orange-600 hover:bg-orange-700" disabled={hasSubmittedCentralOrder} onClick={() => updateOrderQty(item.key, 1)}>
                      <Plus className="h-4 w-4" />
                    </Button>
                    <Button variant="outline" size="icon" className="h-10 w-10" disabled={hasSubmittedCentralOrder} onClick={() => resetOrderQty(item.key)}>
                      <RotateCcw className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>
            )) : (
              <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-slate-500">ยังไม่มีรายการสำหรับสั่งสินค้า</div>
            )}
          </div>
          <div className="grid gap-3 border-t border-slate-200 bg-slate-50 p-4 sm:grid-cols-[1fr_auto] sm:items-center">
            <div>
              <p className="font-bold text-slate-950">รวมรายการสั่งสินค้า</p>
              <p className="text-sm text-slate-500">
                {activePurchaseCount} รายการ · รวม {formatQty(totalRequestedQty)} หน่วย · ปรับเอง {changedRequestCount} รายการ
              </p>
            </div>
            <Button
              type="button"
              className="h-11 bg-orange-600 hover:bg-orange-700"
              disabled={(dailySummary?.closure_count ?? 0) === 0 || purchaseItems.length === 0 || isSubmittingOrder || hasSubmittedCentralOrder}
              onClick={() => void handleSubmitCentralOrder()}
            >
              {isSubmittingOrder ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
              {hasSubmittedCentralOrder ? "ส่งแล้ว" : "ส่งใบสั่งรวมวันนี้"}
            </Button>
          </div>
        </section>
      )}
    </div>
  );
}
