import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ClipboardCheck, History, Loader2, MinusCircle, PackageCheck, Scale, Warehouse } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/ui/use-toast";
import { stockApi } from "@/lib/stockApi";
import { stockCountApi } from "@/lib/stockCountApi";
import {
  wapApi,
  type StoreStockAdjustmentPayload,
  type StoreStockDailySummary,
} from "@/lib/wapApi";
import { useAuthStore } from "@/stores/auth.store";
import type { StockBalance, StockLocation, StockMovement } from "@/types/stock";
import type { CountSession, CountSessionListItem } from "@/types/stockCount";

type AdjustmentDraft = {
  product_id: string;
  kind: "waste" | "adjustment";
  reason: StoreStockAdjustmentPayload["reason"];
  qty: string;
  note: string;
};

const REASONS: Array<{ value: StoreStockAdjustmentPayload["reason"]; label: string; kinds: Array<AdjustmentDraft["kind"]> }> = [
  { value: "prep_waste", label: "เสียระหว่างเตรียม", kinds: ["waste"] },
  { value: "expired", label: "หมดอายุ", kinds: ["waste"] },
  { value: "staff_sample", label: "พนักงาน / ตัวอย่าง", kinds: ["waste"] },
  { value: "return_central", label: "คืนส่วนกลาง", kinds: ["waste"] },
  { value: "count_higher", label: "ตรวจนับเกิน (เพิ่ม)", kinds: ["adjustment"] },
  { value: "count_lower", label: "ตรวจนับขาด (ลด)", kinds: ["adjustment"] },
  { value: "other", label: "อื่น ๆ", kinds: ["waste", "adjustment"] },
];

const MOVEMENT_LABELS: Record<string, string> = {
  transfer_in: "รับจากส่วนกลาง",
  receive: "รับเข้า",
  sale: "ขายตามสูตร",
  sale_return: "คืนจากขาย",
  waste: "ของเสีย",
  adjust: "ปรับยอด",
  opening: "ยอดตั้งต้น",
};

function todayLocal(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function qty(value: number | string | null | undefined): string {
  return Number(value ?? 0).toLocaleString("th-TH", { maximumFractionDigits: 4 });
}

function errorMessage(error: unknown): string {
  if (error && typeof error === "object" && "response" in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response;
    if (response?.data?.detail) return response.data.detail;
  }
  return error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง";
}

export default function RestaurantStoreStockPage(): JSX.Element {
  const { brandSlug = "" } = useParams<{ brandSlug: string }>();
  const branchId = useAuthStore((state) => state.branchId);
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const canAdjust = hasPermission("brand.store.stock.adjust");
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [businessDate, setBusinessDate] = useState(todayLocal());
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [adjustDraft, setAdjustDraft] = useState<AdjustmentDraft>({
    product_id: "",
    kind: "waste",
    reason: "prep_waste",
    qty: "",
    note: "",
  });
  const [countOpen, setCountOpen] = useState(false);
  const [countSessionId, setCountSessionId] = useState<string | null>(null);
  const [countDrafts, setCountDrafts] = useState<Record<string, string>>({});
  const [countBusy, setCountBusy] = useState(false);

  const locationsQuery = useQuery({
    queryKey: ["restaurant-store-stock-locations", branchId],
    queryFn: async () => (await stockApi.listLocations(branchId ?? undefined)).data.data as StockLocation[],
    enabled: Boolean(branchId),
  });

  const dailyQuery = useQuery({
    queryKey: ["restaurant-store-stock-daily", brandSlug, businessDate],
    queryFn: async () => (await wapApi.storeStockDaily(brandSlug, businessDate)).data.data as StoreStockDailySummary,
    enabled: Boolean(branchId),
  });
  const storeLocationId = dailyQuery.data?.location_id ?? null;
  const storeLocation = locationsQuery.data?.find((item) => item.id === storeLocationId) ?? null;

  const balancesQuery = useQuery({
    queryKey: ["restaurant-store-stock-balances", brandSlug, storeLocationId],
    queryFn: async () => (
      await stockApi.listBalances({ location_id: storeLocationId ?? undefined })
    ).data.data as StockBalance[],
    enabled: Boolean(storeLocationId),
  });

  const movementsQuery = useQuery({
    queryKey: ["restaurant-store-stock-movements", storeLocationId, businessDate],
    queryFn: async () => (
      await stockApi.listMovements({
        location_id: storeLocationId ?? undefined,
        date_from: businessDate,
        date_to: businessDate,
        page: 1,
        limit: 100,
      })
    ).data.data as StockMovement[],
    enabled: Boolean(storeLocationId),
  });

  const sessionsQuery = useQuery({
    queryKey: ["restaurant-store-stock-count-sessions", storeLocationId],
    queryFn: async () => (
      await stockCountApi.listSessions({ location_id: storeLocationId ?? undefined, page: 1, limit: 50 })
    ).data.data as CountSessionListItem[],
    enabled: Boolean(storeLocationId) && canAdjust,
  });

  const countSessionQuery = useQuery({
    queryKey: ["restaurant-store-stock-count-session", countSessionId],
    queryFn: async () => (await stockCountApi.getSession(countSessionId ?? "")).data.data as CountSession,
    enabled: Boolean(countSessionId),
  });

  useEffect(() => {
    const session = countSessionQuery.data;
    if (!session) return;
    setCountDrafts(Object.fromEntries(session.items.map((item) => [
      item.id,
      item.actual_qty === null ? "" : String(item.actual_qty),
    ])));
  }, [countSessionQuery.data]);

  const balances = balancesQuery.data ?? [];
  const dailyItems = dailyQuery.data?.items ?? [];
  const movements = movementsQuery.data ?? [];
  const activeCountSession = useMemo(
    () => (sessionsQuery.data ?? []).find((item) => item.status === "draft" || item.status === "in_progress") ?? null,
    [sessionsQuery.data],
  );
  const latestCompletedCount = useMemo(
    () => (sessionsQuery.data ?? []).find((item) => item.status === "completed" && item.count_date === businessDate) ?? null,
    [businessDate, sessionsQuery.data],
  );
  const negativeCount = dailyQuery.data?.negative_count ?? balances.filter((item) => Number(item.qty_on_hand) < 0).length;
  const receivedTotal = dailyItems.reduce((sum, item) => sum + item.received_qty, 0);
  const usedTotal = dailyItems.reduce((sum, item) => sum + item.used_sales_qty, 0);
  const wasteTotal = dailyItems.reduce((sum, item) => sum + item.waste_qty, 0);

  async function refreshAll(): Promise<void> {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["restaurant-store-stock-balances"] }),
      queryClient.invalidateQueries({ queryKey: ["restaurant-store-stock-daily"] }),
      queryClient.invalidateQueries({ queryKey: ["restaurant-store-stock-movements"] }),
      queryClient.invalidateQueries({ queryKey: ["restaurant-store-stock-count-sessions"] }),
    ]);
  }

  const adjustmentMutation = useMutation({
    mutationFn: async () => {
      const enteredQty = Number(adjustDraft.qty);
      let signedQty = enteredQty;
      if (adjustDraft.kind === "adjustment" && adjustDraft.reason === "count_lower") {
        signedQty = -Math.abs(enteredQty);
      }
      if (adjustDraft.kind === "adjustment" && adjustDraft.reason === "count_higher") {
        signedQty = Math.abs(enteredQty);
      }
      return wapApi.adjustStoreStock(brandSlug, {
        product_id: adjustDraft.product_id,
        qty: signedQty,
        kind: adjustDraft.kind,
        reason: adjustDraft.reason,
        note: adjustDraft.note.trim() || null,
      });
    },
    onSuccess: async () => {
      toast({ title: adjustDraft.kind === "waste" ? "บันทึกของเสียแล้ว" : "ปรับยอด stock แล้ว" });
      setAdjustOpen(false);
      setAdjustDraft((current) => ({ ...current, qty: "", note: "" }));
      await refreshAll();
    },
    onError: (error) => toast({ title: "บันทึกไม่สำเร็จ", description: errorMessage(error), variant: "destructive" }),
  });

  function openAdjustment(productId: string, kind: AdjustmentDraft["kind"]): void {
    setAdjustDraft({
      product_id: productId,
      kind,
      reason: kind === "waste" ? "prep_waste" : "count_higher",
      qty: "",
      note: "",
    });
    setAdjustOpen(true);
  }

  async function openDailyCount(): Promise<void> {
    if (!branchId || !storeLocationId || balances.length === 0) return;
    setCountBusy(true);
    try {
      let sessionId = activeCountSession?.id ?? null;
      let status = activeCountSession?.status ?? null;
      if (!sessionId) {
        const created = (await stockCountApi.createSession({
          branch_id: branchId,
          location_id: storeLocationId,
          count_date: businessDate,
          product_ids: balances.map((item) => item.product_id),
          note: `ตรวจนับ STORE-STOCK ${brandSlug}`,
        })).data.data as CountSession;
        sessionId = created.id;
        status = created.status;
      }
      if (status === "draft") {
        await stockCountApi.startSession(sessionId);
      }
      setCountSessionId(sessionId);
      setCountOpen(true);
      await queryClient.invalidateQueries({ queryKey: ["restaurant-store-stock-count-session", sessionId] });
      await queryClient.invalidateQueries({ queryKey: ["restaurant-store-stock-count-sessions"] });
    } catch (error) {
      toast({ title: "เริ่มตรวจนับไม่สำเร็จ", description: errorMessage(error), variant: "destructive" });
    } finally {
      setCountBusy(false);
    }
  }

  async function completeDailyCount(): Promise<void> {
    const session = countSessionQuery.data;
    if (!session) return;
    const missing = session.items.filter((item) => countDrafts[item.id] === "");
    if (missing.length > 0) {
      toast({ title: `ยังไม่ได้นับ ${missing.length} รายการ`, variant: "destructive" });
      return;
    }
    setCountBusy(true);
    try {
      await stockCountApi.batchUpdateItems(session.id, session.items.map((item) => ({
        item_id: item.id,
        actual_qty: Number(countDrafts[item.id]),
      })));
      await stockCountApi.completeSession(session.id, {
        apply_adjustments: true,
        note: `ปิดยอด STORE-STOCK ${businessDate}`,
      });
      toast({ title: "ตรวจนับและปรับยอดจริงเรียบร้อย" });
      setCountOpen(false);
      setCountSessionId(null);
      await refreshAll();
    } catch (error) {
      toast({ title: "ปิดการตรวจนับไม่สำเร็จ", description: errorMessage(error), variant: "destructive" });
    } finally {
      setCountBusy(false);
    }
  }

  const loading = locationsQuery.isLoading || balancesQuery.isLoading || dailyQuery.isLoading;

  return (
    <div className="mx-auto max-w-6xl space-y-4 pb-10">
      <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-slate-500"><Warehouse className="h-4 w-4" /><span className="text-xs font-black uppercase tracking-wider">STORE-STOCK</span></div>
          <h1 className="mt-1 text-2xl font-black text-slate-950">Stock หน้าร้าน</h1>
          <p className="mt-1 text-sm text-slate-500">{storeLocation?.name ?? (storeLocationId ? "STORE-STOCK ของสาขา" : "กำลังตรวจสอบคลังสาขา")} · ไม่แสดง RAW/READY ของส่วนกลาง</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Input className="w-40" type="date" value={businessDate} onChange={(event) => setBusinessDate(event.target.value)} />
          {canAdjust ? (
            <Button onClick={() => void openDailyCount()} disabled={countBusy || balances.length === 0}>
              {countBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ClipboardCheck className="h-4 w-4" />}
              {activeCountSession ? "นับต่อ" : "ตรวจนับประจำวัน"}
            </Button>
          ) : null}
        </div>
      </div>

      {negativeCount > 0 ? (
        <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-red-800">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <div><p className="font-bold">มี stock ติดลบ {negativeCount} รายการ</p><p className="text-sm">ระบบยังขายต่อได้ แต่ผู้จัดการควรตรวจยอดรับสินค้า สูตร และยอดนับจริง</p></div>
        </div>
      ) : null}

      {dailyQuery.isError ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-800">
          โหลด STORE-STOCK ไม่สำเร็จ: {errorMessage(dailyQuery.error)}
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-4">
        <SummaryCard icon={<PackageCheck className="h-5 w-5" />} label="รายการในร้าน" value={`${balances.length}`} />
        <SummaryCard icon={<Warehouse className="h-5 w-5" />} label="รับเข้าวันนี้" value={qty(receivedTotal)} />
        <SummaryCard icon={<Scale className="h-5 w-5" />} label="ใช้จากการขาย" value={qty(usedTotal)} />
        <SummaryCard icon={<MinusCircle className="h-5 w-5" />} label="ของเสีย" value={qty(wasteTotal)} />
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div><CardTitle>ยอดคงเหลือและสรุปรายวัน</CardTitle><p className="mt-1 text-sm text-slate-500">ยอดขายถูกตัดจากวัตถุดิบตามสูตรของเมนู</p></div>
          {latestCompletedCount ? <Badge variant="success">นับแล้ว {latestCompletedCount.session_number}</Badge> : <Badge variant="secondary">ยังไม่นับวันนี้</Badge>}
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex h-48 items-center justify-center text-slate-500"><Loader2 className="mr-2 h-5 w-5 animate-spin" />โหลด stock</div>
          ) : dailyItems.length === 0 ? (
            <div className="p-10 text-center text-slate-500">ยังไม่มีสินค้าใน STORE-STOCK กรุณารับสินค้าจากส่วนกลางก่อน</div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>สินค้า</TableHead><TableHead className="text-right">ยกมา</TableHead><TableHead className="text-right">รับเข้า</TableHead><TableHead className="text-right">ขาย</TableHead><TableHead className="text-right">เสีย</TableHead><TableHead className="text-right">ควรเหลือ</TableHead><TableHead className="text-right">นับจริง</TableHead><TableHead className="text-right">คงเหลือปัจจุบัน</TableHead>{canAdjust ? <TableHead>จัดการ</TableHead> : null}
                </TableRow></TableHeader>
                <TableBody>
                  {dailyItems.map((item) => (
                    <TableRow key={item.product_id} className={item.is_negative ? "bg-red-50" : undefined}>
                      <TableCell><p className="font-semibold text-slate-950">{item.product_name}</p><p className="text-xs text-slate-500">{item.sku} · {item.unit_code ?? "หน่วย"}</p></TableCell>
                      <TableCell className="text-right">{qty(item.opening_qty)}</TableCell>
                      <TableCell className="text-right text-emerald-700">{qty(item.received_qty)}</TableCell>
                      <TableCell className="text-right text-blue-700">{qty(item.used_sales_qty)}</TableCell>
                      <TableCell className="text-right text-amber-700">{qty(item.waste_qty)}</TableCell>
                      <TableCell className="text-right">{qty(item.expected_closing_qty)}</TableCell>
                      <TableCell className="text-right">{item.physical_qty === null ? "—" : qty(item.physical_qty)}</TableCell>
                      <TableCell className={`text-right font-black ${item.is_negative ? "text-red-700" : "text-slate-950"}`}>{qty(item.current_qty)}</TableCell>
                      {canAdjust ? <TableCell><div className="flex gap-1"><Button size="sm" variant="outline" onClick={() => openAdjustment(item.product_id, "waste")}>ของเสีย</Button><Button size="sm" variant="ghost" onClick={() => openAdjustment(item.product_id, "adjustment")}>ปรับยอด</Button></div></TableCell> : null}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><History className="h-5 w-5" />รายการเคลื่อนไหววันที่เลือก</CardTitle></CardHeader>
        <CardContent className="p-0">
          {movements.length === 0 ? <div className="p-8 text-center text-slate-500">ยังไม่มีรายการเคลื่อนไหว</div> : (
            <div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead>เวลา</TableHead><TableHead>สินค้า</TableHead><TableHead>ประเภท</TableHead><TableHead className="text-right">เปลี่ยนแปลง</TableHead><TableHead className="text-right">คงเหลือ</TableHead><TableHead>ผู้ทำ / หมายเหตุ</TableHead></TableRow></TableHeader><TableBody>
              {movements.map((item) => <TableRow key={item.id}><TableCell>{new Date(item.created_at).toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" })}</TableCell><TableCell><p className="font-medium">{item.product_name}</p><p className="text-xs text-slate-500">{item.product_sku}</p></TableCell><TableCell><Badge variant={item.movement_type === "waste" ? "destructive" : item.qty > 0 ? "success" : "secondary"}>{MOVEMENT_LABELS[item.movement_type] ?? item.movement_type}</Badge></TableCell><TableCell className={`text-right font-semibold ${Number(item.qty) > 0 ? "text-emerald-700" : "text-red-700"}`}>{Number(item.qty) > 0 ? "+" : ""}{qty(item.qty)}</TableCell><TableCell className="text-right">{qty(item.qty_after)}</TableCell><TableCell><p>{item.user_name ?? "—"}</p><p className="max-w-xs truncate text-xs text-slate-500">{item.note ?? "—"}</p></TableCell></TableRow>)}
            </TableBody></Table></div>
          )}
        </CardContent>
      </Card>

      <Dialog open={adjustOpen} onOpenChange={setAdjustOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>{adjustDraft.kind === "waste" ? "บันทึกของเสีย" : "ปรับยอด STORE-STOCK"}</DialogTitle><DialogDescription>ทุกรายการเก็บผู้ทำ สาขา เวลา เหตุผล และยอดก่อน–หลัง</DialogDescription></DialogHeader>
          <div className="space-y-4">
            <div><Label>สินค้า</Label><select className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 text-sm" value={adjustDraft.product_id} onChange={(event) => setAdjustDraft((current) => ({ ...current, product_id: event.target.value }))}>{balances.map((item) => <option key={item.product_id} value={item.product_id}>{item.product_name} ({qty(item.qty_on_hand)})</option>)}</select></div>
            <div className="grid grid-cols-2 gap-2"><Button type="button" variant={adjustDraft.kind === "waste" ? "default" : "outline"} onClick={() => setAdjustDraft((current) => ({ ...current, kind: "waste", reason: "prep_waste" }))}>ของเสีย</Button><Button type="button" variant={adjustDraft.kind === "adjustment" ? "default" : "outline"} onClick={() => setAdjustDraft((current) => ({ ...current, kind: "adjustment", reason: "count_higher" }))}>ปรับยอด</Button></div>
            <div><Label>เหตุผล</Label><select className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 text-sm" value={adjustDraft.reason} onChange={(event) => setAdjustDraft((current) => ({ ...current, reason: event.target.value as StoreStockAdjustmentPayload["reason"] }))}>{REASONS.filter((item) => item.kinds.includes(adjustDraft.kind)).map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></div>
            <div><Label>{adjustDraft.kind === "waste" ? "จำนวนเสีย" : "จำนวนที่ปรับ"}</Label><Input className="mt-1" type="number" min="0" step="0.0001" value={adjustDraft.qty} onChange={(event) => setAdjustDraft((current) => ({ ...current, qty: event.target.value }))} /><p className="mt-1 text-xs text-slate-500">เลือก “ตรวจนับขาด” ระบบจะปรับลดให้อัตโนมัติ</p></div>
            <div><Label>หมายเหตุ</Label><Input className="mt-1" value={adjustDraft.note} onChange={(event) => setAdjustDraft((current) => ({ ...current, note: event.target.value }))} placeholder="รายละเอียดเพิ่มเติม" /></div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setAdjustOpen(false)}>ยกเลิก</Button><Button disabled={!adjustDraft.product_id || Number(adjustDraft.qty) <= 0 || adjustmentMutation.isPending} onClick={() => adjustmentMutation.mutate()}>{adjustmentMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}บันทึก</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={countOpen} onOpenChange={setCountOpen}>
        <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
          <DialogHeader><DialogTitle>ตรวจนับ STORE-STOCK</DialogTitle><DialogDescription>กรอกยอดจริงครบทุกสินค้า แล้วระบบจะแสดง variance และปรับ stock ให้ตรงยอดนับ</DialogDescription></DialogHeader>
          {countSessionQuery.isLoading ? <div className="flex h-40 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin" /></div> : (
            <div className="space-y-3">
              {(countSessionQuery.data?.items ?? []).map((item) => {
                const actual = countDrafts[item.id];
                const variance = actual === "" || actual === undefined ? null : Number(actual) - Number(item.expected_qty);
                return <div key={item.id} className="grid gap-2 rounded-lg border border-slate-200 p-3 sm:grid-cols-[1fr_140px_120px] sm:items-center"><div><p className="font-semibold">{item.product_name}</p><p className="text-xs text-slate-500">ระบบ {qty(item.expected_qty)} {item.unit_code ?? ""}</p></div><Input type="number" min="0" step="0.0001" value={actual ?? ""} onChange={(event) => setCountDrafts((current) => ({ ...current, [item.id]: event.target.value }))} placeholder="ยอดนับจริง" /><div className={`text-right text-sm font-bold ${variance === null || variance === 0 ? "text-slate-500" : variance > 0 ? "text-emerald-700" : "text-red-700"}`}>{variance === null ? "ยังไม่นับ" : `ต่าง ${variance > 0 ? "+" : ""}${qty(variance)}`}</div></div>;
              })}
            </div>
          )}
          <DialogFooter><Button variant="outline" onClick={() => setCountOpen(false)}>เก็บไว้นับต่อ</Button><Button disabled={countBusy || !countSessionQuery.data?.items.length} onClick={() => void completeDailyCount()}>{countBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ClipboardCheck className="h-4 w-4" />}ยืนยันยอดนับและปรับ stock</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SummaryCard({ icon, label, value }: { icon: JSX.Element; label: string; value: string }): JSX.Element {
  return <Card><CardContent className="flex items-center gap-3 p-4"><div className="rounded-lg bg-slate-100 p-2 text-slate-700">{icon}</div><div><p className="text-xs font-semibold text-slate-500">{label}</p><p className="text-xl font-black text-slate-950">{value}</p></div></CardContent></Card>;
}
