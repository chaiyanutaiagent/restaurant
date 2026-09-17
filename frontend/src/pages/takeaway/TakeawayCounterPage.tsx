import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CloudOff, Minus, Plus, Printer, QrCode, ReceiptText, RefreshCw, ShoppingCart } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useReactToPrint } from "react-to-print";
import TakeawayReceiptSlip from "@/components/takeaway/TakeawayReceiptSlip";
import { useToast } from "@/components/ui/use-toast";
import { takeawayApi, type TakeawayCatalogRow, type TakeawayReceipt } from "@/lib/takeawayApi";
import {
  getTakeawayOutboxSummary,
  loadTakeawayWorkspace,
  markTakeawayReceiptPrinted,
  queueTakeawaySale,
  refreshTakeawayWorkspace,
  retryTakeawayNeedsReview,
  syncTakeawayPendingSales,
} from "@/lib/takeawayOffline";
import QRCode from "qrcode";
import { printTakeawayReceipt } from "@/lib/takeawayPrinter";

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
  const [lastReceipt, setLastReceipt] = useState<TakeawayReceipt | null>(null);
  const [lastClientSaleId, setLastClientSaleId] = useState<string | null>(null);
  const [receiptCopyType, setReceiptCopyType] = useState<"customer" | "merchant">("customer");
  const receiptRef = useRef<HTMLDivElement | null>(null);
  const workspaceQuery = useQuery({
    queryKey: ["takeaway", "offline-workspace"],
    queryFn: loadTakeawayWorkspace,
    networkMode: "always",
  });
  const context = workspaceQuery.data?.context;
  const categories = workspaceQuery.data?.categories ?? [];
  const catalog = workspaceQuery.data?.catalog ?? [];
  const shifts = workspaceQuery.data?.shifts ?? [];
  const outboxQuery = useQuery({
    queryKey: ["takeaway", "outbox"],
    queryFn: getTakeawayOutboxSummary,
    refetchInterval: 5_000,
    networkMode: "always",
  });
  const pendingOrdersQuery = useQuery({
    queryKey: ["takeaway", "orders", "awaiting_payment", context?.branch_id],
    queryFn: async () => (await takeawayApi.orders({ branch_id: context!.branch_id!, fulfillment_status: "awaiting_payment" })).data.data,
    enabled: Boolean(context?.branch_id),
    refetchInterval: 5_000,
  });
  const recentOrdersQuery = useQuery({
    queryKey: ["takeaway", "orders", "recent", context?.branch_id],
    queryFn: async () => (await takeawayApi.orders({ branch_id: context!.branch_id!, limit: 8 })).data.data,
    enabled: Boolean(context?.branch_id),
  });
  const openShift = shifts.find((row) => row.status === "open");
  const browserPrintReceipt = useReactToPrint({
    contentRef: receiptRef,
    onAfterPrint: () => {
      if (!lastReceipt) return;
      void markTakeawayReceiptPrinted(lastClientSaleId, lastReceipt.order_id, receiptCopyType)
        .then(setLastReceipt)
        .catch(() => toast({ title: "พิมพ์แล้ว แต่บันทึกประวัติไม่สำเร็จ", variant: "destructive" }));
    },
  });
  const printReceipt = async (
    receipt: TakeawayReceipt,
    copyType: "customer" | "merchant",
    clientSaleId: string | null = lastClientSaleId,
  ): Promise<void> => {
    setLastReceipt(receipt);
    setReceiptCopyType(copyType);
    try {
      if (await printTakeawayReceipt(receipt, copyType)) {
        setLastReceipt(await markTakeawayReceiptPrinted(clientSaleId, receipt.order_id, copyType));
        toast({ title: "พิมพ์ใบเสร็จผ่าน Bluetooth แล้ว" });
        return;
      }
    } catch (error) {
      toast({
        title: "เครื่องพิมพ์ Bluetooth ไม่พร้อม",
        description: error instanceof Error ? error.message : "กำลังเปิดหน้าต่างพิมพ์แทน",
        variant: "destructive",
      });
    }
    window.setTimeout(() => browserPrintReceipt(), 0);
  };
  useEffect(() => {
    const synchronize = (): void => {
      void syncTakeawayPendingSales()
        .then(() => outboxQuery.refetch())
        .catch(() => undefined);
    };
    window.addEventListener("online", synchronize);
    return () => window.removeEventListener("online", synchronize);
  }, [outboxQuery]);
  const openShiftMutation = useMutation({
    mutationFn: () => takeawayApi.openShift({ business_date: businessDate(), opening_cash: openingCash || "0" }),
    onSuccess: async () => { await refreshTakeawayWorkspace(); await queryClient.invalidateQueries({ queryKey: ["takeaway", "offline-workspace"] }); toast({ title: "เปิดกะแล้ว", description: "พร้อมรับรายการขาย" }); },
    onError: () => toast({ title: "เปิดกะไม่สำเร็จ", description: "ตรวจสาขาและสิทธิ์อีกครั้ง", variant: "destructive" }),
  });
  const saleMutation = useMutation({
    networkMode: "always",
    mutationFn: async () => {
      if (!context?.brand_id || !context.branch_id || !openShift) throw new Error("กรุณาเปิดกะก่อนขาย");
      const total = cart.reduce((sum, line) => sum + Number(line.row.effective_price) * line.quantity * (1 + Number(line.row.item.tax_rate ?? 0) / 100), 0);
      return queueTakeawaySale({
        brand_id: context.brand_id,
        branch_id: context.branch_id,
        shift_id: openShift.id,
        channel: "counter",
        items: cart.map((line) => ({ catalog_item_id: line.row.item.id, quantity: String(line.quantity) })),
        discount_amount: "0",
        payment: { method: "cash", amount: total.toFixed(2) },
      }, catalog);
    },
    onSuccess: async (result) => {
      const order = result.order;
      const pickupToken = result.pickupToken;
      const queueNumber = order.queue_number == null ? null : Number(order.queue_number);
      setLastQueue(queueNumber);
      setLastReceipt(result.receipt);
      setLastClientSaleId(result.clientSaleId);
      if (pickupToken) {
        const url = `${window.location.origin}/takeaway/pickup-status/${pickupToken}`;
        setPickupQr(await QRCode.toDataURL(url, { width: 240, margin: 2, color: { dark: "#0f172a" } }));
      } else {
        setPickupQr("");
      }
      setCart([]);
      await outboxQuery.refetch();
      if (result.status === "synced") {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["takeaway", "orders"] }),
          queryClient.invalidateQueries({ queryKey: ["takeaway", "stock"] }),
        ]);
      } else {
        void queryClient.invalidateQueries({ queryKey: ["takeaway", "orders"], refetchType: "none" });
        void queryClient.invalidateQueries({ queryKey: ["takeaway", "stock"], refetchType: "none" });
      }
      toast({
        title: result.status === "synced" ? `รับเงินแล้ว · คิว ${String(order.queue_number)}` : "เก็บรายการไว้ในเครื่องแล้ว",
        description: result.status === "synced" ? String(order.order_number) : "ระบบจะส่งรายการอัตโนมัติเมื่อเชื่อมต่อได้",
      });
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
  const reprintMutation = useMutation({
    mutationFn: async (orderId: string) => (await takeawayApi.receipt(orderId)).data.data,
    onSuccess: (receipt) => {
      setLastReceipt(receipt);
      setLastClientSaleId(null);
      setReceiptCopyType("customer");
      void printReceipt(receipt, "customer", null);
    },
    onError: () => toast({ title: "เรียกใบเสร็จไม่สำเร็จ", variant: "destructive" }),
  });
  const visibleItems = catalog.filter((row) => row.is_available && (!categoryId || row.item.category_id === categoryId));
  const subtotal = useMemo(() => cart.reduce((sum, line) => sum + Number(line.row.effective_price) * line.quantity, 0), [cart]);
  const tax = useMemo(() => cart.reduce((sum, line) => sum + Number(line.row.effective_price) * line.quantity * Number(line.row.item.tax_rate ?? 0) / 100, 0), [cart]);
  const total = subtotal + tax;
  const adjust = (row: TakeawayCatalogRow, delta: number): void => setCart((current) => {
    const found = current.find((line) => line.row.item.id === row.item.id);
    if (!found && delta > 0) return [...current, { row, quantity: 1 }];
    return current.map((line) => line.row.item.id === row.item.id ? { ...line, quantity: line.quantity + delta } : line).filter((line) => line.quantity > 0);
  });

  if (!workspaceQuery.isLoading && (!context?.brand_id || !context.branch_id)) {
    return <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-amber-900">กรุณาเลือกสาขาของแบรนด์ Takeaway ก่อนเปิดหน้าขาย</div>;
  }
  return (
    <div className="grid min-h-[calc(100vh-10rem)] items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(360px,420px)] xl:min-h-[calc(100vh-3.5rem)]">
      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-white p-4 shadow-sm">
          <div><h1 className="text-xl font-black">ขายหน้าร้าน</h1><p className="text-sm text-slate-500">ชำระก่อนผลิต · ขายต่อได้เมื่อเน็ตหลุด · ส่งซ้ำไม่เกิดบิลซ้ำ</p></div>
          <button onClick={() => void syncTakeawayPendingSales().then(() => outboxQuery.refetch())} className="flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2 text-sm font-bold"><RefreshCw className="h-4 w-4" /> ส่งรายการค้าง</button>
          <button disabled={!openShift || orderingLinkMutation.isPending} onClick={() => orderingLinkMutation.mutate()} className="flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2 text-sm font-bold disabled:opacity-40"><QrCode className="h-4 w-4" /> QR ลูกค้าสั่งเอง</button>
          {openShift ? <span className="rounded-full bg-emerald-100 px-4 py-2 text-sm font-bold text-emerald-700">กะ #{String(openShift.round_no)} เปิดอยู่</span> : <div className="flex gap-2"><input className="w-28 rounded-xl border px-3 py-2" inputMode="decimal" value={openingCash} onChange={(event) => setOpeningCash(event.target.value)} /><button className="rounded-xl bg-slate-950 px-4 py-2 font-bold text-white" onClick={() => openShiftMutation.mutate()}>เปิดกะ</button></div>}
        </div>
        {(outboxQuery.data?.pending || outboxQuery.data?.syncing || outboxQuery.data?.needsReview) ? <div className={`flex flex-wrap items-center justify-between gap-3 rounded-2xl border p-4 ${outboxQuery.data.needsReview ? "border-amber-300 bg-amber-50" : "border-sky-200 bg-sky-50"}`}><div className="flex items-center gap-3">{outboxQuery.data.needsReview ? <AlertTriangle className="h-5 w-5 text-amber-700" /> : <CloudOff className="h-5 w-5 text-sky-700" />}<div><p className="font-black">รายการในเครื่อง: รอส่ง {outboxQuery.data.pending} · กำลังส่ง {outboxQuery.data.syncing} · ต้องตรวจ {outboxQuery.data.needsReview}</p>{outboxQuery.data.latestError ? <p className="text-xs text-amber-800">{outboxQuery.data.latestError}</p> : null}</div></div>{outboxQuery.data.needsReview ? <button onClick={() => void retryTakeawayNeedsReview().then(() => outboxQuery.refetch())} className="rounded-xl bg-amber-500 px-4 py-2 text-sm font-black">ลองส่งอีกครั้ง</button> : null}</div> : null}
        {orderingQr ? <div className="flex flex-wrap items-center gap-5 rounded-2xl border border-emerald-200 bg-emerald-50 p-4"><img src={orderingQr} alt="QR ลูกค้าสั่งเอง" className="h-36 w-36 rounded-xl bg-white p-2" /><div><h2 className="font-black text-emerald-950">QR สั่งอาหารของสาขา</h2><p className="mt-1 text-sm text-emerald-800">ใช้ได้ 12 ชั่วโมง ลูกค้าสั่งแล้วรายการจะรอรับชำระที่เคาน์เตอร์ก่อนส่งครัว</p><button onClick={() => window.print()} className="mt-3 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-bold text-white">พิมพ์ QR</button></div></div> : null}
        {(pendingOrdersQuery.data ?? []).length ? <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4"><h2 className="font-black text-amber-950">ออเดอร์ QR รอชำระ</h2><div className="mt-3 grid gap-2">{(pendingOrdersQuery.data ?? []).map((order) => <div key={order.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white p-3"><div><p className="font-black">คิว {String(order.queue_number)} · {String(order.order_number)}</p><p className="text-sm text-slate-500">ยอด {money(Number(order.total_amount))}</p></div><button disabled={captureMutation.isPending} onClick={() => captureMutation.mutate(order)} className="rounded-xl bg-slate-950 px-4 py-2 text-sm font-bold text-white">รับเงินสดและส่งครัว</button></div>)}</div></div> : null}
        <div className="flex gap-2 overflow-x-auto rounded-2xl bg-white p-3 shadow-sm">
          <button onClick={() => setCategoryId(null)} className={`min-w-fit rounded-xl px-4 py-2 text-sm font-bold ${categoryId === null ? "bg-emerald-500 text-slate-950" : "bg-slate-100"}`}>ทั้งหมด</button>
          {categories.map((category) => <button key={category.id} onClick={() => setCategoryId(category.id)} className={`min-w-fit rounded-xl px-4 py-2 text-sm font-bold ${categoryId === category.id ? "bg-emerald-500 text-slate-950" : "bg-slate-100"}`}>{String(category.name)}</button>)}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {visibleItems.map((row) => <button key={row.item.id} onClick={() => adjust(row, 1)} className="min-h-36 rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:border-emerald-400 hover:shadow-md"><p className="text-xs font-bold text-slate-400">{row.item.sku}</p><h2 className="mt-2 font-black">{row.item.name}</h2><p className="mt-6 text-xl font-black text-emerald-700">{money(Number(row.effective_price))}</p></button>)}
          {!workspaceQuery.isLoading && visibleItems.length === 0 ? <div className="col-span-full rounded-2xl border border-dashed bg-white p-10 text-center text-slate-500">ยังไม่มีสินค้าพร้อมขายในหมวดนี้</div> : null}
        </div>
        {(recentOrdersQuery.data ?? []).length ? <div className="rounded-2xl border bg-white p-4 shadow-sm"><h2 className="font-black">บิลล่าสุด</h2><div className="mt-3 flex gap-2 overflow-x-auto">{(recentOrdersQuery.data ?? []).slice(0, 8).map((order) => <button key={order.id} disabled={reprintMutation.isPending} onClick={() => reprintMutation.mutate(order.id)} className="min-w-fit rounded-xl border px-3 py-2 text-left text-sm"><span className="font-black">คิว {String(order.queue_number ?? "-")}</span><span className="ml-2 text-slate-500">{money(Number(order.total_amount))}</span><Printer className="ml-2 inline h-4 w-4" /></button>)}</div></div> : null}
      </section>
      <aside className="flex min-h-[620px] flex-col overflow-hidden rounded-3xl bg-slate-950 text-white shadow-xl lg:sticky lg:top-5 lg:h-[calc(100vh-2.5rem)] lg:min-h-0">
        <div className="flex items-center justify-between border-b border-slate-800 p-5"><div><h2 className="flex items-center gap-2 text-lg font-black"><ShoppingCart className="h-5 w-5" /> ตะกร้า</h2><p className="text-xs text-slate-400">{cart.length} รายการ</p></div>{lastQueue ? <span className="rounded-xl bg-emerald-500 px-3 py-2 font-black text-slate-950">คิวล่าสุด {lastQueue}</span> : null}</div>
        {pickupQr && lastQueue ? <div className="border-b border-slate-800 bg-white p-4 text-center text-slate-950"><img className="mx-auto h-36 w-36" src={pickupQr} alt={`QR ติดตามคิว ${lastQueue}`} /><p className="mt-2 font-black">สแกนติดตามคิว {lastQueue}</p><p className="text-xs text-slate-500">ลูกค้าเปิดดูสถานะได้โดยไม่ต้องเข้าสู่ระบบ</p></div> : null}
        {lastReceipt ? <div className="grid grid-cols-2 gap-2 border-b border-slate-800 p-4"><button onClick={() => void printReceipt(lastReceipt, "customer")} className="rounded-xl bg-white px-3 py-3 text-sm font-black text-slate-950"><Printer className="mr-2 inline h-4 w-4" />ใบลูกค้า</button><button onClick={() => void printReceipt(lastReceipt, "merchant")} className="rounded-xl border border-slate-600 px-3 py-3 text-sm font-black"><Printer className="mr-2 inline h-4 w-4" />สำเนาร้าน</button></div> : null}
        <div className="flex-1 space-y-3 overflow-y-auto p-4">{cart.map((line) => <div key={line.row.item.id} className="rounded-2xl bg-slate-900 p-4"><div className="flex justify-between gap-3"><div><p className="font-bold">{line.row.item.name}</p><p className="text-sm text-emerald-400">{money(Number(line.row.effective_price) * line.quantity)}</p></div><div className="flex items-center gap-2"><button className="rounded-lg bg-slate-800 p-2" onClick={() => adjust(line.row, -1)}><Minus className="h-4 w-4" /></button><span className="w-5 text-center font-bold">{line.quantity}</span><button className="rounded-lg bg-emerald-500 p-2 text-slate-950" onClick={() => adjust(line.row, 1)}><Plus className="h-4 w-4" /></button></div></div></div>)}{cart.length === 0 ? <div className="grid h-full place-items-center text-center text-slate-500"><div><ShoppingCart className="mx-auto h-12 w-12" /><p className="mt-3">เลือกสินค้าเพื่อเริ่มขาย</p></div></div> : null}</div>
        <div className="space-y-2 border-t border-slate-800 p-5"><div className="flex justify-between text-sm text-slate-400"><span>สินค้า</span><span>{money(subtotal)}</span></div><div className="flex justify-between text-sm text-slate-400"><span>ภาษี</span><span>{money(tax)}</span></div><div className="flex justify-between text-2xl font-black"><span>สุทธิ</span><span>{money(total)}</span></div><button disabled={!openShift || cart.length === 0 || saleMutation.isPending} onClick={() => saleMutation.mutate()} className="mt-3 flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-500 py-4 text-lg font-black text-slate-950 disabled:opacity-40"><ReceiptText className="h-5 w-5" />{saleMutation.isPending ? "กำลังรับชำระ" : "รับเงินสดและส่งครัว"}</button></div>
      </aside>
      <div className="fixed -left-[10000px] top-0"><div ref={receiptRef}><TakeawayReceiptSlip receipt={lastReceipt} copyType={receiptCopyType} /></div></div>
    </div>
  );
}
