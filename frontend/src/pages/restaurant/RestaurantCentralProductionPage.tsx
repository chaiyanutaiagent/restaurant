import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import {
  ArrowLeft,
  Ban,
  CheckCircle2,
  ChefHat,
  ClipboardList,
  CreditCard,
  Factory,
  Loader2,
  PackageCheck,
  Play,
  PlusCircle,
} from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { stockApi } from "@/lib/stockApi";
import { wapApi, type ProductionBatch, type ProductionBatchLine } from "@/lib/wapApi";
import type { StockBalance } from "@/types/stock";

function todayString(): string {
  return new Date().toISOString().slice(0, 10);
}

function firstDayOfMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
}

function formatQty(value: number): string {
  return Number.isInteger(value)
    ? String(value)
    : value.toLocaleString("th-TH", { maximumFractionDigits: 4 });
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  return new Date(value).toLocaleString("th-TH", { dateStyle: "medium", timeStyle: "short" });
}

function orderStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    submitted: "ส่งแล้ว",
    reserved_credit: "กันเครดิตแล้ว",
    approved: "อนุมัติแล้ว",
    packed: "แพ็กแล้ว",
    shipped: "จัดส่งแล้ว",
    received: "รับแล้ว",
    cancelled: "ยกเลิก",
  };
  return labels[status] ?? status;
}

function batchStatusLabel(status: ProductionBatch["status"]): string {
  return {
    draft: "ร่าง",
    planned: "วางแผนแล้ว",
    in_progress: "กำลังผลิต",
    completed: "ผลิตเสร็จ",
    cancelled: "ยกเลิก",
  }[status];
}

function batchStatusClass(status: ProductionBatch["status"]): string {
  if (status === "completed") return "bg-emerald-100 text-emerald-700";
  if (status === "in_progress") return "bg-blue-100 text-blue-700";
  if (status === "cancelled") return "bg-slate-200 text-slate-600";
  return "bg-amber-100 text-amber-700";
}

function apiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail ?? error.response?.data?.error?.message;
    if (typeof detail === "string") return detail;
  }
  return error instanceof Error ? error.message : "กรุณาลองใหม่";
}

export default function RestaurantCentralProductionPage(): JSX.Element {
  const { brandSlug } = useParams<{ brandSlug?: string }>();
  const queryClient = useQueryClient();
  const [dateFrom, setDateFrom] = useState(firstDayOfMonth());
  const [dateTo, setDateTo] = useState(todayString());
  const [statusFilter, setStatusFilter] = useState("");
  const [plannedDate, setPlannedDate] = useState(todayString());
  const [batchNote, setBatchNote] = useState("");
  const [actualQty, setActualQty] = useState<Record<string, string>>({});
  const [receiveProductId, setReceiveProductId] = useState("");
  const [receiveQty, setReceiveQty] = useState("");
  const [receiveCost, setReceiveCost] = useState("");
  const [receiveNote, setReceiveNote] = useState("รับวัตถุดิบเข้าคลัง RAW");
  const centralBase = brandSlug ? `/central/${brandSlug}` : "/restaurant";
  const summaryParams = { date_from: dateFrom, date_to: dateTo, status: statusFilter || undefined };

  const productionQuery = useQuery({
    queryKey: ["restaurant-central-production-summary", brandSlug ?? "legacy", summaryParams],
    queryFn: async () => (await wapApi.centralProductionSummary(brandSlug, summaryParams)).data.data,
  });
  const ingredientsQuery = useQuery({
    queryKey: ["restaurant-central-production-ingredients", brandSlug ?? "legacy", summaryParams],
    queryFn: async () => (await wapApi.centralProductionIngredients(brandSlug, summaryParams)).data.data,
  });
  const ordersQuery = useQuery({
    queryKey: ["restaurant-central-orders", brandSlug ?? "legacy"],
    queryFn: async () => (await wapApi.centralOrders(brandSlug)).data.data,
  });
  const batchQuery = useQuery({
    queryKey: ["restaurant-production-batches", brandSlug ?? "legacy", dateFrom, dateTo],
    queryFn: async () => (
      await wapApi.productionBatches(brandSlug as string, { date_from: dateFrom, date_to: dateTo })
    ).data.data,
    enabled: Boolean(brandSlug),
  });
  const transferConfigQuery = useQuery({
    queryKey: ["restaurant-central-transfer-config", brandSlug ?? "legacy"],
    queryFn: async () => (await wapApi.transferConfig(brandSlug ?? "")).data.data,
    enabled: Boolean(brandSlug),
  });
  const rawLocationId = transferConfigQuery.data?.central_location_id ?? null;
  const readyLocationId = transferConfigQuery.data?.central_ready_location_id ?? null;
  const rawStockQuery = useQuery({
    queryKey: ["restaurant-central-stock", brandSlug ?? "legacy", rawLocationId],
    queryFn: async () => (
      await stockApi.listBalances({ location_id: rawLocationId ?? undefined })
    ).data.data as StockBalance[],
    enabled: Boolean(rawLocationId),
  });

  const activeOrders = (ordersQuery.data ?? []).filter((order) =>
    ["submitted", "reserved_credit", "approved", "packed"].includes(order.status)
    && order.business_date >= dateFrom
    && order.business_date <= dateTo
    && (!statusFilter || order.status === statusFilter)
  );
  const rawStockByProduct = new Map(
    (rawStockQuery.data ?? []).map((balance) => [balance.product_id, balance])
  );
  const ingredientRows = (ingredientsQuery.data ?? []).map((item) => {
    const stock = item.product_id ? rawStockByProduct.get(item.product_id) : undefined;
    const qtyAvailable = Number(stock?.qty_available ?? 0);
    const shortageQty = Math.max(Number(item.required_qty || 0) - qtyAvailable, 0);
    return { ...item, stock, qtyAvailable, shortageQty };
  });
  const shortageCount = ingredientRows.filter((item) => !item.stock || item.shortageQty > 0).length;
  const productionRows = (productionQuery.data ?? []).map((item) => ({
    ...item,
    readyAvailable: Number(item.ready_available ?? 0),
    inProductionQty: Number(item.in_production_qty ?? 0),
    productionRequired: Number(item.production_required ?? item.requested_qty ?? 0),
  }));
  const requiredOutputs = productionRows.filter(
    (item) => item.product_id && item.productionRequired > 0
  );
  const receivableItems = ingredientRows.filter(
    (item): item is typeof item & { product_id: string; stock: StockBalance } =>
      Boolean(item.product_id && item.stock)
  );

  async function refreshProduction(): Promise<void> {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["restaurant-production-batches"] }),
      queryClient.invalidateQueries({ queryKey: ["restaurant-central-production-summary"] }),
      queryClient.invalidateQueries({ queryKey: ["restaurant-central-production-ingredients"] }),
      queryClient.invalidateQueries({ queryKey: ["restaurant-central-stock"] }),
    ]);
  }

  const createBatchMutation = useMutation({
    mutationFn: async () => {
      if (!brandSlug) throw new Error("ไม่พบแบรนด์");
      return wapApi.createProductionBatch(brandSlug, {
        planned_date: plannedDate,
        outputs: requiredOutputs.map((item) => ({
          product_id: item.product_id as string,
          planned_qty: item.productionRequired,
          unit_code: item.unit,
        })),
        note: batchNote.trim() || null,
      });
    },
    onSuccess: async () => {
      setBatchNote("");
      await refreshProduction();
      window.alert("สร้าง Production Batch แล้ว ระบบคำนวณวัตถุดิบจากสูตรให้เรียบร้อย");
    },
    onError: (error) => window.alert(`สร้าง Batch ไม่สำเร็จ: ${apiError(error)}`),
  });
  const startBatchMutation = useMutation({
    mutationFn: async (batchId: string) => {
      if (!brandSlug) throw new Error("ไม่พบแบรนด์");
      return wapApi.startProductionBatch(brandSlug, batchId);
    },
    onSuccess: refreshProduction,
    onError: (error) => window.alert(`เริ่มผลิตไม่สำเร็จ: ${apiError(error)}`),
  });
  const completeBatchMutation = useMutation({
    mutationFn: async (batch: ProductionBatch) => {
      if (!brandSlug) throw new Error("ไม่พบแบรนด์");
      return wapApi.completeProductionBatch(brandSlug, batch.id, {
        lines: batch.lines.map((line) => ({
          line_id: line.id,
          actual_qty: Number(actualQty[line.id] ?? line.planned_qty),
        })),
        note: batch.note,
      });
    },
    onSuccess: async () => {
      setActualQty({});
      await refreshProduction();
      window.alert("ผลิตเสร็จแล้ว: RAW ถูกตัดและผลผลิตถูกเพิ่มเข้า READY ในรายการเดียวกัน");
    },
    onError: (error) => window.alert(`ยืนยันผลิตเสร็จไม่สำเร็จ: ${apiError(error)}`),
  });
  const cancelBatchMutation = useMutation({
    mutationFn: async ({ batchId, reason }: { batchId: string; reason: string }) => {
      if (!brandSlug) throw new Error("ไม่พบแบรนด์");
      return wapApi.cancelProductionBatch(brandSlug, batchId, reason);
    },
    onSuccess: refreshProduction,
    onError: (error) => window.alert(`ยกเลิก Batch ไม่สำเร็จ: ${apiError(error)}`),
  });
  const receiveMutation = useMutation({
    mutationFn: async () => {
      if (!rawLocationId || !receiveProductId) return;
      await stockApi.receive({
        location_id: rawLocationId,
        items: [{
          product_id: receiveProductId,
          qty: Number(receiveQty || 0),
          cost_per_unit: receiveCost ? Number(receiveCost) : undefined,
        }],
        note: receiveNote || "รับวัตถุดิบเข้าคลัง RAW",
        reference_type: "central_raw_material_receive",
      });
    },
    onSuccess: async () => {
      setReceiveProductId("");
      setReceiveQty("");
      setReceiveCost("");
      await refreshProduction();
      window.alert("รับวัตถุดิบเข้าคลัง RAW แล้ว");
    },
    onError: (error) => window.alert(`รับวัตถุดิบไม่สำเร็จ: ${apiError(error)}`),
  });

  function setLineActual(line: ProductionBatchLine, value: string): void {
    setActualQty((current) => ({ ...current, [line.id]: value }));
  }

  function fillReceiveForm(productId: string | null, qty: number, note: string): void {
    if (!productId) return;
    setReceiveProductId(productId);
    setReceiveQty(qty > 0 ? String(qty) : "1");
    setReceiveNote(note);
  }

  const isLoading = productionQuery.isLoading
    || ingredientsQuery.isLoading
    || ordersQuery.isLoading
    || batchQuery.isLoading
    || transferConfigQuery.isLoading
    || rawStockQuery.isLoading;
  const isError = productionQuery.isError
    || ingredientsQuery.isError
    || ordersQuery.isError
    || batchQuery.isError
    || transferConfigQuery.isError
    || rawStockQuery.isError;

  return (
    <div className="mx-auto flex min-h-full max-w-6xl flex-col gap-4">
      <header className="rounded-lg border border-slate-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 p-4">
          <div className="flex min-w-0 items-center gap-3">
            <Button asChild variant="outline" size="icon" className="h-10 w-10 shrink-0">
              <Link to={`${centralBase}/orders`} aria-label="กลับหน้าใบสั่ง">
                <ArrowLeft className="h-5 w-5" />
              </Link>
            </Button>
            <div className="min-w-0">
              <h1 className="truncate text-xl font-black text-slate-950">Production Batch</h1>
              <p className="truncate text-sm text-slate-500">วางแผน ตัด RAW และรับผลผลิตเข้า READY</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to={`${centralBase}/credits`}><CreditCard className="mr-2 h-4 w-4" />เครดิต</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to={`${centralBase}/recipes`}><ChefHat className="mr-2 h-4 w-4" />สูตร</Link>
            </Button>
          </div>
        </div>
      </header>

      {isLoading ? (
        <div className="flex h-72 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />โหลดแผนผลิต
        </div>
      ) : isError ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-6 text-center font-semibold text-rose-700">
          โหลดข้อมูล Production ไม่สำเร็จ
        </div>
      ) : (
        <>
          <section className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="grid gap-3 md:grid-cols-[1fr_1fr_180px]">
              <Input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
              <Input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
              <select
                className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
              >
                <option value="">ใบสั่ง Active ทั้งหมด</option>
                <option value="submitted">ส่งแล้ว</option>
                <option value="reserved_credit">กันเครดิตแล้ว</option>
                <option value="approved">อนุมัติแล้ว</option>
                <option value="packed">แพ็กแล้ว</option>
              </select>
            </div>
          </section>

          {(!rawLocationId || !readyLocationId) ? (
            <section className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-800">
              กรุณาตั้งคลัง RAW และ READY ให้ครบและเป็นคนละคลังก่อนสร้าง Production Batch
            </section>
          ) : null}

          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-500">ใบสั่ง Active</p>
              <p className="mt-2 text-3xl font-black text-slate-950">{activeOrders.length}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-500">ต้องผลิตเพิ่ม</p>
              <p className="mt-2 text-3xl font-black text-orange-700">{requiredOutputs.length}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-500">Batch กำลังทำ</p>
              <p className="mt-2 text-3xl font-black text-blue-700">
                {(batchQuery.data ?? []).filter((batch) => ["draft", "planned", "in_progress"].includes(batch.status)).length}
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-500">วัตถุดิบขาด/ไม่พบ RAW</p>
              <p className={`mt-2 text-3xl font-black ${shortageCount > 0 ? "text-rose-700" : "text-emerald-700"}`}>{shortageCount}</p>
            </div>
          </section>

          <section className="rounded-lg border border-orange-200 bg-orange-50/40 p-4">
            <div className="mb-3 flex items-center gap-2">
              <Factory className="h-5 w-5 text-orange-700" />
              <h2 className="font-bold text-slate-950">สร้างแผนผลิตจากยอดที่ยังขาด</h2>
            </div>
            <div className="grid gap-3 lg:grid-cols-[160px_1fr_auto] lg:items-end">
              <div>
                <p className="mb-1 text-xs font-semibold text-slate-600">วันที่วางแผนผลิต</p>
                <Input type="date" value={plannedDate} onChange={(event) => setPlannedDate(event.target.value)} />
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold text-slate-600">หมายเหตุ</p>
                <Input value={batchNote} onChange={(event) => setBatchNote(event.target.value)} placeholder="เช่น รอบเช้า" />
              </div>
              <Button
                className="bg-orange-600 hover:bg-orange-700"
                disabled={!brandSlug || !rawLocationId || !readyLocationId || requiredOutputs.length === 0 || createBatchMutation.isPending}
                onClick={() => createBatchMutation.mutate()}
              >
                <PlusCircle className="mr-2 h-4 w-4" />
                {createBatchMutation.isPending ? "กำลังสร้าง..." : "สร้าง Batch"}
              </Button>
            </div>
            <p className="mt-2 text-xs text-slate-600">ระบบหัก READY และจำนวนใน Batch ที่กำลังทำแล้ว จากนั้นคำนวณวัตถุดิบตามสูตรให้อัตโนมัติ</p>
          </section>

          <section className="rounded-lg border border-slate-200 bg-white">
            <div className="flex items-center gap-2 border-b border-slate-200 p-4">
              <Factory className="h-5 w-5 text-blue-700" />
              <h2 className="font-bold text-slate-950">Production Batches</h2>
            </div>
            <div className="divide-y divide-slate-100">
              {(batchQuery.data ?? []).length > 0 ? (batchQuery.data ?? []).map((batch) => {
                const inputs = batch.lines.filter((line) => line.line_type === "input");
                const outputs = batch.lines.filter((line) => line.line_type === "output");
                return (
                  <article key={batch.id} className="p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="font-black text-slate-950">{batch.batch_number}</p>
                          <span className={`rounded-full px-2 py-1 text-xs font-bold ${batchStatusClass(batch.status)}`}>
                            {batchStatusLabel(batch.status)}
                          </span>
                        </div>
                        <p className="mt-1 text-sm text-slate-500">แผน {batch.planned_date} · {batch.raw_location_name} → {batch.ready_location_name}</p>
                        {batch.note ? <p className="mt-1 text-sm text-slate-600">{batch.note}</p> : null}
                      </div>
                      <div className="flex gap-2">
                        {batch.status === "planned" || batch.status === "draft" ? (
                          <Button size="sm" onClick={() => startBatchMutation.mutate(batch.id)} disabled={startBatchMutation.isPending}>
                            <Play className="mr-2 h-4 w-4" />เริ่มผลิต
                          </Button>
                        ) : null}
                        {batch.status === "in_progress" ? (
                          <Button
                            size="sm"
                            className="bg-emerald-600 hover:bg-emerald-700"
                            disabled={completeBatchMutation.isPending}
                            onClick={() => {
                              if (window.confirm(`ยืนยันผลิตเสร็จ ${batch.batch_number}? ระบบจะตัด RAW และรับ READY พร้อมกัน`)) {
                                completeBatchMutation.mutate(batch);
                              }
                            }}
                          >
                            <CheckCircle2 className="mr-2 h-4 w-4" />ผลิตเสร็จ
                          </Button>
                        ) : null}
                        {["draft", "planned", "in_progress"].includes(batch.status) ? (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={cancelBatchMutation.isPending}
                            onClick={() => {
                              const reason = window.prompt("เหตุผลที่ยกเลิก Batch")?.trim();
                              if (reason) cancelBatchMutation.mutate({ batchId: batch.id, reason });
                            }}
                          >
                            <Ban className="mr-2 h-4 w-4" />ยกเลิก
                          </Button>
                        ) : null}
                      </div>
                    </div>
                    <div className="mt-4 grid gap-4 lg:grid-cols-2">
                      <BatchLines
                        title="วัตถุดิบที่ตัด"
                        lines={inputs}
                        editable={batch.status === "in_progress"}
                        actualQty={actualQty}
                        onActualChange={setLineActual}
                      />
                      <BatchLines
                        title="ผลผลิตเข้า READY"
                        lines={outputs}
                        editable={batch.status === "in_progress"}
                        actualQty={actualQty}
                        onActualChange={setLineActual}
                      />
                    </div>
                    {batch.completed_at ? <p className="mt-3 text-xs text-slate-500">เสร็จเมื่อ {formatDateTime(batch.completed_at)}</p> : null}
                  </article>
                );
              }) : <div className="p-8 text-center text-slate-500">ยังไม่มี Production Batch ในช่วงวันที่เลือก</div>}
            </div>
          </section>

          <section className="rounded-lg border border-slate-200 bg-white">
            <div className="flex items-center gap-2 border-b border-slate-200 p-4">
              <PackageCheck className="h-5 w-5 text-orange-600" />
              <h2 className="font-bold text-slate-950">ยอดต้องผลิต</h2>
            </div>
            <div className="divide-y divide-slate-100">
              {productionRows.length > 0 ? productionRows.map((item) => (
                <div key={`${item.product_id ?? item.sku}:${item.unit}`} className="grid gap-3 px-4 py-3 lg:grid-cols-[1fr_repeat(4,110px)] lg:items-center">
                  <div>
                    <p className="font-bold text-slate-950">{item.product_name}</p>
                    <p className="text-sm text-slate-500">{item.sku || "-"} · {item.order_count} ใบสั่ง</p>
                  </div>
                  <QtyStat label="ยอดสั่ง" value={Number(item.requested_qty)} unit={item.unit} />
                  <QtyStat label="READY" value={item.readyAvailable} unit={item.unit} />
                  <QtyStat label="ใน Batch" value={item.inProductionQty} unit={item.unit} />
                  <QtyStat label="ต้องผลิต" value={item.productionRequired} unit={item.unit} accent />
                </div>
              )) : <div className="p-8 text-center text-slate-500">ยังไม่มีรายการผลิต</div>}
            </div>
          </section>

          <section className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="mb-3 flex items-center gap-2">
              <PlusCircle className="h-5 w-5 text-blue-700" />
              <h2 className="font-bold text-slate-950">รับวัตถุดิบเข้า RAW</h2>
            </div>
            <div className="grid gap-3 lg:grid-cols-[1fr_120px_120px_1fr_auto]">
              <select className="h-10 rounded-md border border-gray-300 px-3 text-sm" value={receiveProductId} disabled={!rawLocationId} onChange={(event) => setReceiveProductId(event.target.value)}>
                <option value="">เลือกวัตถุดิบ RAW</option>
                {receivableItems.map((item) => <option key={item.product_id} value={item.product_id}>{item.product_name} ({item.sku || "-"})</option>)}
              </select>
              <Input type="number" min="0.0001" step="0.0001" value={receiveQty} disabled={!rawLocationId} onChange={(event) => setReceiveQty(event.target.value)} placeholder="จำนวน" />
              <Input type="number" min="0" step="0.0001" value={receiveCost} disabled={!rawLocationId} onChange={(event) => setReceiveCost(event.target.value)} placeholder="ทุน/หน่วย" />
              <Input value={receiveNote} disabled={!rawLocationId} onChange={(event) => setReceiveNote(event.target.value)} placeholder="หมายเหตุ" />
              <Button className="bg-blue-600 hover:bg-blue-700" disabled={!rawLocationId || !receiveProductId || Number(receiveQty || 0) <= 0 || receiveMutation.isPending} onClick={() => receiveMutation.mutate()}>
                {receiveMutation.isPending ? "กำลังรับ..." : "รับเข้า RAW"}
              </Button>
            </div>
          </section>

          <section className="rounded-lg border border-slate-200 bg-white">
            <div className="flex items-center gap-2 border-b border-slate-200 p-4">
              <PackageCheck className="h-5 w-5 text-emerald-700" />
              <h2 className="font-bold text-slate-950">วัตถุดิบประมาณการจากยอดสั่ง</h2>
            </div>
            <div className="divide-y divide-slate-100">
              {ingredientRows.length > 0 ? ingredientRows.map((item) => (
                <div key={`${item.product_id ?? item.sku}:${item.unit}`} className="grid gap-3 px-4 py-3 lg:grid-cols-[1fr_auto_auto_auto] lg:items-center">
                  <div><p className="font-bold text-slate-950">{item.product_name}</p><p className="text-sm text-slate-500">{item.sku || "-"}</p></div>
                  <QtyStat label="ต้องใช้" value={Number(item.required_qty)} unit={item.unit} />
                  <QtyStat label="RAW ใช้ได้" value={item.qtyAvailable} unit={item.stock?.unit_code ?? item.unit} />
                  <div className="text-right">
                    <QtyStat label="ต้องรับเพิ่ม" value={item.shortageQty} unit={item.unit} accent={item.shortageQty > 0} />
                    {item.stock && item.product_id ? (
                      <Button type="button" variant="outline" size="sm" className="mt-2" onClick={() => fillReceiveForm(item.product_id, item.shortageQty > 0 ? item.shortageQty : Number(item.required_qty), `รับวัตถุดิบ ${item.product_name}`)}>กรอกยอดรับ</Button>
                    ) : <span className="mt-2 inline-flex rounded-full bg-amber-100 px-2 py-1 text-xs font-bold text-amber-700">ไม่ใช่ RAW หรือไม่พบ balance</span>}
                  </div>
                </div>
              )) : <div className="p-8 text-center text-slate-500">ยังไม่มีวัตถุดิบที่ต้องเตรียม</div>}
            </div>
          </section>

          <section className="rounded-lg border border-slate-200 bg-white">
            <div className="flex items-center gap-2 border-b border-slate-200 p-4"><ClipboardList className="h-5 w-5 text-slate-700" /><h2 className="font-bold text-slate-950">ใบสั่งที่รวมในแผน</h2></div>
            <div className="divide-y divide-slate-100">
              {activeOrders.length > 0 ? activeOrders.map((order) => (
                <Link key={order.id} to={`${centralBase}/orders`} className="grid gap-2 px-4 py-3 transition hover:bg-slate-50 sm:grid-cols-[1fr_auto] sm:items-center">
                  <div><p className="font-bold text-slate-950">{order.order_number}</p><p className="text-sm text-slate-500">{order.branch_name ?? "ไม่ระบุสาขา"} · {formatDateTime(order.submitted_at)}</p></div>
                  <span className="rounded-full bg-orange-100 px-3 py-1 text-sm font-bold text-orange-700">{orderStatusLabel(order.status)}</span>
                </Link>
              )) : <div className="p-8 text-center text-slate-500">ยังไม่มีใบสั่ง Active</div>}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function BatchLines({
  title,
  lines,
  editable,
  actualQty,
  onActualChange,
}: {
  title: string;
  lines: ProductionBatchLine[];
  editable: boolean;
  actualQty: Record<string, string>;
  onActualChange: (line: ProductionBatchLine, value: string) => void;
}): JSX.Element {
  return (
    <div className="rounded-lg border border-slate-200">
      <p className="border-b border-slate-200 px-3 py-2 text-sm font-bold text-slate-700">{title}</p>
      <div className="divide-y divide-slate-100">
        {lines.map((line) => (
          <div key={line.id} className="grid grid-cols-[1fr_120px] items-center gap-3 px-3 py-2">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-slate-950">{line.product_name}</p>
              <p className="truncate text-xs text-slate-500">{line.product_sku || "-"} · {line.source_location_name ?? line.destination_location_name}</p>
            </div>
            {editable ? (
              <Input
                type="number"
                min="0"
                step="0.0001"
                value={actualQty[line.id] ?? String(line.planned_qty)}
                onChange={(event) => onActualChange(line, event.target.value)}
                aria-label={`จำนวนจริง ${line.product_name}`}
              />
            ) : (
              <div className="text-right">
                <p className="font-black text-slate-900">{formatQty(Number(line.actual_qty ?? line.planned_qty))}</p>
                <p className="text-xs text-slate-500">{line.unit_code}</p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function QtyStat({ label, value, unit, accent = false }: { label: string; value: number; unit: string; accent?: boolean }): JSX.Element {
  return (
    <div className="text-right">
      <p className="text-xs font-semibold uppercase text-slate-500">{label}</p>
      <p className={`text-xl font-black ${accent ? "text-orange-700" : "text-slate-900"}`}>{formatQty(value)}</p>
      <p className="text-xs text-slate-500">{unit}</p>
    </div>
  );
}
