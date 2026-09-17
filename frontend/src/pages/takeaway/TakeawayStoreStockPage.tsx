import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Boxes, Loader2, Plus, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useToast } from "@/components/ui/use-toast";
import { takeawayApi, type TakeawayRecord } from "@/lib/takeawayApi";
import { useAuthStore } from "@/stores/auth.store";

function amount(value: unknown, digits = 2): string {
  const numeric = Number(value ?? 0);
  return Number.isFinite(numeric) ? numeric.toLocaleString("th-TH", { maximumFractionDigits: digits }) : "0";
}

export default function TakeawayStoreStockPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const canManage = useAuthStore((state) => state.hasPermission("takeaway.stock.manage"));
  const [locationId, setLocationId] = useState("");
  const [itemId, setItemId] = useState("");
  const [movementType, setMovementType] = useState<"receive" | "adjust" | "waste">("receive");
  const [quantity, setQuantity] = useState("1");
  const [unitCost, setUnitCost] = useState("0");
  const [note, setNote] = useState("");
  const contextQuery = useQuery({ queryKey: ["takeaway", "status"], queryFn: async () => (await takeawayApi.status()).data.data });
  const context = contextQuery.data;
  const locationsQuery = useQuery({ queryKey: ["takeaway", "locations", "store"], queryFn: async () => (await takeawayApi.stockLocations()).data.data });
  const catalogQuery = useQuery({
    queryKey: ["takeaway", "catalog", context?.brand_id, context?.branch_id],
    queryFn: async () => (await takeawayApi.catalog(context!.brand_id!, context!.branch_id)).data.data,
    enabled: Boolean(context?.brand_id && context?.branch_id),
  });
  const balancesQuery = useQuery({
    queryKey: ["takeaway", "stock", locationId],
    queryFn: async () => (await takeawayApi.stock(locationId || undefined)).data.data,
  });
  const movementsQuery = useQuery({
    queryKey: ["takeaway", "stock-movements", locationId],
    queryFn: async () => (await takeawayApi.stockMovements(locationId || undefined)).data.data,
  });
  const itemNames = new Map((catalogQuery.data ?? []).map((row) => [row.item.id, row.item]));
  const mutation = useMutation({
    mutationFn: () => {
      if (!context?.brand_id || !context.branch_id || !locationId || !itemId) throw new Error("กรุณาเลือกคลังและสินค้า");
      const rawQuantity = Number(quantity);
      if (!Number.isFinite(rawQuantity) || rawQuantity <= 0) throw new Error("จำนวนต้องมากกว่า 0");
      if (movementType !== "receive" && !note.trim()) throw new Error("การปรับยอดหรือของเสียต้องระบุเหตุผล");
      const quantityDelta = movementType === "waste" ? -rawQuantity : rawQuantity;
      return takeawayApi.stockMovement({
        location_id: locationId,
        item_id: itemId,
        quantity_delta: String(quantityDelta),
        unit_cost: unitCost || "0",
        movement_type: movementType,
        brand_id: context.brand_id,
        branch_id: context.branch_id,
        idempotency_key: `store-stock-${movementType}-${crypto.randomUUID()}`,
        note: note.trim() || undefined,
      });
    },
    onSuccess: async () => {
      setQuantity("1");
      setNote("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["takeaway", "stock"] }),
        queryClient.invalidateQueries({ queryKey: ["takeaway", "stock-movements"] }),
      ]);
      toast({ title: "บันทึกสต๊อกร้านแล้ว" });
    },
    onError: (error) => toast({ title: "บันทึกไม่สำเร็จ", description: error instanceof Error ? error.message : "ตรวจยอดสินค้า", variant: "destructive" }),
  });
  const balances = (balancesQuery.data ?? []) as TakeawayRecord[];
  const movements = (movementsQuery.data ?? []) as TakeawayRecord[];
  const busy = balancesQuery.isLoading || movementsQuery.isLoading;

  return <div className="space-y-5">
    <header className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-bold uppercase tracking-[0.22em] text-emerald-700">Store workspace</p><h1 className="mt-1 text-2xl font-black">สต๊อกร้านประจำวัน</h1><p className="mt-1 text-sm text-slate-500">ดูคงเหลือ รับเข้า ปรับยอด และบันทึกของเสียพร้อมเหตุผล</p></div><button onClick={() => void Promise.all([balancesQuery.refetch(), movementsQuery.refetch()])} className="flex items-center gap-2 rounded-xl border bg-white px-4 py-2 text-sm font-bold"><RefreshCw className="h-4 w-4" /> รีเฟรช</button></header>

    <div className="rounded-2xl border bg-white p-4 shadow-sm"><label className="text-xs font-bold text-slate-600">คลังของสาขา<select value={locationId} onChange={(event) => setLocationId(event.target.value)} className="mt-1 w-full max-w-lg rounded-xl border px-3 py-2 text-sm"><option value="">ทุกคลังของสาขา</option>{(locationsQuery.data ?? []).map((row) => <option key={row.id} value={row.id}>{String(row.name)} · {String(row.location_type)}</option>)}</select></label></div>

    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{balances.map((row) => { const item = itemNames.get(String(row.item_id)); const onHand = Number(row.on_hand_qty ?? 0); return <article key={row.id} className={`rounded-2xl border bg-white p-4 shadow-sm ${onHand <= 5 ? "border-amber-300" : "border-slate-200"}`}><div className="flex items-start justify-between gap-2"><div><p className="text-xs font-bold text-slate-400">{item?.sku ?? String(row.item_id).slice(0, 8)}</p><h2 className="mt-1 font-black">{item?.name ?? "สินค้า"}</h2></div>{onHand <= 5 ? <AlertTriangle className="h-5 w-5 text-amber-500" /> : <Boxes className="h-5 w-5 text-emerald-600" />}</div><p className={`mt-4 text-3xl font-black ${onHand <= 5 ? "text-amber-700" : "text-slate-950"}`}>{amount(onHand, 4)}</p><p className="text-xs text-slate-500">คงเหลือ · ต้นทุนเฉลี่ย ฿{amount(row.average_cost, 4)}</p></article>; })}{!busy && !balances.length ? <div className="col-span-full rounded-2xl border border-dashed bg-white p-10 text-center text-slate-500">ยังไม่มียอดสต๊อกในสาขา</div> : null}</section>

    {canManage ? <section className="rounded-2xl border bg-white p-5 shadow-sm"><h2 className="font-black">บันทึกความเคลื่อนไหว</h2><div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5"><label className="text-xs font-bold text-slate-600">รายการ<select value={movementType} onChange={(event) => setMovementType(event.target.value as "receive" | "adjust" | "waste")} className="mt-1 w-full rounded-xl border px-3 py-2 text-sm"><option value="receive">รับเข้า</option><option value="adjust">ปรับยอดเพิ่ม</option><option value="waste">ของเสีย/ตัดออก</option></select></label><label className="text-xs font-bold text-slate-600">สินค้า<select value={itemId} onChange={(event) => setItemId(event.target.value)} className="mt-1 w-full rounded-xl border px-3 py-2 text-sm"><option value="">เลือกสินค้า</option>{(catalogQuery.data ?? []).map((row) => <option key={row.item.id} value={row.item.id}>{row.item.name}</option>)}</select></label><label className="text-xs font-bold text-slate-600">จำนวน<input value={quantity} onChange={(event) => setQuantity(event.target.value)} inputMode="decimal" className="mt-1 w-full rounded-xl border px-3 py-2 text-sm" /></label><label className="text-xs font-bold text-slate-600">ต้นทุน/หน่วย<input value={unitCost} onChange={(event) => setUnitCost(event.target.value)} inputMode="decimal" className="mt-1 w-full rounded-xl border px-3 py-2 text-sm" /></label><label className="text-xs font-bold text-slate-600">เหตุผล<input value={note} onChange={(event) => setNote(event.target.value)} className="mt-1 w-full rounded-xl border px-3 py-2 text-sm" /></label></div><button disabled={mutation.isPending || !locationId} onClick={() => mutation.mutate()} className="mt-4 flex items-center gap-2 rounded-xl bg-slate-950 px-5 py-3 font-bold text-white disabled:opacity-40">{mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} บันทึก</button></section> : null}

    <section className="rounded-2xl border bg-white p-5 shadow-sm"><h2 className="font-black">รายการเคลื่อนไหวล่าสุด</h2><div className="mt-3 space-y-2">{movements.slice(0, 30).map((row) => <article key={row.id} className="grid gap-2 rounded-xl bg-slate-50 p-3 text-sm sm:grid-cols-[1fr_auto_auto] sm:items-center"><div><p className="font-bold">{itemNames.get(String(row.item_id))?.name ?? String(row.item_id).slice(0, 8)}</p><p className="text-xs text-slate-500">{String(row.note ?? row.movement_type)} · {new Date(String(row.occurred_at)).toLocaleString("th-TH")}</p></div><span className="text-slate-500">{String(row.movement_type)}</span><span className={`font-black ${Number(row.quantity_delta) < 0 ? "text-rose-700" : "text-emerald-700"}`}>{Number(row.quantity_delta) > 0 ? "+" : ""}{amount(row.quantity_delta, 4)}</span></article>)}{!busy && !movements.length ? <p className="rounded-xl border border-dashed p-8 text-center text-slate-500">ยังไม่มีความเคลื่อนไหว</p> : null}</div></section>
  </div>;
}
