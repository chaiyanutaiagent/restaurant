import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Minus, Plus, QrCode, ReceiptText, ShoppingCart } from "lucide-react";
import { useMemo, useState } from "react";
import { useToast } from "@/components/ui/use-toast";
import { takeawayApi, type TakeawayCatalogRow } from "@/lib/takeawayApi";
import QRCode from "qrcode";

type CartLine = { row: TakeawayCatalogRow; quantity: number };

function businessDate(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok" }).format(new Date());
}

function money(value: number): string {
  return new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(value);
}

export default function TakeawayCounterPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [cart, setCart] = useState<CartLine[]>([]);
  const [openingCash, setOpeningCash] = useState("0");
  const [lastQueue, setLastQueue] = useState<number | null>(null);
  const [pickupQr, setPickupQr] = useState("");
  const [orderingQr, setOrderingQr] = useState("");
  const contextQuery = useQuery({ queryKey: ["takeaway", "status"], queryFn: async () => (await takeawayApi.status()).data.data });
  const context = contextQuery.data;
  const categoriesQuery = useQuery({
    queryKey: ["takeaway", "categories", context?.brand_id],
    queryFn: async () => (await takeawayApi.categories(context!.brand_id!)).data.data,
    enabled: Boolean(context?.brand_id),
  });
  const catalogQuery = useQuery({
    queryKey: ["takeaway", "catalog", context?.brand_id, context?.branch_id],
    queryFn: async () => (await takeawayApi.catalog(context!.brand_id!, context?.branch_id)).data.data,
    enabled: Boolean(context?.brand_id && context?.branch_id),
  });
  const shiftsQuery = useQuery({ queryKey: ["takeaway", "shifts"], queryFn: async () => (await takeawayApi.shifts()).data.data });
  const pendingOrdersQuery = useQuery({
    queryKey: ["takeaway", "orders", "awaiting_payment", context?.branch_id],
    queryFn: async () => (await takeawayApi.orders({ branch_id: context!.branch_id!, fulfillment_status: "awaiting_payment" })).data.data,
    enabled: Boolean(context?.branch_id),
    refetchInterval: 5_000,
  });
  const openShift = shiftsQuery.data?.find((row) => row.status === "open");
  const openShiftMutation = useMutation({
    mutationFn: () => takeawayApi.openShift({ business_date: businessDate(), opening_cash: openingCash || "0" }),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["takeaway", "shifts"] }); toast({ title: "เปิดกะแล้ว", description: "พร้อมรับรายการขาย" }); },
    onError: () => toast({ title: "เปิดกะไม่สำเร็จ", description: "ตรวจสาขาและสิทธิ์อีกครั้ง", variant: "destructive" }),
  });
  const saleMutation = useMutation({
    mutationFn: async () => {
      if (!context?.brand_id || !context.branch_id || !openShift) throw new Error("กรุณาเปิดกะก่อนขาย");
      const total = cart.reduce((sum, line) => sum + Number(line.row.effective_price) * line.quantity * (1 + Number(line.row.item.tax_rate ?? 0) / 100), 0);
      return takeawayApi.createSale({
        brand_id: context.brand_id,
        branch_id: context.branch_id,
        shift_id: openShift.id,
        idempotency_key: `web-sale-${crypto.randomUUID()}`,
        channel: "counter",
        items: cart.map((line) => ({ catalog_item_id: line.row.item.id, quantity: String(line.quantity) })),
        discount_amount: "0",
        payment: { method: "cash", amount: total.toFixed(2), idempotency_key: `web-payment-${crypto.randomUUID()}` },
      });
    },
    onSuccess: async (response) => {
      const order = response.data.data.order;
      const pickupToken = response.data.data.pickup_token;
      setLastQueue(Number(order.queue_number));
      if (pickupToken) {
        const url = `${window.location.origin}/takeaway/pickup-status/${pickupToken}`;
        setPickupQr(await QRCode.toDataURL(url, { width: 240, margin: 2, color: { dark: "#0f172a" } }));
      } else {
        setPickupQr("");
      }
      setCart([]);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["takeaway", "orders"] }),
        queryClient.invalidateQueries({ queryKey: ["takeaway", "stock"] }),
      ]);
      toast({ title: `รับเงินแล้ว · คิว ${String(order.queue_number)}`, description: String(order.order_number) });
    },
    onError: (error) => toast({ title: "ขายไม่สำเร็จ", description: error instanceof Error ? error.message : "กรุณาตรวจสต๊อกและยอดชำระ", variant: "destructive" }),
  });
  const orderingLinkMutation = useMutation({
    mutationFn: () => takeawayApi.createOrderingLink(12),
    onSuccess: async (response) => {
      const url = `${window.location.origin}/takeaway/order/${response.data.data.token}`;
      setOrderingQr(await QRCode.toDataURL(url, { width: 260, margin: 2, color: { dark: "#0f172a" } }));
    },
    onError: () => toast({ title: "สร้าง QR ไม่สำเร็จ", variant: "destructive" }),
  });
  const captureMutation = useMutation({
    mutationFn: (order: Record<string, unknown> & { id: string }) => takeawayApi.captureOrderPayment(order.id, {
      payment: {
        method: "cash",
        amount: String(order.total_amount),
        idempotency_key: `web-qr-payment-${crypto.randomUUID()}`,
      },
    }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["takeaway", "orders"] });
      toast({ title: "รับชำระแล้ว", description: "ออเดอร์ถูกส่งเข้าครัว" });
    },
    onError: () => toast({ title: "รับชำระไม่สำเร็จ", description: "ตรวจยอดเงินและสต๊อก", variant: "destructive" }),
  });
  const visibleItems = (catalogQuery.data ?? []).filter((row) => row.is_available && (!categoryId || row.item.category_id === categoryId));
  const subtotal = useMemo(() => cart.reduce((sum, line) => sum + Number(line.row.effective_price) * line.quantity, 0), [cart]);
  const tax = useMemo(() => cart.reduce((sum, line) => sum + Number(line.row.effective_price) * line.quantity * Number(line.row.item.tax_rate ?? 0) / 100, 0), [cart]);
  const total = subtotal + tax;
  const adjust = (row: TakeawayCatalogRow, delta: number): void => setCart((current) => {
    const found = current.find((line) => line.row.item.id === row.item.id);
    if (!found && delta > 0) return [...current, { row, quantity: 1 }];
    return current.map((line) => line.row.item.id === row.item.id ? { ...line, quantity: line.quantity + delta } : line).filter((line) => line.quantity > 0);
  });

  if (!contextQuery.isLoading && (!context?.brand_id || !context.branch_id)) {
    return <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-amber-900">กรุณาเลือกสาขาของแบรนด์ Takeaway ก่อนเปิดหน้าขาย</div>;
  }
  return (
    <div className="grid min-h-[calc(100vh-7rem)] gap-4 xl:grid-cols-[1fr_420px]">
      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-white p-4 shadow-sm">
          <div><h1 className="text-xl font-black">ขายหน้าร้าน</h1><p className="text-sm text-slate-500">ชำระก่อนผลิต · รับเลขคิวอัตโนมัติ</p></div>
          <button disabled={!openShift || orderingLinkMutation.isPending} onClick={() => orderingLinkMutation.mutate()} className="flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2 text-sm font-bold disabled:opacity-40"><QrCode className="h-4 w-4" /> QR ลูกค้าสั่งเอง</button>
          {openShift ? <span className="rounded-full bg-emerald-100 px-4 py-2 text-sm font-bold text-emerald-700">กะ #{String(openShift.round_no)} เปิดอยู่</span> : <div className="flex gap-2"><input className="w-28 rounded-xl border px-3 py-2" inputMode="decimal" value={openingCash} onChange={(event) => setOpeningCash(event.target.value)} /><button className="rounded-xl bg-slate-950 px-4 py-2 font-bold text-white" onClick={() => openShiftMutation.mutate()}>เปิดกะ</button></div>}
        </div>
        {orderingQr ? <div className="flex flex-wrap items-center gap-5 rounded-2xl border border-emerald-200 bg-emerald-50 p-4"><img src={orderingQr} alt="QR ลูกค้าสั่งเอง" className="h-36 w-36 rounded-xl bg-white p-2" /><div><h2 className="font-black text-emerald-950">QR สั่งอาหารของสาขา</h2><p className="mt-1 text-sm text-emerald-800">ใช้ได้ 12 ชั่วโมง ลูกค้าสั่งแล้วรายการจะรอรับชำระที่เคาน์เตอร์ก่อนส่งครัว</p><button onClick={() => window.print()} className="mt-3 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-bold text-white">พิมพ์ QR</button></div></div> : null}
        {(pendingOrdersQuery.data ?? []).length ? <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4"><h2 className="font-black text-amber-950">ออเดอร์ QR รอชำระ</h2><div className="mt-3 grid gap-2">{(pendingOrdersQuery.data ?? []).map((order) => <div key={order.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white p-3"><div><p className="font-black">คิว {String(order.queue_number)} · {String(order.order_number)}</p><p className="text-sm text-slate-500">ยอด {money(Number(order.total_amount))}</p></div><button disabled={captureMutation.isPending} onClick={() => captureMutation.mutate(order)} className="rounded-xl bg-slate-950 px-4 py-2 text-sm font-bold text-white">รับเงินสดและส่งครัว</button></div>)}</div></div> : null}
        <div className="flex gap-2 overflow-x-auto rounded-2xl bg-white p-3 shadow-sm">
          <button onClick={() => setCategoryId(null)} className={`min-w-fit rounded-xl px-4 py-2 text-sm font-bold ${categoryId === null ? "bg-emerald-500 text-slate-950" : "bg-slate-100"}`}>ทั้งหมด</button>
          {(categoriesQuery.data ?? []).map((category) => <button key={category.id} onClick={() => setCategoryId(category.id)} className={`min-w-fit rounded-xl px-4 py-2 text-sm font-bold ${categoryId === category.id ? "bg-emerald-500 text-slate-950" : "bg-slate-100"}`}>{String(category.name)}</button>)}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {visibleItems.map((row) => <button key={row.item.id} onClick={() => adjust(row, 1)} className="min-h-36 rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:border-emerald-400 hover:shadow-md"><p className="text-xs font-bold text-slate-400">{row.item.sku}</p><h2 className="mt-2 font-black">{row.item.name}</h2><p className="mt-6 text-xl font-black text-emerald-700">{money(Number(row.effective_price))}</p></button>)}
          {!catalogQuery.isLoading && visibleItems.length === 0 ? <div className="col-span-full rounded-2xl border border-dashed bg-white p-10 text-center text-slate-500">ยังไม่มีสินค้าพร้อมขายในหมวดนี้</div> : null}
        </div>
      </section>
      <aside className="flex min-h-[620px] flex-col overflow-hidden rounded-3xl bg-slate-950 text-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-800 p-5"><div><h2 className="flex items-center gap-2 text-lg font-black"><ShoppingCart className="h-5 w-5" /> ตะกร้า</h2><p className="text-xs text-slate-400">{cart.length} รายการ</p></div>{lastQueue ? <span className="rounded-xl bg-emerald-500 px-3 py-2 font-black text-slate-950">คิวล่าสุด {lastQueue}</span> : null}</div>
        {pickupQr && lastQueue ? <div className="border-b border-slate-800 bg-white p-4 text-center text-slate-950"><img className="mx-auto h-36 w-36" src={pickupQr} alt={`QR ติดตามคิว ${lastQueue}`} /><p className="mt-2 font-black">สแกนติดตามคิว {lastQueue}</p><p className="text-xs text-slate-500">ลูกค้าเปิดดูสถานะได้โดยไม่ต้องเข้าสู่ระบบ</p></div> : null}
        <div className="flex-1 space-y-3 overflow-y-auto p-4">{cart.map((line) => <div key={line.row.item.id} className="rounded-2xl bg-slate-900 p-4"><div className="flex justify-between gap-3"><div><p className="font-bold">{line.row.item.name}</p><p className="text-sm text-emerald-400">{money(Number(line.row.effective_price) * line.quantity)}</p></div><div className="flex items-center gap-2"><button className="rounded-lg bg-slate-800 p-2" onClick={() => adjust(line.row, -1)}><Minus className="h-4 w-4" /></button><span className="w-5 text-center font-bold">{line.quantity}</span><button className="rounded-lg bg-emerald-500 p-2 text-slate-950" onClick={() => adjust(line.row, 1)}><Plus className="h-4 w-4" /></button></div></div></div>)}{cart.length === 0 ? <div className="grid h-full place-items-center text-center text-slate-500"><div><ShoppingCart className="mx-auto h-12 w-12" /><p className="mt-3">เลือกสินค้าเพื่อเริ่มขาย</p></div></div> : null}</div>
        <div className="space-y-2 border-t border-slate-800 p-5"><div className="flex justify-between text-sm text-slate-400"><span>สินค้า</span><span>{money(subtotal)}</span></div><div className="flex justify-between text-sm text-slate-400"><span>ภาษี</span><span>{money(tax)}</span></div><div className="flex justify-between text-2xl font-black"><span>สุทธิ</span><span>{money(total)}</span></div><button disabled={!openShift || cart.length === 0 || saleMutation.isPending} onClick={() => saleMutation.mutate()} className="mt-3 flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-500 py-4 text-lg font-black text-slate-950 disabled:opacity-40"><ReceiptText className="h-5 w-5" />{saleMutation.isPending ? "กำลังรับชำระ" : "รับเงินสดและส่งครัว"}</button></div>
      </aside>
    </div>
  );
}
