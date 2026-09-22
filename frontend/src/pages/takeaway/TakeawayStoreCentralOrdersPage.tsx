import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ClipboardList, Loader2, PackageCheck, Plus, RefreshCw, Send, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useToast } from "@/components/ui/use-toast";
import { useTakeawayReleaseGate } from "@/hooks/useTakeawayReleaseGate";
import {
  takeawayApi,
  type TakeawayCatalogRow,
  type TakeawayCentralOrder,
} from "@/lib/takeawayApi";

type DraftLine = {
  key: string;
  catalog_item_id?: string;
  sku?: string;
  item_name: string;
  quantity: string;
  unit: string;
  source_kind: "catalog" | "extra" | "unlisted";
};

function today(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok" }).format(new Date());
}

const typeLabels = { regular: "ใบสั่งประจำ", extra: "ขอสินค้าเพิ่ม", unlisted: "สินค้านอกแคตตาล็อก" } as const;
const statusLabels: Record<string, string> = {
  submitted: "ส่งแล้ว",
  approved: "อนุมัติแล้ว",
  rejected: "ไม่อนุมัติ",
  in_production: "กำลังผลิต",
  packed: "แพ็กแล้ว",
  shipped: "กำลังส่ง",
  received: "รับแล้ว",
};

function randomId(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}`;
}

export default function TakeawayStoreCentralOrdersPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const releaseGate = useTakeawayReleaseGate();
  const writesEnabled = releaseGate.writesEnabled;
  const [orderType, setOrderType] = useState<"regular" | "extra" | "unlisted">("regular");
  const [selectedItemId, setSelectedItemId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [unlistedName, setUnlistedName] = useState("");
  const [unit, setUnit] = useState("ชิ้น");
  const [note, setNote] = useState("");
  const [deliveryDate, setDeliveryDate] = useState(today());
  const [lines, setLines] = useState<DraftLine[]>([]);
  const contextQuery = useQuery({ queryKey: ["takeaway", "status"], queryFn: async () => (await takeawayApi.status()).data.data });
  const context = contextQuery.data;
  const catalogQuery = useQuery({
    queryKey: ["takeaway", "catalog", context?.brand_id, context?.branch_id],
    queryFn: async () => (await takeawayApi.catalog(context!.brand_id!, context!.branch_id)).data.data,
    enabled: Boolean(context?.brand_id && context?.branch_id),
  });
  const ordersQuery = useQuery({
    queryKey: ["takeaway", "store-central-orders", context?.branch_id],
    queryFn: async () => (await takeawayApi.centralOrders({ branch_id: context!.branch_id! })).data.data,
    enabled: Boolean(context?.branch_id),
    refetchInterval: 15_000,
  });
  const catalogById = useMemo(
    () => new Map((catalogQuery.data ?? []).map((row) => [row.item.id, row])),
    [catalogQuery.data],
  );

  function addLine(): void {
    if (Number(quantity) <= 0) return;
    if (orderType === "unlisted") {
      if (!unlistedName.trim() || !unit.trim()) return;
      setLines((current) => [...current, {
        key: randomId(),
        item_name: unlistedName.trim(),
        quantity,
        unit: unit.trim(),
        source_kind: "unlisted",
      }]);
      setUnlistedName("");
      setQuantity("1");
      return;
    }
    const row = catalogById.get(selectedItemId) as TakeawayCatalogRow | undefined;
    if (!row) return;
    setLines((current) => [...current, {
      key: randomId(),
      catalog_item_id: row.item.id,
      sku: row.item.sku,
      item_name: row.item.name,
      quantity,
      unit: row.item.unit,
      source_kind: orderType === "regular" ? "catalog" : "extra",
    }]);
    setSelectedItemId("");
    setQuantity("1");
  }

  const submitMutation = useMutation({
    mutationFn: () => {
      if (!writesEnabled) throw new Error("การส่งใบสั่งยังถูกล็อกในช่วง Dark launch");
      if (!context?.branch_id) throw new Error("ไม่พบสาขา Takeaway");
      if (!lines.length) throw new Error("กรุณาเพิ่มสินค้าอย่างน้อยหนึ่งรายการ");
      const idempotencyKey = orderType === "regular"
        ? `store-regular:${context.branch_id}:${today()}:1`
        : `store-${orderType}:${context.branch_id}:${randomId()}`;
      return takeawayApi.createStoreCentralOrder({
        business_date: today(),
        round_no: 1,
        order_type: orderType,
        idempotency_key: idempotencyKey,
        requested_delivery_date: deliveryDate || undefined,
        note: note.trim() || undefined,
        items: lines.map(({ key: _key, ...line }) => line),
      });
    },
    onSuccess: async () => {
      setLines([]);
      setNote("");
      await queryClient.invalidateQueries({ queryKey: ["takeaway", "store-central-orders"] });
      toast({ title: "ส่งใบสั่งไปส่วนกลางแล้ว", description: typeLabels[orderType] });
    },
    onError: (error) => toast({
      title: "ส่งใบสั่งไม่สำเร็จ",
      description: error instanceof Error ? error.message : "ตรวจรายการและลองอีกครั้ง",
      variant: "destructive",
    }),
  });
  const receiveMutation = useMutation({
    mutationFn: (orderId: string) => {
      if (!writesEnabled) throw new Error("การรับสินค้ายังถูกล็อกในช่วง Dark launch");
      return takeawayApi.receiveStoreCentralOrder(orderId);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["takeaway", "store-central-orders"] }),
        queryClient.invalidateQueries({ queryKey: ["takeaway", "stock"] }),
      ]);
      toast({ title: "รับสินค้าเข้าสต๊อกร้านแล้ว" });
    },
    onError: () => toast({ title: "รับสินค้าไม่สำเร็จ", description: "รับได้เมื่อส่วนกลางเปลี่ยนสถานะเป็นกำลังส่งแล้ว", variant: "destructive" }),
  });
  const orders = (ordersQuery.data ?? []) as TakeawayCentralOrder[];

  return <div className="space-y-5">
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div><p className="text-xs font-bold uppercase tracking-[0.22em] text-emerald-700">Store workspace</p><h1 className="mt-1 text-2xl font-black">สั่งสินค้าจากส่วนกลาง</h1><p className="mt-1 text-sm text-slate-500">ใบสั่งประจำ · ขอเพิ่ม · สินค้านอกแคตตาล็อก · ยืนยันรับเข้าสต๊อก</p></div>
      <button onClick={() => void ordersQuery.refetch()} className="flex items-center gap-2 rounded-xl border bg-white px-4 py-2 text-sm font-bold"><RefreshCw className="h-4 w-4" /> รีเฟรช</button>
    </header>

    {writesEnabled ? <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap gap-2">{(["regular", "extra", "unlisted"] as const).map((value) => <button key={value} onClick={() => { setOrderType(value); setLines([]); }} className={`rounded-xl px-4 py-2 text-sm font-black ${orderType === value ? "bg-emerald-500 text-slate-950" : "bg-slate-100 text-slate-600"}`}>{typeLabels[value]}</button>)}</div>
      <div className="mt-4 grid gap-3 md:grid-cols-[1fr_120px_110px] md:items-end">
        {orderType === "unlisted" ? <label className="text-xs font-bold text-slate-600">ชื่อสินค้าที่ต้องการ<input value={unlistedName} onChange={(event) => setUnlistedName(event.target.value)} className="mt-1 w-full rounded-xl border px-3 py-2 text-sm" /></label> : <label className="text-xs font-bold text-slate-600">สินค้า<select value={selectedItemId} onChange={(event) => setSelectedItemId(event.target.value)} className="mt-1 w-full rounded-xl border px-3 py-2 text-sm"><option value="">เลือกสินค้า</option>{(catalogQuery.data ?? []).map((row) => <option key={row.item.id} value={row.item.id}>{row.item.name} · {row.item.unit}</option>)}</select></label>}
        <label className="text-xs font-bold text-slate-600">จำนวน<input value={quantity} onChange={(event) => setQuantity(event.target.value)} inputMode="decimal" className="mt-1 w-full rounded-xl border px-3 py-2 text-sm" /></label>
        {orderType === "unlisted" ? <label className="text-xs font-bold text-slate-600">หน่วย<input value={unit} onChange={(event) => setUnit(event.target.value)} className="mt-1 w-full rounded-xl border px-3 py-2 text-sm" /></label> : <button onClick={addLine} className="flex items-center justify-center gap-2 rounded-xl bg-slate-950 px-4 py-2 font-bold text-white"><Plus className="h-4 w-4" /> เพิ่ม</button>}
      </div>
      {orderType === "unlisted" ? <button onClick={addLine} className="mt-3 flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-2 text-sm font-bold text-white"><Plus className="h-4 w-4" /> เพิ่มรายการนอกแคตตาล็อก</button> : null}
      <div className="mt-4 space-y-2">{lines.map((line) => <div key={line.key} className="flex items-center justify-between rounded-xl bg-slate-50 p-3"><div><p className="font-bold">{line.item_name}</p><p className="text-xs text-slate-500">{line.quantity} {line.unit} · {line.source_kind}</p></div><button onClick={() => setLines((current) => current.filter((item) => item.key !== line.key))} className="rounded-lg p-2 text-rose-600"><Trash2 className="h-4 w-4" /></button></div>)}</div>
      <div className="mt-4 grid gap-3 md:grid-cols-2"><label className="text-xs font-bold text-slate-600">ต้องการรับวันที่<input type="date" value={deliveryDate} onChange={(event) => setDeliveryDate(event.target.value)} className="mt-1 w-full rounded-xl border px-3 py-2 text-sm" /></label><label className="text-xs font-bold text-slate-600">หมายเหตุ<input value={note} onChange={(event) => setNote(event.target.value)} className="mt-1 w-full rounded-xl border px-3 py-2 text-sm" /></label></div>
      <button disabled={!lines.length || submitMutation.isPending} onClick={() => submitMutation.mutate()} className="mt-4 flex items-center gap-2 rounded-xl bg-emerald-500 px-5 py-3 font-black text-slate-950 disabled:opacity-40">{submitMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} ส่งใบสั่ง</button>
    </section> : <section className="rounded-2xl border border-amber-300 bg-amber-50 p-5 text-sm font-bold text-amber-950">โหมดอ่านอย่างเดียว — ดูประวัติใบสั่งได้ แต่การสร้างใบสั่งและรับสินค้าเข้าสต๊อกยังถูกปิดที่ Server</section>}

    <section className="space-y-3">
      <h2 className="flex items-center gap-2 font-black"><ClipboardList className="h-5 w-5 text-emerald-700" /> ประวัติใบสั่งของสาขา</h2>
      {ordersQuery.isLoading ? <div className="flex justify-center p-10"><Loader2 className="h-7 w-7 animate-spin text-emerald-600" /></div> : orders.length ? orders.map((order) => <article key={order.id} className="rounded-2xl border bg-white p-4 shadow-sm"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-black">{order.order_number}</p><p className="mt-1 text-xs text-slate-500">{typeLabels[order.order_type]} · ต้องการรับ {order.requested_delivery_date ?? "ไม่ระบุ"}</p></div><div className="flex items-center gap-2"><span className={`rounded-full px-3 py-1 text-xs font-bold ${order.status === "received" ? "bg-emerald-100 text-emerald-800" : order.status === "rejected" ? "bg-rose-100 text-rose-800" : "bg-amber-100 text-amber-800"}`}>{statusLabels[order.status] ?? order.status}</span>{order.status === "shipped" ? <button disabled={!writesEnabled || receiveMutation.isPending} onClick={() => receiveMutation.mutate(order.id)} className="flex items-center gap-2 rounded-xl bg-emerald-500 px-3 py-2 text-sm font-black disabled:opacity-40"><PackageCheck className="h-4 w-4" /> รับของครบ</button> : null}</div></div><div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">{(order.items ?? []).map((item) => <div key={item.id} className="rounded-xl bg-slate-50 p-3 text-sm"><p className="font-bold">{item.item_name}</p><p className="text-xs text-slate-500">{item.quantity} {item.unit} · {item.source_kind}</p></div>)}</div>{order.status === "received" ? <p className="mt-3 flex items-center gap-2 text-sm font-bold text-emerald-700"><CheckCircle2 className="h-4 w-4" /> รับเข้าสต๊อกร้านแล้ว</p> : null}</article>) : <div className="rounded-2xl border border-dashed bg-white p-10 text-center text-slate-500">ยังไม่มีใบสั่งของสาขา</div>}
    </section>
  </div>;
}
