import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CloudOff, Minus, Plus, Printer, QrCode, ReceiptText, RefreshCw, Search, ShoppingCart } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useReactToPrint } from "react-to-print";
import TakeawayReceiptSlip from "@/components/takeaway/TakeawayReceiptSlip";
import { useToast } from "@/components/ui/use-toast";
import { useTakeawayReleaseGate } from "@/hooks/useTakeawayReleaseGate";
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
import { printTakeawaySlipFrame, TAKEAWAY_SLIP_PRINT_CSS } from "@/lib/takeawaySlipPrint";

type CartLine = { row: TakeawayCatalogRow; quantity: number };
type ReceiptPrintJob = { receipt: TakeawayReceipt; copyType: "customer" | "merchant"; clientSaleId: string | null; key: string; started: boolean; recording?: boolean };

function businessDate(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok" }).format(new Date());
}

function money(value: number): string {
  return new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(value);
}

function publicTakeawayUrl(path: string): string {
  const configuredOrigin = import.meta.env.VITE_PUBLIC_APP_ORIGIN?.trim().replace(/\/$/, "");
  const origin = configuredOrigin || window.location.origin;
  return new URL(path, `${origin}/`).toString();
}

export default function TakeawayCounterPage({ mode = "combined", storeOnly = false }: { mode?: "combined" | "sales" | "orders"; storeOnly?: boolean } = {}): JSX.Element {
  const showSales = mode !== "orders";
  const showOrders = mode !== "sales";
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const releaseGate = useTakeawayReleaseGate();
  const writesEnabled = releaseGate.writesEnabled;
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [productSearch, setProductSearch] = useState("");
  const [cart, setCart] = useState<CartLine[]>([]);
  const [paymentMethod, setPaymentMethod] = useState<"cash" | "other">("cash");
  const [paymentReference, setPaymentReference] = useState("");
  const [paymentConfirmed, setPaymentConfirmed] = useState(false);
  const [openingCash, setOpeningCash] = useState("0");
  const [lastQueue, setLastQueue] = useState<number | null>(null);
  const [pickupQr, setPickupQr] = useState("");
  const [orderingQr, setOrderingQr] = useState("");
  const [lastReceipt, setLastReceipt] = useState<TakeawayReceipt | null>(null);
  const [lastClientSaleId, setLastClientSaleId] = useState<string | null>(null);
  const [receiptCopyType, setReceiptCopyType] = useState<"customer" | "merchant">("customer");
  const receiptRef = useRef<HTMLDivElement | null>(null);
  const orderingQrRef = useRef<HTMLDivElement | null>(null);
  const printBusyRef = useRef(false);
  const [printBusy, setPrintBusy] = useState(false);
  const [browserJob, setBrowserJob] = useState<ReceiptPrintJob | null>(null);
  const [confirmPrinted, setConfirmPrinted] = useState(false);
  const activePrintJob = useRef<ReceiptPrintJob | null>(null);
  const releasePrintJob = (): void => {
    printBusyRef.current = false; setPrintBusy(false); setBrowserJob(null);
    setConfirmPrinted(false); activePrintJob.current = null;
  };
  const recordPrint = async (job: ReceiptPrintJob): Promise<void> => {
    if (activePrintJob.current !== job || job.recording) return;
    job.recording = true;
    try {
      setLastReceipt(await markTakeawayReceiptPrinted(job.clientSaleId, job.receipt.order_id, job.copyType, job.key));
    } catch {
      toast({ title: "พิมพ์แล้ว แต่บันทึกประวัติไม่สำเร็จ", description: "ตรวจประวัติก่อนสั่งพิมพ์ซ้ำ", variant: "destructive" });
    } finally { releasePrintJob(); }
  };
  const workspaceQuery = useQuery({
    queryKey: ["takeaway", "offline-workspace"],
    queryFn: loadTakeawayWorkspace,
    networkMode: "always",
  });
  const context = workspaceQuery.data?.context;
  // Store builds never expose kitchen stages, even before cached context refreshes.
  // The server still authorizes counter mode independently for every action.
  const twoStep = storeOnly || context?.counter_two_step === true;
  const fulfillmentLock = useRef(false);
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
    enabled: !storeOnly && showOrders && Boolean(context?.branch_id),
    refetchInterval: 5_000,
  });
  const recentOrdersQuery = useQuery({
    queryKey: ["takeaway", "orders", "recent", context?.branch_id],
    queryFn: async () => (await takeawayApi.orders({ branch_id: context!.branch_id!, limit: 50 })).data.data,
    enabled: Boolean(context?.branch_id),
    refetchInterval: 5_000,
  });
  const openShift = shifts.find((row) => row.status === "open");
  const activeOrdersQuery = useQuery({
    queryKey: ["takeaway", "orders", "active", context?.branch_id],
    queryFn: async () => (await takeawayApi.orders({ branch_id: context!.branch_id!, active_only: true, limit: 500 })).data.data,
    enabled: showOrders && Boolean(context?.branch_id), refetchInterval: 5_000,
  });
  const browserPrintReceipt = useReactToPrint({
    contentRef: receiptRef,
    pageStyle: TAKEAWAY_SLIP_PRINT_CSS,
    print: printTakeawaySlipFrame,
    onAfterPrint: () => { if (activePrintJob.current) setConfirmPrinted(true); },
    onPrintError: (_where, error) => { releasePrintJob(); toast({ title: "พิมพ์ไม่สำเร็จ", description: error.message, variant: "destructive" }); },
  });
  const printOrderingQr = useReactToPrint({
    contentRef: orderingQrRef, pageStyle: TAKEAWAY_SLIP_PRINT_CSS, print: printTakeawaySlipFrame,
    onAfterPrint: releasePrintJob,
    onPrintError: (_where, error) => { releasePrintJob(); toast({ title: "พิมพ์ QR ไม่สำเร็จ", description: error.message, variant: "destructive" }); },
  });
  const startOrderingQrPrint = (): void => {
    if (printBusyRef.current) return;
    printBusyRef.current = true; setPrintBusy(true);
    printOrderingQr();
  };
  useEffect(() => {
    if (!browserJob || browserJob.started) return;
    browserJob.started = true;
    browserPrintReceipt();
  }, [browserJob, browserPrintReceipt]);
  const printReceipt = async (
    receipt: TakeawayReceipt,
    copyType: "customer" | "merchant",
    clientSaleId: string | null = lastClientSaleId,
  ): Promise<void> => {
    if (printBusyRef.current) return;
    if (!writesEnabled) {
      toast({ title: "การพิมพ์หลักฐานยังถูกพักไว้", description: "รอ Physical UAT และ Server transaction gate", variant: "destructive" });
      return;
    }
    setLastReceipt(receipt);
    setReceiptCopyType(copyType);
    printBusyRef.current = true; setPrintBusy(true);
    const job: ReceiptPrintJob = { receipt, copyType, clientSaleId, key: `takeaway-print:${crypto.randomUUID()}`, started: false };
    activePrintJob.current = job;
    try {
      if (await printTakeawayReceipt(receipt, copyType)) {
        // Bluetooth flush/USB ACK cannot certify paper or print-head success.
        setConfirmPrinted(true);
        toast({ title: "ส่งข้อมูลแล้ว กรุณาตรวจใบเสร็จก่อนยืนยัน" });
        return;
      }
    } catch (error) {
      toast({
        title: "เครื่องพิมพ์ ESC/POS ไม่พร้อม",
        description: `${error instanceof Error ? error.message : "ไม่ทราบสถานะเครื่องพิมพ์"} — ตรวจว่ากระดาษออกแล้วหรือไม่ก่อนลองใหม่ ระบบไม่พิมพ์ซ้ำอัตโนมัติ`,
        variant: "destructive",
      });
      releasePrintJob();
      return;
    }
    setBrowserJob(job);
  };
  useEffect(() => {
    if (!writesEnabled) return undefined;
    const synchronize = (): void => {
      void syncTakeawayPendingSales()
        .then(() => Promise.all([outboxQuery.refetch(), queryClient.invalidateQueries({ queryKey: ["takeaway", "orders"] })]))
        .catch(() => undefined);
    };
    window.addEventListener("online", synchronize);
    return () => window.removeEventListener("online", synchronize);
  }, [outboxQuery, writesEnabled]);
  const openShiftMutation = useMutation({
    mutationFn: () => {
      if (!writesEnabled) throw new Error("รายการขายยังถูกล็อกในช่วง Dark launch");
      return takeawayApi.openShift({ business_date: businessDate(), opening_cash: openingCash || "0" });
    },
    onSuccess: async () => { await refreshTakeawayWorkspace(); await queryClient.invalidateQueries({ queryKey: ["takeaway", "offline-workspace"] }); toast({ title: "เปิดกะแล้ว", description: "พร้อมรับรายการขาย" }); },
    onError: () => toast({ title: "เปิดกะไม่สำเร็จ", description: "ตรวจสาขาและสิทธิ์อีกครั้ง", variant: "destructive" }),
  });
  const saleMutation = useMutation({
    networkMode: "always",
    mutationFn: async () => {
      if (!writesEnabled) throw new Error("รายการขายยังถูกล็อกในช่วง Dark launch");
      if (!context?.brand_id || !context.branch_id || !openShift) throw new Error("กรุณาเปิดกะก่อนขาย");
      const total = cart.reduce((sum, line) => sum + Number(line.row.effective_price) * line.quantity * (1 + Number(line.row.item.tax_rate ?? 0) / 100), 0);
      if (paymentMethod !== "cash" && (!navigator.onLine || !paymentConfirmed || !paymentReference.trim())) throw new Error("กรุณาออนไลน์ ตรวจสอบการรับเงินจริง และระบุเลขอ้างอิงก่อนบันทึก");
      return queueTakeawaySale({
        brand_id: context.brand_id,
        branch_id: context.branch_id,
        shift_id: openShift.id,
        channel: "counter",
        items: cart.map((line) => ({ catalog_item_id: line.row.item.id, quantity: String(line.quantity) })),
        discount_amount: "0",
        payment: { method: paymentMethod, amount: total.toFixed(2), ...(paymentMethod !== "cash" ? { reference: paymentReference.trim() } : {}) },
      }, catalog);
    },
    onSuccess: async (result) => {
      const order = result.order;
      const pickupToken = result.pickupToken;
      const queueNumber = order.queue_number == null ? null : Number(order.queue_number);
      setLastQueue(queueNumber);
      setLastReceipt(result.receipt);
      setLastClientSaleId(result.clientSaleId);
      if (pickupToken && !storeOnly) {
        const url = publicTakeawayUrl(`/takeaway/pickup-status/${encodeURIComponent(pickupToken)}`);
        setPickupQr(await QRCode.toDataURL(url, { width: 240, margin: 2, color: { dark: "#0f172a" } }));
      } else {
        setPickupQr("");
      }
      setCart([]);
      setPaymentReference(""); setPaymentConfirmed(false);
      await outboxQuery.refetch();
      if (result.status === "synced") {
        await Promise.all([
          refreshTakeawayWorkspace(),
          queryClient.invalidateQueries({ queryKey: ["takeaway", "orders"] }),
          queryClient.invalidateQueries({ queryKey: ["takeaway", "stock"] }),
        ]);
        await queryClient.invalidateQueries({ queryKey: ["takeaway", "offline-workspace"] });
      } else {
        void queryClient.invalidateQueries({ queryKey: ["takeaway", "orders"], refetchType: "none" });
        void queryClient.invalidateQueries({ queryKey: ["takeaway", "stock"], refetchType: "none" });
      }
      toast({
        title: result.status === "synced" ? `รับเงินแล้ว · คิว ${String(order.queue_number)}` : result.status === "needs_review" ? "บันทึกในเครื่องแล้ว · ต้องตรวจสอบ" : "เก็บรายการไว้ในเครื่องแล้ว",
        description: result.status === "synced" ? String(order.order_number) : result.error || "ระบบจะส่งรายการอัตโนมัติเมื่อเชื่อมต่อได้",
      });
    },
    onError: (error) => toast({ title: "ขายไม่สำเร็จ", description: error instanceof Error ? error.message : "กรุณาตรวจสต๊อกและยอดชำระ", variant: "destructive" }),
  });
  const orderingLinkMutation = useMutation({
    mutationFn: () => {
      if (storeOnly || !writesEnabled) throw new Error("การสร้าง QR สั่งซื้อยังถูกล็อกในช่วง Dark launch");
      return takeawayApi.createOrderingLink(12);
    },
    onSuccess: async (response) => {
      const url = publicTakeawayUrl(`/takeaway/order/${encodeURIComponent(response.data.data.token)}`);
      setOrderingQr(await QRCode.toDataURL(url, { width: 260, margin: 2, color: { dark: "#0f172a" } }));
    },
    onError: () => toast({ title: "สร้าง QR ไม่สำเร็จ", variant: "destructive" }),
  });
  const captureMutation = useMutation({
    mutationFn: (order: Record<string, unknown> & { id: string }) => {
      if (!writesEnabled) throw new Error("การรับชำระยังถูกล็อกในช่วง Dark launch");
      return takeawayApi.captureOrderPayment(order.id, {
        payment: {
          method: "cash",
          amount: String(order.total_amount),
          idempotency_key: `web-qr-payment-${crypto.randomUUID()}`,
        },
      });
    },
    onSuccess: async () => {
      await Promise.all([
        refreshTakeawayWorkspace(),
        queryClient.invalidateQueries({ queryKey: ["takeaway", "orders"] }),
        queryClient.invalidateQueries({ queryKey: ["takeaway", "stock"] }),
      ]);
      await queryClient.invalidateQueries({ queryKey: ["takeaway", "offline-workspace"] });
      toast({ title: "รับชำระแล้ว", description: "รายการพร้อมให้พนักงานเริ่มเตรียมสินค้า" });
    },
    onError: () => toast({ title: "รับชำระไม่สำเร็จ", description: "ตรวจยอดเงินและสต๊อก", variant: "destructive" }),
  });
  const fulfillmentMutation = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "preparing" | "ready" | "picked_up" | "accept" | "handoff" }) => {
      if (!writesEnabled) throw new Error("รายการขายยังถูกล็อกในช่วง Dark launch");
      if (action === "accept" || action === "handoff") return takeawayApi.counterOrderAction(id, action);
      return action === "picked_up"
        ? takeawayApi.markPickedUp(id)
        : takeawayApi.updateFulfillmentOrder(id, action);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["takeaway", "orders"] });
      toast({ title: "อัปเดตสถานะสินค้าแล้ว" });
    },
    onError: () => toast({ title: "เปลี่ยนสถานะไม่สำเร็จ", description: "ตรวจลำดับสถานะและสิทธิ์อีกครั้ง", variant: "destructive" }),
    onSettled: () => { fulfillmentLock.current = false; },
  });
  const runFulfillment = (id: string, action: "preparing" | "ready" | "picked_up" | "accept" | "handoff"): void => {
    if (fulfillmentLock.current) return;
    fulfillmentLock.current = true;
    fulfillmentMutation.mutate({ id, action });
  };
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
  const visibleItems = catalog.filter((row) => {
    if (categoryId && row.item.category_id !== categoryId) return false;
    const needle = productSearch.trim().toLowerCase();
    if (!needle) return true;
    return `${row.item.name} ${row.item.sku} ${row.item.barcode ?? ""} ${row.item.description ?? ""}`
      .toLowerCase()
      .includes(needle);
  });
  const subtotal = useMemo(() => cart.reduce((sum, line) => sum + Number(line.row.effective_price) * line.quantity, 0), [cart]);
  const tax = useMemo(() => cart.reduce((sum, line) => sum + Number(line.row.effective_price) * line.quantity * Number(line.row.item.tax_rate ?? 0) / 100, 0), [cart]);
  const total = subtotal + tax;
  const activeFulfillmentOrders = (activeOrdersQuery.data ?? []).filter((order) =>
    ["queued", "preparing", "ready"].includes(String(order.fulfillment_status)),
  );
  const adjust = (row: TakeawayCatalogRow, delta: number): void => setCart((current) => {
    if (!row.is_available && delta > 0) return current;
    const found = current.find((line) => line.row.item.id === row.item.id);
    if (!found && delta > 0) return [...current, { row, quantity: 1 }];
    return current.map((line) => line.row.item.id === row.item.id ? { ...line, quantity: line.quantity + delta } : line).filter((line) => line.quantity > 0);
  });

  if (workspaceQuery.isError) return <div role="alert" className="rounded-xl bg-amber-50 p-4"><p>{workspaceQuery.error instanceof Error ? workspaceQuery.error.message : "โหลดหน้าร้านไม่สำเร็จ"}</p><button className="mt-3 rounded border p-3" onClick={() => void workspaceQuery.refetch()}>ลองใหม่</button></div>;
  if (!workspaceQuery.isLoading && (!context?.brand_id || !context.branch_id)) {
    return <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-amber-900">กรุณาเลือกสาขาของแบรนด์ Takeaway ก่อนเปิดหน้าขาย</div>;
  }
  return (
    <div className={`grid items-start gap-4 ${mode === "combined" ? "lg:grid-cols-[minmax(0,1fr)_minmax(360px,420px)]" : mode === "sales" ? "pb-24" : ""}`} data-testid={`takeaway-${mode}-workspace`}>
      <section className="min-w-0 space-y-4">
        {confirmPrinted ? <div role="status" className="rounded-xl border border-amber-300 bg-amber-50 p-4">
          <p className="font-bold">กระดาษออกครบแล้วหรือไม่?</p><p className="text-sm">ถ้ากด Cancel หรือกระดาษไม่ออก ให้เลือก “ไม่ได้พิมพ์” จะไม่บันทึกประวัติ</p>
          <button className="m-2 rounded-lg bg-emerald-700 p-3 text-white" onClick={() => {
            const job = activePrintJob.current;
            if (!job) return;
            setConfirmPrinted(false); void recordPrint(job);
          }}>ยืนยันพิมพ์แล้ว</button>
          <button className="m-2 rounded-lg border p-3" onClick={releasePrintJob}>ไม่ได้พิมพ์</button>
        </div> : null}
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-white p-4 shadow-sm">
          <div><h1 className="text-xl font-black">{mode === "sales" ? "ขายสินค้า" : mode === "orders" ? "รับออเดอร์" : "ขายและเตรียมสินค้า"}</h1><p className="text-sm text-slate-500">{showSales ? "เลือกสินค้า ระบุจำนวน แล้วรับชำระเงิน" : twoStep || storeOnly ? "รับออเดอร์ · ส่งมอบ" : "รับชำระ · เตรียม · ส่งมอบ"}</p></div>
          <button disabled={!writesEnabled} onClick={() => void syncTakeawayPendingSales().then(() => outboxQuery.refetch())} className="flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2 text-sm font-bold disabled:opacity-40"><RefreshCw className="h-4 w-4" /> ส่งรายการค้าง</button>
          {!storeOnly && showOrders ? <button disabled={!writesEnabled || !openShift || orderingLinkMutation.isPending} onClick={() => orderingLinkMutation.mutate()} className="flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2 text-sm font-bold disabled:opacity-40"><QrCode className="h-4 w-4" /> QR ลูกค้าสั่งเอง</button> : null}
          {openShift ? <span className="rounded-full bg-emerald-100 px-4 py-2 text-sm font-bold text-emerald-700">กะ #{String(openShift.round_no)} เปิดอยู่</span> : <div className="flex gap-2"><input disabled={!writesEnabled} className="w-28 rounded-xl border px-3 py-2 disabled:bg-slate-100" inputMode="decimal" value={openingCash} onChange={(event) => setOpeningCash(event.target.value)} /><button disabled={!writesEnabled} className="rounded-xl bg-slate-950 px-4 py-2 font-bold text-white disabled:opacity-40" onClick={() => openShiftMutation.mutate()}>เปิดกะ</button></div>}
        </div>
        {(outboxQuery.data?.pending || outboxQuery.data?.syncing || outboxQuery.data?.needsReview) ? <div className={`flex flex-wrap items-center justify-between gap-3 rounded-2xl border p-4 ${outboxQuery.data.needsReview ? "border-amber-300 bg-amber-50" : "border-sky-200 bg-sky-50"}`}><div className="flex items-center gap-3">{outboxQuery.data.needsReview ? <AlertTriangle className="h-5 w-5 text-amber-700" /> : <CloudOff className="h-5 w-5 text-sky-700" />}<div><p className="font-black">รายการในเครื่อง: รอส่ง {outboxQuery.data.pending} · กำลังส่ง {outboxQuery.data.syncing} · ต้องตรวจ {outboxQuery.data.needsReview}</p>{outboxQuery.data.latestError ? <p className="text-xs text-amber-800">{outboxQuery.data.latestError}</p> : null}</div></div>{outboxQuery.data.needsReview ? <button disabled={!writesEnabled} onClick={() => void retryTakeawayNeedsReview().then(() => outboxQuery.refetch())} className="rounded-xl bg-amber-500 px-4 py-2 text-sm font-black disabled:opacity-40">ลองส่งอีกครั้ง</button> : null}</div> : null}
        {!storeOnly && orderingQr ? <div className="flex flex-wrap items-center gap-5 rounded-2xl border border-emerald-200 bg-emerald-50 p-4"><img src={orderingQr} alt="QR ลูกค้าสั่งเอง" className="h-36 w-36 rounded-xl bg-white p-2" /><div><h2 className="font-black text-emerald-950">QR สั่งสินค้าของสาขา</h2><p className="mt-1 text-sm text-emerald-800">ใช้ได้ 12 ชั่วโมง ลูกค้าสั่งแล้วรายการจะรอรับชำระก่อนเริ่มเตรียมสินค้า</p><button disabled={printBusy} onClick={startOrderingQrPrint} className="mt-3 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-bold text-white">พิมพ์ QR</button></div></div> : null}
        {!storeOnly && showOrders && (pendingOrdersQuery.data ?? []).length ? <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4"><h2 className="font-black text-amber-950">ออเดอร์ QR รอชำระ</h2><div className="mt-3 grid gap-2">{(pendingOrdersQuery.data ?? []).map((order) => <div key={order.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white p-3"><div><p className="font-black">คิว {String(order.queue_number)} · {String(order.order_number)}</p><p className="text-sm text-slate-500">ยอด {money(Number(order.total_amount))}</p></div><button disabled={!writesEnabled || captureMutation.isPending} onClick={() => captureMutation.mutate(order)} className="rounded-xl bg-slate-950 px-4 py-2 text-sm font-bold text-white disabled:opacity-40">รับเงินสดและเริ่มงาน</button></div>)}</div></div> : null}
        {showOrders && activeFulfillmentOrders.length ? <div className="rounded-2xl border border-sky-200 bg-sky-50 p-4"><h2 className="font-black text-sky-950">{twoStep ? "รายการรับออเดอร์และส่งมอบ" : "รายการเตรียมและส่งมอบ"}</h2><div className="mt-3 grid gap-2 md:grid-cols-2">{activeFulfillmentOrders.map((order) => {
          const status = String(order.fulfillment_status);
          const action = twoStep ? (status === "queued" ? "accept" : "handoff") : status === "queued" ? "preparing" : status === "preparing" ? "ready" : "picked_up";
          const label = twoStep ? (status === "queued" ? "รับออเดอร์" : "ส่งมอบ") : status === "queued" ? "เริ่มเตรียม" : status === "preparing" ? "พร้อมรับ" : "ส่งมอบแล้ว";
          return <div key={order.id} data-testid={`active-order-${order.id}`} className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white p-3"><div><p className="font-black">คิว {String(order.queue_number ?? "-")} · {String(order.order_number)}</p><p className="text-sm text-slate-500">{twoStep ? (status === "queued" ? "รอรับออเดอร์" : "รับออเดอร์แล้ว") : status === "queued" ? "รอเตรียม" : status === "preparing" ? "กำลังเตรียม" : "พร้อมส่งมอบ"}</p></div><button disabled={!writesEnabled || !navigator.onLine || fulfillmentMutation.isPending} onClick={() => runFulfillment(order.id, action)} className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-black text-white disabled:opacity-40">{label}</button></div>;
        })}</div></div> : null}
        {showOrders && activeOrdersQuery.isError ? <p role="alert">โหลดออเดอร์ไม่สำเร็จ กรุณาเชื่อมต่อแล้วลองใหม่</p> : null}
        {showOrders && !activeOrdersQuery.isLoading && !activeOrdersQuery.isError && !activeFulfillmentOrders.length && (storeOnly || !pendingOrdersQuery.data?.length) ? <p className="rounded-xl bg-white p-4 text-slate-500">{twoStep || storeOnly ? "ไม่มีออเดอร์รอรับหรือส่งมอบ" : "ยังไม่มีคิวรอรับชำระ เตรียม หรือส่งมอบ"}</p> : null}
        {showSales ? <>
        <label className="relative block rounded-2xl bg-white shadow-sm">
          <Search className="pointer-events-none absolute left-4 top-3.5 h-5 w-5 text-slate-400" />
          <input
            value={productSearch}
            onChange={(event) => setProductSearch(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== "Enter") return;
              const exact = catalog.find((row) => row.is_available && [row.item.sku, row.item.barcode].filter(Boolean).some((value) => String(value).toLowerCase() === productSearch.trim().toLowerCase()));
              if (exact) {
                event.preventDefault();
                adjust(exact, 1);
                setProductSearch("");
              }
            }}
            placeholder="ค้นหาชื่อสินค้า หรือสแกน SKU / บาร์โค้ด แล้วกด Enter"
            className="h-12 w-full rounded-2xl border border-slate-200 pl-12 pr-4 text-sm outline-none focus:border-emerald-500"
          />
        </label>
        <div className="flex gap-2 overflow-x-auto rounded-2xl bg-white p-3 shadow-sm">
          <button onClick={() => setCategoryId(null)} className={`min-w-fit rounded-xl px-4 py-2 text-sm font-bold ${categoryId === null ? "bg-emerald-500 text-slate-950" : "bg-slate-100"}`}>ทั้งหมด</button>
          {categories.map((category) => <button key={category.id} onClick={() => setCategoryId(category.id)} className={`min-w-fit rounded-xl px-4 py-2 text-sm font-bold ${categoryId === category.id ? "bg-emerald-500 text-slate-950" : "bg-slate-100"}`}>{String(category.name)}</button>)}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {visibleItems.map((row) => {
            const quantity = cart.find((line) => line.row.item.id === row.item.id)?.quantity ?? 0;
            return <article key={row.item.id} className="flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-xl border bg-white p-4" data-testid="sales-product">
              <div className="min-w-0 flex-1"><h2 className="break-words font-bold">{row.item.name}</h2><p className="text-xs text-slate-500">{row.item.sku}</p><p className="mt-1 font-bold text-emerald-700">{money(Number(row.effective_price))}</p>{!row.is_available ? <p className="text-sm text-rose-700">หมด/ปิดขาย</p> : null}</div>
              <div className="flex items-center gap-2">
                <button aria-label={`ลด ${row.item.name}`} disabled={!quantity || saleMutation.isPending} onClick={() => adjust(row, -1)} className="grid h-12 w-12 place-items-center rounded-lg border disabled:opacity-40"><Minus /></button>
                <output aria-label={`จำนวน ${row.item.name}`} className="w-8 text-center font-black">{quantity}</output>
                <button aria-label={`เพิ่ม ${row.item.name}`} disabled={!row.is_available || saleMutation.isPending} onClick={() => adjust(row, 1)} className="grid h-12 w-12 place-items-center rounded-lg bg-emerald-600 text-white disabled:opacity-40"><Plus /></button>
              </div>
            </article>;
          })}
          {!workspaceQuery.isLoading && visibleItems.length === 0 ? <div className="col-span-full rounded-2xl border border-dashed bg-white p-10 text-center text-slate-500">ไม่พบสินค้าในหมวดหรือคำค้นหานี้</div> : null}
        </div>
        </> : null}
        {(recentOrdersQuery.data ?? []).length ? <div className="rounded-2xl border bg-white p-4 shadow-sm"><h2 className="font-black">บิลล่าสุด</h2><div className="mt-3 flex gap-2 overflow-x-auto">{(recentOrdersQuery.data ?? []).slice(0, 8).map((order) => <button key={order.id} disabled={!writesEnabled || reprintMutation.isPending} onClick={() => reprintMutation.mutate(order.id)} className="min-w-fit rounded-xl border px-3 py-2 text-left text-sm disabled:opacity-40"><span className="font-black">คิว {String(order.queue_number ?? "-")}</span><span className="ml-2 text-slate-500">{money(Number(order.total_amount))}</span><Printer className="ml-2 inline h-4 w-4" /></button>)}</div></div> : null}
      </section>
      {showSales ? <aside id="takeaway-sale-checkout" aria-label="ตะกร้าและชำระเงิน" className="flex scroll-mt-40 flex-col overflow-hidden rounded-2xl bg-slate-950 text-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-800 p-5"><div><h2 className="flex items-center gap-2 text-lg font-black"><ShoppingCart className="h-5 w-5" /> ตะกร้า</h2><p className="text-xs text-slate-400">{cart.length} รายการ</p></div>{lastQueue ? <span className="rounded-xl bg-emerald-500 px-3 py-2 font-black text-slate-950">คิวล่าสุด {lastQueue}</span> : null}</div>
        {!storeOnly && pickupQr && lastQueue ? <div className="border-b border-slate-800 bg-white p-4 text-center text-slate-950"><img className="mx-auto h-36 w-36" src={pickupQr} alt={`QR ติดตามคิว ${lastQueue}`} /><p className="mt-2 font-black">สแกนติดตามคิว {lastQueue}</p><p className="text-xs text-slate-500">ลูกค้าเปิดดูสถานะได้โดยไม่ต้องเข้าสู่ระบบ</p></div> : null}
        {lastReceipt ? <div className="grid grid-cols-2 gap-2 border-b border-slate-800 p-4"><button disabled={!writesEnabled} onClick={() => void printReceipt(lastReceipt, "customer")} className="rounded-xl bg-white px-3 py-3 text-sm font-black text-slate-950 disabled:opacity-40"><Printer className="mr-2 inline h-4 w-4" />ใบลูกค้า</button><button disabled={!writesEnabled} onClick={() => void printReceipt(lastReceipt, "merchant")} className="rounded-xl border border-slate-600 px-3 py-3 text-sm font-black disabled:opacity-40"><Printer className="mr-2 inline h-4 w-4" />สำเนาร้าน</button></div> : null}
        <div className="flex-1 space-y-3 overflow-y-auto p-4">{cart.map((line) => <div key={line.row.item.id} className="rounded-2xl bg-slate-900 p-4"><div className="flex justify-between gap-3"><div><p className="font-bold">{line.row.item.name}</p><p className="text-sm text-emerald-400">{money(Number(line.row.effective_price) * line.quantity)}</p></div><div className="flex items-center gap-2"><button className="rounded-lg bg-slate-800 p-2" onClick={() => adjust(line.row, -1)}><Minus className="h-4 w-4" /></button><span className="w-5 text-center font-bold">{line.quantity}</span><button className="rounded-lg bg-emerald-500 p-2 text-slate-950" onClick={() => adjust(line.row, 1)}><Plus className="h-4 w-4" /></button></div></div></div>)}{cart.length === 0 ? <div className="grid h-full place-items-center text-center text-slate-500"><div><ShoppingCart className="mx-auto h-12 w-12" /><p className="mt-3">เลือกสินค้าเพื่อเริ่มขาย</p></div></div> : null}</div>
        <div className="space-y-2 border-t border-slate-800 p-5"><div className="flex justify-between text-sm text-slate-400"><span>สินค้า</span><span>{money(subtotal)}</span></div><div className="flex justify-between text-sm text-slate-400"><span>ภาษี</span><span>{money(tax)}</span></div><div className="flex justify-between text-2xl font-black"><span>สุทธิ</span><span>{money(total)}</span></div><fieldset className="space-y-3 rounded-xl border border-slate-700 p-3"><legend className="px-1 text-sm">วิธีรับชำระ</legend>
          <label className="flex items-center gap-3"><input type="radio" name="sale-payment" checked={paymentMethod === "cash"} onChange={() => setPaymentMethod("cash")} />เงินสด</label>
          <label className="flex items-center gap-3"><input type="radio" name="sale-payment" checked={paymentMethod === "other"} onChange={() => setPaymentMethod("other")} />โอน/ชำระภายนอก (ตรวจรับเอง)</label>
          {paymentMethod !== "cash" ? <><p className="text-xs text-amber-200">ไม่ใช่การเรียกเก็บผ่าน Provider หรือยืนยัน PromptPay อัตโนมัติ ต้องตรวจรับเงินจริงก่อน</p><label className="block text-sm">เลขอ้างอิงการรับเงิน<input aria-label="เลขอ้างอิงการรับเงิน" className="mt-1 w-full rounded p-3 text-slate-950" value={paymentReference} onChange={(event) => setPaymentReference(event.target.value)} /></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={paymentConfirmed} onChange={(event) => setPaymentConfirmed(event.target.checked)} />ตรวจสอบว่าได้รับเงินจริงแล้ว</label></> : null}
        </fieldset><button disabled={!writesEnabled || !openShift || cart.length === 0 || saleMutation.isPending || (paymentMethod !== "cash" && (!paymentConfirmed || !paymentReference.trim()))} onClick={() => saleMutation.mutate()} className="mt-3 flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-500 py-4 text-lg font-black text-slate-950 disabled:opacity-40"><ReceiptText className="h-5 w-5" />{saleMutation.isPending ? "กำลังรับชำระ" : writesEnabled ? "บันทึกการรับชำระ" : "รอเปิด Transaction Gate"}</button></div>
      </aside> : null}
      {mode === "sales" ? <div className="fixed inset-x-0 bottom-0 z-30 border-t bg-white p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] shadow-lg"><button disabled={!cart.length} onClick={() => document.getElementById("takeaway-sale-checkout")?.scrollIntoView({ behavior: "smooth", block: "start" })} className="mx-auto block min-h-12 w-full max-w-5xl rounded-xl bg-emerald-600 px-4 py-3 font-bold text-white disabled:bg-slate-400">สรุปออเดอร์ · {cart.reduce((sum, line) => sum + line.quantity, 0)} ชิ้น · {money(total)}</button></div> : null}
      <div className="fixed -left-[10000px] top-0">
        <div ref={receiptRef} className="takeaway-thermal-sheet"><TakeawayReceiptSlip receipt={browserJob?.receipt ?? lastReceipt} copyType={browserJob?.copyType ?? receiptCopyType} /></div>
        {!storeOnly && orderingQr ? <div ref={orderingQrRef} className="takeaway-thermal-sheet text-center">
          <div><h2 className="font-bold">QR สั่งสินค้าของสาขา</h2><img data-ordering-qr src={orderingQr} alt="QR ลูกค้าสั่งเอง" />
          <p>สแกนเลือกสินค้า แล้วชำระเงินที่เคาน์เตอร์</p><p className="text-xs">QR มีอายุ 12 ชั่วโมงนับจากสร้าง</p></div>
        </div> : null}
      </div>
    </div>
  );
}
