import { useMutation, useQuery } from "@tanstack/react-query";
import { App } from "@capacitor/app";
import { liveQuery } from "dexie";
import { AlertTriangle, ArrowRightLeft, ChefHat, ClipboardCheck, CloudUpload, CreditCard, LogOut, Loader2, Menu, Minus, PackageCheck, PackageOpen, Plus, Printer, ReceiptText, UserRoundCheck, Warehouse, Wifi, WifiOff } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useReactToPrint } from "react-to-print";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";
import { useToast } from "@/components/ui/use-toast";
import { useLogout } from "@/hooks/useAuth";
import {
  getRestaurantOutboxSummary,
  getQueuedRestaurantOrder,
  loadRestaurantMenu,
  markRestaurantLocalSlip,
  queueRestaurantOrder,
  retryRestaurantNeedsReview,
  syncRestaurantPendingOrders,
  type RestaurantOutboxSummary,
} from "@/lib/restaurantOffline";
import { useOnlineStatus } from "@/lib/syncService";
import { wapApi, type WapMenu, type WapMenuProduct, type WapOrder } from "@/lib/wapApi";
import { useAuthStore } from "@/stores/auth.store";

type CartItem = {
  product: WapMenuProduct;
  qty: number;
  note: string;
};

const paymentLabels: Record<string, string> = {
  cash: "เงินสด",
  promptpay: "PromptPay",
};

function money(value: number | string): string {
  return Number(value || 0).toLocaleString("th-TH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function getErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "response" in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response;
    if (response?.data?.detail) return response.data.detail;
  }
  return error instanceof Error ? error.message : "ทำรายการไม่สำเร็จ";
}

function lineTotal(item: CartItem): number {
  return Number(item.product.selling_price) * item.qty;
}

function Slip({
  order,
  type,
  employeeName,
  menu,
  promptpayQrDataUrl,
}: {
  order: WapOrder | null;
  type: "customer" | "kitchen";
  employeeName: string;
  menu: WapMenu | null;
  promptpayQrDataUrl: string | null;
}): JSX.Element {
  if (!order) return <div />;
  const isKitchen = type === "kitchen";
  const shopName = menu?.brand_name?.trim() || "ระบบร้านอาหาร";
  const branchName = menu?.branch_name?.trim() || "ไม่ระบุสาขา";
  const branchLabel = branchName.startsWith("สาขา") ? branchName : `สาขา ${branchName}`;
  return (
    <div className="w-[280px] bg-white p-4 font-mono text-[12px] text-black">
      <div className="text-center">
        <p className="text-sm font-bold">{isKitchen ? "สลิปครัว" : "สลิปลูกค้า"}</p>
        <p className={`${isKitchen ? "mt-3" : "mt-2"} text-5xl font-black`}>{order.queue_display ?? "-"}</p>
        <p className="mt-2 text-sm font-bold">{shopName}</p>
        <p className="mt-0.5 text-[11px]">{branchLabel}</p>
        <p className="mt-2">เลขขาย {order.sale_order_number}</p>
        <p>พนักงาน {employeeName}</p>
        <p>{order.created_at ? new Date(order.created_at).toLocaleString("th-TH") : ""}</p>
      </div>
      <div className="my-3 border-t border-dashed border-black" />
      {order.customer_name || order.customer_phone ? (
        <div className="mb-2">
          {order.customer_name ? <p>ลูกค้า: {order.customer_name}</p> : null}
          {order.customer_phone ? <p>โทร: {order.customer_phone}</p> : null}
        </div>
      ) : null}
      <div className="space-y-2">
        {order.items.map((item) => (
          <div key={`${type}-${item.product_id}-${item.special_request ?? ""}`}>
            <div className="flex justify-between gap-2">
              <span>{item.qty} x {item.product_name}</span>
              {!isKitchen ? <span>{money(Number(item.unit_price) * item.qty)}</span> : null}
            </div>
            {item.special_request ? <p className="pl-3">* {item.special_request}</p> : null}
          </div>
        ))}
      </div>
      {!isKitchen ? (
        <>
          <div className="my-3 border-t border-dashed border-black" />
          <div className="space-y-1">
            <div className="flex justify-between"><span>รวม</span><span>{money(order.total_amount)}</span></div>
            <div className="flex justify-between"><span>รับเงิน</span><span>{money(order.paid_amount)}</span></div>
            <div className="flex justify-between"><span>ทอน</span><span>{money(order.change_amount)}</span></div>
            <div className="flex justify-between"><span>ชำระโดย</span><span>{paymentLabels[order.payment_method] ?? order.payment_method}</span></div>
          </div>
          <div className="my-3 border-t border-dashed border-black" />
          <p className="text-center text-[11px]">นำสลิปนี้ไปรับสินค้าที่เคาน์เตอร์</p>
          {promptpayQrDataUrl ? (
            <>
              <div className="my-3 border-t border-dashed border-black" />
              <div className="text-center">
                <p className="font-bold">PromptPay {branchLabel}</p>
                <img
                  src={promptpayQrDataUrl}
                  alt={`QR PromptPay ${branchName}`}
                  className="mx-auto mt-1 h-36 w-36"
                />
                <p className="font-bold">สแกนเพื่อชำระเงิน</p>
                <p className="text-[10px]">ยอดชำระ ฿{money(order.total_amount)}</p>
                {menu?.promptpay_name ? <p className="text-[10px]">ชื่อบัญชี {menu.promptpay_name}</p> : null}
              </div>
            </>
          ) : null}
        </>
      ) : (
        <>
          <div className="my-3 border-t border-dashed border-black" />
          <p className="text-center text-[11px]">ทำสินค้าแล้วส่งกลับเคาน์เตอร์</p>
        </>
      )}
    </div>
  );
}

export default function WapOrderPage(): JSX.Element {
  const { brandSlug } = useParams<{ brandSlug?: string }>();
  const location = useLocation();
  const { toast } = useToast();
  const isCounterWorkspace = location.pathname.startsWith("/counter/");
  const logout = useLogout(isCounterWorkspace ? "/counter" : "/login");
  const isOnline = useOnlineStatus();
  const user = useAuthStore((state) => state.user);
  const customerSlipRef = useRef<HTMLDivElement | null>(null);
  const kitchenSlipRef = useRef<HTMLDivElement | null>(null);
  const [promptpayQrDataUrl, setPromptpayQrDataUrl] = useState<string | null>(null);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [currentOrder, setCurrentOrder] = useState<WapOrder | null>(null);
  const [showSummary, setShowSummary] = useState(false);
  const [pendingPrint, setPendingPrint] = useState<"customer" | "kitchen" | null>(null);
  const [outboxSummary, setOutboxSummary] = useState<RestaurantOutboxSummary>({ pending: 0, syncing: 0, needsReview: 0 });
  const [handoverOpen, setHandoverOpen] = useState(false);
  const [closingCash, setClosingCash] = useState(0);
  const [handoverNote, setHandoverNote] = useState("");

  const customerPrint = useReactToPrint({ contentRef: customerSlipRef });
  const kitchenPrint = useReactToPrint({ contentRef: kitchenSlipRef });

  const offlineBrandSlug = brandSlug;
  const menuQuery = useQuery({
    queryKey: ["wap-menu", offlineBrandSlug],
    queryFn: async () => loadRestaurantMenu(offlineBrandSlug),
    retry: false,
  });
  const storeBase = brandSlug ? `/store/${brandSlug}` : "/restaurant";
  const orderPath = isCounterWorkspace
    ? "/counter/orders"
    : brandSlug ? `${storeBase}/orders` : "/restaurant/wap";
  const stockPath = brandSlug ? `${storeBase}/stock` : "/stock";
  const closeShiftPath = `${storeBase}/close-shift`;
  const centralBase = brandSlug ? `/central/${brandSlug}` : null;
  const employeeName = user?.display_name || [user?.first_name, user?.last_name].filter(Boolean).join(" ") || user?.username || "พนักงาน";
  const employeeIdentifier = user?.employee_code?.trim() || user?.username || "-";

  useEffect(() => {
    let cancelled = false;
    const payload = menuQuery.data?.promptpay_payload;
    if (!payload) {
      setPromptpayQrDataUrl(null);
      return () => {
        cancelled = true;
      };
    }
    void QRCode.toDataURL(payload, {
      errorCorrectionLevel: "M",
      margin: 1,
      width: 256,
      color: { dark: "#000000", light: "#ffffff" },
    }).then((dataUrl) => {
      if (!cancelled) setPromptpayQrDataUrl(dataUrl);
    }).catch(() => {
      if (!cancelled) setPromptpayQrDataUrl(null);
    });
    return () => {
      cancelled = true;
    };
  }, [menuQuery.data?.promptpay_payload]);

  useEffect(() => {
    const subscription = liveQuery(() => getRestaurantOutboxSummary(offlineBrandSlug)).subscribe({
      next: setOutboxSummary,
      error: () => undefined,
    });
    return () => subscription.unsubscribe();
  }, [offlineBrandSlug]);

  useEffect(() => {
    if (!isOnline) return;
    let cancelled = false;
    void (async () => {
      const before = await getRestaurantOutboxSummary(offlineBrandSlug);
      const after = await syncRestaurantPendingOrders(offlineBrandSlug);
      await menuQuery.refetch();
      if (cancelled) return;
      if (before.pending + before.syncing > 0 && after.pending + after.syncing === 0) {
        toast({ title: "ซิงก์ยอดขายแล้ว", description: after.needsReview > 0 ? `มี ${after.needsReview} รายการที่ต้องตรวจสอบ` : "ข้อมูลออฟไลน์ขึ้นเซิร์ฟเวอร์ครบแล้ว" });
      }
      if (currentOrder?.is_offline_pending && currentOrder.client_order_id) {
        const resolved = await getQueuedRestaurantOrder(currentOrder.client_order_id);
        if (resolved) setCurrentOrder(resolved);
      }
    })();
    return () => {
      cancelled = true;
    };
    // Reconnect is the trigger; current order and query changes must not start another sync.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOnline, offlineBrandSlug]);

  useEffect(() => {
    let removeListener: (() => Promise<void>) | undefined;
    void App.addListener("appStateChange", ({ isActive }) => {
      if (isActive) void syncRestaurantPendingOrders(offlineBrandSlug);
    }).then((handle) => {
      removeListener = () => handle.remove();
    });
    return () => {
      if (removeListener) void removeListener();
    };
  }, [offlineBrandSlug]);

  const products = menuQuery.data?.products ?? [];
  const visibleProducts = useMemo(() => {
    return [...products].sort((a, b) =>
      (a.category_name ?? "").localeCompare(b.category_name ?? "", "th")
      || a.name.localeCompare(b.name, "th")
    );
  }, [products]);

  const total = cart.reduce((sum, item) => sum + lineTotal(item), 0);

  useEffect(() => {
    if (!pendingPrint || !currentOrder) return;
    const printTimer = window.setTimeout(() => {
      if (pendingPrint === "customer") {
        customerPrint();
      } else {
        kitchenPrint();
      }
      setPendingPrint(null);
    }, 150);
    return () => window.clearTimeout(printTimer);
  }, [currentOrder, customerPrint, kitchenPrint, pendingPrint]);

  const createOrderMutation = useMutation({
    mutationFn: async (method: "cash" | "promptpay") => {
      const orderItems = cart.map((item) => ({
        product_id: item.product.id,
        qty: item.qty,
        special_request: item.note.trim() || null,
      }));
      return queueRestaurantOrder(offlineBrandSlug, {
        items: orderItems,
        payment_method: method,
        paid_amount: total,
        payments: [{
          payment_method: method,
          amount: total,
          reference_no: null,
        }],
        customer_name: null,
        customer_phone: null,
        note: null,
      }, menuQuery.data!);
    },
    onSuccess: ({ order, status, error }) => {
      setCurrentOrder(order);
      setShowSummary(true);
      setCart([]);
      if (status === "pending" || status === "syncing") {
        toast({ title: "บันทึกการขายในเครื่องแล้ว", description: "ระบบจะส่งข้อมูลขึ้นเซิร์ฟเวอร์อัตโนมัติเมื่ออินเทอร์เน็ตกลับมา" });
      } else if (status === "needs_review") {
        toast({ title: "เก็บรายการไว้แล้ว แต่ต้องตรวจสอบ", description: error, variant: "destructive" });
      }
      if (order.recipe_stock_warnings?.length) {
        toast({
          title: "ขายสำเร็จ แต่ stock ต้องตรวจสอบ",
          description: order.recipe_stock_warnings.join(" · "),
          variant: "destructive",
        });
      }
    },
    onError: (error) => {
      toast({ title: "รับออเดอร์ไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
    },
  });

  const customerSlipMutation = useMutation({
    mutationFn: async () => {
      if (!currentOrder) throw new Error("ยังไม่มีออเดอร์");
      if (currentOrder.client_order_id) {
        return markRestaurantLocalSlip(currentOrder.client_order_id, "customer");
      }
      return (await wapApi.markCustomerSlip(currentOrder.session_id)).data.data;
    },
    onSuccess: (order) => {
      setCurrentOrder(order);
      setPendingPrint("customer");
    },
    onError: (error) => {
      toast({ title: "พิมพ์สลิปลูกค้าไม่ได้", description: getErrorMessage(error), variant: "destructive" });
    },
  });

  const kitchenSlipMutation = useMutation({
    mutationFn: async () => {
      if (!currentOrder) throw new Error("ยังไม่มีออเดอร์");
      if (currentOrder.client_order_id) {
        return markRestaurantLocalSlip(currentOrder.client_order_id, "kitchen");
      }
      return (await wapApi.markKitchenSlip(currentOrder.session_id)).data.data;
    },
    onSuccess: (order) => {
      setCurrentOrder(order);
      setPendingPrint("kitchen");
      toast({ title: "ส่งเข้าครัวแล้ว", description: `คิว ${order.queue_display ?? "-"}` });
    },
    onError: (error) => {
      toast({ title: "พิมพ์สลิปครัวไม่ได้", description: getErrorMessage(error), variant: "destructive" });
    },
  });

  const handoverMutation = useMutation({
    mutationFn: async () => (await wapApi.handoverCounterShift({
      closing_cash: closingCash,
      note: handoverNote.trim() || null,
    })).data.data,
    onSuccess: (shift) => {
      setHandoverOpen(false);
      toast({
        title: "ส่งมอบ Counter แล้ว",
        description: `ปิด ${shift.shift_number} โดย ID ${employeeIdentifier} · ส่วนต่าง ฿${money(shift.cash_difference ?? 0)}`,
      });
      logout();
    },
    onError: (error) => {
      toast({ title: "เปลี่ยนกะไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
    },
  });

  function startCounterHandover(): void {
    if (!isOnline) {
      toast({ title: "ต้องออนไลน์ก่อนเปลี่ยนกะ", description: "ระบบต้องตรวจยอดและบันทึกผู้ส่งมอบก่อน", variant: "destructive" });
      return;
    }
    if (cart.length > 0) {
      toast({ title: "ยังเปลี่ยนกะไม่ได้", description: "กรุณาจบหรือยกเลิกออเดอร์ในตะกร้าก่อน", variant: "destructive" });
      return;
    }
    if (outboxSummary.pending + outboxSummary.syncing + outboxSummary.needsReview > 0) {
      toast({ title: "ยังมีรายการที่ต้องซิงก์หรือตรวจสอบ", description: "จัดการ Outbox ให้เรียบร้อยก่อนเปลี่ยนพนักงาน", variant: "destructive" });
      return;
    }
    setHandoverOpen(true);
  }

  function addProduct(product: WapMenuProduct): void {
    setCart((prev) => {
      const existing = prev.find((item) => item.product.id === product.id);
      if (existing) {
        return prev.map((item) => item.product.id === product.id ? { ...item, qty: item.qty + 1 } : item);
      }
      return [...prev, { product, qty: 1, note: "" }];
    });
  }

  function updateQty(productId: string, delta: number): void {
    setCart((prev) => prev
      .map((item) => item.product.id === productId ? { ...item, qty: item.qty + delta } : item)
      .filter((item) => item.qty > 0));
  }

  function resetOrder(): void {
    setCurrentOrder(null);
    setShowSummary(false);
  }

  const canSubmit = cart.length > 0 && total > 0;
  const customerSlipPrinted = Boolean(currentOrder?.customer_slip_printed_at);
  const isSummaryVisible = showSummary || Boolean(currentOrder);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="grid min-h-0 flex-1 gap-4">
        <section className={`${isSummaryVisible ? "hidden" : "flex"} min-h-0 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white`}>
          <div className="border-b border-slate-200 px-3 py-2 lg:px-4 lg:py-3">
            <div className="flex items-center gap-3">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="icon" className="h-9 w-9 shrink-0">
                    <Menu className="h-5 w-5" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-48">
                  <DropdownMenuItem asChild>
                    <Link to={orderPath} className="flex items-center">
                      <ReceiptText className="mr-2 h-4 w-4" />
                      รับออเดอร์
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <Link to={stockPath} className="flex items-center">
                      <Warehouse className="mr-2 h-4 w-4" />
                      Stock หน้าร้าน
                    </Link>
                  </DropdownMenuItem>
                  {isCounterWorkspace ? (
                    <DropdownMenuItem onClick={startCounterHandover}>
                      <ArrowRightLeft className="mr-2 h-4 w-4" />
                      เปลี่ยนกะ / พนักงาน
                    </DropdownMenuItem>
                  ) : (
                    <DropdownMenuItem asChild>
                      <Link to={closeShiftPath} className="flex items-center">
                        <ClipboardCheck className="mr-2 h-4 w-4" />
                        ปิดกะ
                      </Link>
                    </DropdownMenuItem>
                  )}
                  {brandSlug ? (
                    <>
                      <DropdownMenuItem asChild>
                        <Link to={`${storeBase}/replenishment-orders`} className="flex items-center">
                          <PackageOpen className="mr-2 h-4 w-4" />
                          รายการสั่งสินค้า
                        </Link>
                      </DropdownMenuItem>
                      <DropdownMenuItem asChild>
                        <Link to={`${storeBase}/credits`} className="flex items-center">
                          <CreditCard className="mr-2 h-4 w-4" />
                          แจ้งเติมเครดิต
                        </Link>
                      </DropdownMenuItem>
                      <DropdownMenuItem asChild>
                        <Link to={`${centralBase}/orders`} className="flex items-center">
                          <PackageCheck className="mr-2 h-4 w-4" />
                          ส่วนกลาง
                        </Link>
                      </DropdownMenuItem>
                    </>
                  ) : null}
                  {!isCounterWorkspace ? (
                    <>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem onClick={logout}>
                        <LogOut className="mr-2 h-4 w-4" />
                        ออกจากระบบ
                      </DropdownMenuItem>
                    </>
                  ) : null}
                </DropdownMenuContent>
              </DropdownMenu>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-slate-700">เมนูขายหน้าร้าน · {menuQuery.data?.branch_name ?? "สาขา"}</p>
                <p className="flex items-center gap-1 truncate text-xs text-slate-500"><UserRoundCheck className="h-3.5 w-3.5" />พนักงาน: {employeeName} · ID {employeeIdentifier}</p>
              </div>
              <div className="ml-auto flex shrink-0 items-center gap-2 text-xs">
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 font-semibold ${isOnline ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
                  {isOnline ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
                  {isOnline ? "ออนไลน์" : "ออฟไลน์"}
                </span>
                {outboxSummary.pending + outboxSummary.syncing > 0 ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-1 font-semibold text-blue-700">
                    <CloudUpload className="h-3.5 w-3.5" />
                    รอส่ง {outboxSummary.pending + outboxSummary.syncing}
                  </span>
                ) : null}
                {outboxSummary.needsReview > 0 ? (
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-1 font-semibold text-red-700"
                    onClick={() => void retryRestaurantNeedsReview(offlineBrandSlug)}
                    title="กดเพื่อลองส่งรายการที่ต้องตรวจสอบอีกครั้ง"
                  >
                    <AlertTriangle className="h-3.5 w-3.5" />
                    ตรวจสอบ {outboxSummary.needsReview}
                  </button>
                ) : null}
              </div>
            </div>
          </div>

          {outboxSummary.needsReview > 0 ? (
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800">
              <div>
                <p className="font-bold">มี {outboxSummary.needsReview} รายการที่ต้องตรวจสอบ</p>
                <p className="text-xs">{outboxSummary.latestError ?? "ตรวจ stock, ราคา หรือกะ แล้วลองส่งใหม่"}</p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="border-red-300 bg-white text-red-800 hover:bg-red-100"
                onClick={() => void retryRestaurantNeedsReview(offlineBrandSlug)}
              >
                ลองส่งอีกครั้ง
              </Button>
            </div>
          ) : null}

          {menuQuery.isLoading ? (
            <div className="flex h-72 items-center justify-center text-slate-500">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              โหลดเมนู
            </div>
          ) : menuQuery.isError ? (
            <div className="flex h-72 flex-col items-center justify-center gap-3 text-center text-slate-500">
              <p className="font-semibold text-slate-700">โหลดเมนูไม่สำเร็จ</p>
              <p className="max-w-md text-sm">
                {menuQuery.error instanceof Error ? menuQuery.error.message : "กรุณาลองโหลดเมนูอีกครั้ง"}
              </p>
              <Button variant="outline" onClick={() => void menuQuery.refetch()}>
                ลองใหม่
              </Button>
            </div>
          ) : visibleProducts.length === 0 ? (
            <div className="flex h-72 items-center justify-center text-slate-500">ยังไม่มีเมนูสำหรับขาย</div>
          ) : (
            <div className="min-h-0 flex-1 overflow-auto p-3 lg:p-4">
              <div className="grid gap-2 sm:grid-cols-2 2xl:grid-cols-3 2xl:gap-3">
                {visibleProducts.map((product) => {
                  const cartItem = cart.find((item) => item.product.id === product.id);
                  const qty = cartItem?.qty ?? 0;
                  return (
                    <div
                      key={product.id}
                      className="flex min-h-20 items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 lg:min-h-24 lg:gap-3 lg:p-4"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="line-clamp-2 font-semibold text-slate-950">{product.name}</p>
                      </div>
                      <div className="flex shrink-0 items-center gap-3">
                        <span className="whitespace-nowrap font-bold text-emerald-700">
                          ฿{money(product.selling_price)}
                        </span>
                        <div className="flex shrink-0 items-center gap-2">
                          <Button
                            variant="outline"
                            size="icon"
                            className="h-11 w-11"
                            disabled={qty <= 0}
                            onClick={() => updateQty(product.id, -1)}
                          >
                            <Minus className="h-4 w-4" />
                          </Button>
                          <span className="min-w-8 text-center text-base font-black text-slate-950 lg:min-w-12">{qty}</span>
                          <Button
                            size="icon"
                            className="h-11 w-11 bg-emerald-600 hover:bg-emerald-700"
                            onClick={() => addProduct(product)}
                          >
                            <Plus className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div className="border-t border-slate-200 p-3 lg:p-4">
            <Button
              className="h-11 w-full bg-slate-950 text-sm hover:bg-slate-800 lg:h-12 lg:text-base"
              disabled={!canSubmit}
              onClick={() => setShowSummary(true)}
            >
              สรุปออเดอร์ · {cart.length} รายการ · ฿{money(total)}
            </Button>
          </div>
        </section>

        <aside className={`${isSummaryVisible ? "flex" : "hidden"} min-h-0 flex-col rounded-lg border border-slate-200 bg-white`}>
          <div className="border-b border-slate-200 p-3 lg:p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <ReceiptText className="h-5 w-5 text-slate-700" />
                <h2 className="font-bold text-slate-950">สรุปออเดอร์</h2>
              </div>
              {currentOrder ? (
                <Button variant="outline" size="sm" onClick={resetOrder}>
                  เริ่มออเดอร์ใหม่
                </Button>
              ) : (
                <Button variant="outline" size="sm" onClick={() => setShowSummary(false)}>
                  กลับไปแก้ไขเมนู
                </Button>
              )}
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-auto p-3 lg:p-4">
            {currentOrder ? (
              <div className="space-y-4">
                <div className="rounded-lg bg-slate-950 p-4 text-center text-white lg:p-5">
                  <p className="text-xs uppercase tracking-[0.25em] text-slate-400">Queue</p>
                  <p className="mt-1 text-5xl font-black lg:mt-2 lg:text-6xl">{currentOrder.queue_display ?? "-"}</p>
                  <p className="mt-2 text-sm text-slate-300">รับเงินแล้ว ฿{money(currentOrder.total_amount)}</p>
                </div>
                <div className="space-y-3 rounded-lg border border-slate-200 p-4">
                  <p className="font-bold text-slate-950">รายการสินค้า</p>
                  <div className="space-y-2">
                    {currentOrder.items.map((item) => (
                      <div key={`${item.product_id}-${item.special_request ?? ""}`} className="flex items-start justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2">
                        <div className="min-w-0">
                          <p className="font-semibold text-slate-950">{item.product_name}</p>
                          {item.special_request ? <p className="text-xs text-slate-500">{item.special_request}</p> : null}
                        </div>
                        <div className="shrink-0 text-right">
                          <p className="font-black text-slate-950">{item.qty}</p>
                          <p className="text-sm font-bold text-emerald-700">฿{money(Number(item.unit_price) * item.qty)}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <Button
                  className="h-12 w-full"
                  onClick={() => customerSlipMutation.mutate()}
                  disabled={customerSlipMutation.isPending}
                >
                  {customerSlipMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Printer className="mr-2 h-4 w-4" />}
                  {customerSlipPrinted ? "พิมพ์สลิปลูกค้าซ้ำ" : "พิมพ์สลิปลูกค้า"}
                </Button>
                <Button
                  className="h-12 w-full bg-orange-600 hover:bg-orange-700"
                  onClick={() => kitchenSlipMutation.mutate()}
                  disabled={kitchenSlipMutation.isPending || !customerSlipPrinted}
                >
                  {kitchenSlipMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ChefHat className="mr-2 h-4 w-4" />}
                  {!customerSlipPrinted
                    ? "พิมพ์สลิปลูกค้าก่อนส่งครัว"
                    : currentOrder.kitchen_slip_printed_at
                      ? "พิมพ์ออเดอร์ส่งครัวซ้ำ"
                      : "พิมพ์ออเดอร์ส่งครัว"}
                </Button>
              </div>
            ) : (
              <div className="space-y-4">
                {cart.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-slate-500">กดสินค้าเพื่อเริ่มออเดอร์</div>
                ) : (
                  <div className="space-y-3">
                    {cart.map((item) => (
                      <div key={item.product.id} className="rounded-lg border border-slate-200 p-3">
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <p className="font-semibold text-slate-950">{item.product.name}</p>
                            <p className="text-sm text-slate-500">฿{money(item.product.selling_price)}</p>
                          </div>
                          <div className="flex shrink-0 items-center gap-2">
                            <Button
                              variant="outline"
                              size="icon"
                              className="h-9 w-9"
                              onClick={() => updateQty(item.product.id, -1)}
                            >
                              <Minus className="h-4 w-4" />
                            </Button>
                            <div className="min-w-16 text-center">
                              <p className="text-lg font-black text-slate-950">{item.qty}</p>
                            </div>
                            <Button
                              size="icon"
                              className="h-9 w-9 bg-emerald-600 hover:bg-emerald-700"
                              onClick={() => addProduct(item.product)}
                            >
                              <Plus className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

              </div>
            )}
          </div>

          {!currentOrder ? (
            <div className="border-t border-slate-200 p-3 lg:p-4">
              <div className="mb-3 space-y-1 text-sm">
                <div className="flex justify-between"><span>ยอดรวม</span><span className="font-bold">฿{money(total)}</span></div>
                <div className="text-slate-500">เลือกวิธีรับเงินเพื่อออกคิว</div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Button
                  className="h-12 px-2 text-sm bg-slate-950 hover:bg-slate-800"
                  disabled={!canSubmit || createOrderMutation.isPending}
                  onClick={() => createOrderMutation.mutate("cash")}
                >
                  {createOrderMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  <span className="truncate">รับเงินสด / ออกคิว</span>
                </Button>
                <Button
                  className="h-12 px-2 text-sm bg-emerald-600 hover:bg-emerald-700"
                  disabled={!canSubmit || createOrderMutation.isPending}
                  onClick={() => createOrderMutation.mutate("promptpay")}
                >
                  {createOrderMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  <span className="truncate">PromptPay จ่ายแล้ว / ออกคิว</span>
                </Button>
              </div>
            </div>
          ) : null}
        </aside>
      </div>

      <Dialog open={handoverOpen} onOpenChange={setHandoverOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>เปลี่ยนกะ Counter</DialogTitle>
            <DialogDescription>ปิดความรับผิดชอบของพนักงานคนปัจจุบัน แล้วให้คนถัดไปลงชื่อโดยไม่ Pair เครื่องใหม่</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
              <p className="font-semibold">ผู้ส่งมอบ: {employeeName}</p>
              <p className="mt-1 text-blue-700">Employee ID: {employeeIdentifier} · Shift {menuQuery.data?.shift_id ?? "-"}</p>
            </div>
            <div className="space-y-2">
              <label htmlFor="counter-closing-cash" className="text-sm font-medium text-slate-700">เงินสดที่นับได้</label>
              <input
                id="counter-closing-cash"
                type="number"
                min="0"
                step="0.01"
                className="h-12 w-full rounded-lg border border-slate-300 px-3 text-lg font-semibold"
                value={closingCash}
                onChange={(event) => setClosingCash(Math.max(Number(event.target.value || 0), 0))}
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="counter-handover-note" className="text-sm font-medium text-slate-700">หมายเหตุ (ถ้ามี)</label>
              <textarea
                id="counter-handover-note"
                className="min-h-20 w-full rounded-lg border border-slate-300 px-3 py-2"
                value={handoverNote}
                onChange={(event) => setHandoverNote(event.target.value)}
                placeholder="เช่น ส่งมอบกะเช้าให้กะบ่าย"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setHandoverOpen(false)} disabled={handoverMutation.isPending}>ยกเลิก</Button>
            <Button className="bg-amber-600 hover:bg-amber-700" onClick={() => handoverMutation.mutate()} disabled={handoverMutation.isPending}>
              {handoverMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRightLeft className="h-4 w-4" />}
              ปิดกะและเปลี่ยนพนักงาน
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="fixed -left-[9999px] top-0">
        <div ref={customerSlipRef} className="wap-print-slip">
          <Slip
            order={currentOrder}
            type="customer"
            employeeName={employeeName}
            menu={menuQuery.data ?? null}
            promptpayQrDataUrl={promptpayQrDataUrl}
          />
        </div>
        <div ref={kitchenSlipRef} className="wap-print-slip">
          <Slip
            order={currentOrder}
            type="kitchen"
            employeeName={employeeName}
            menu={menuQuery.data ?? null}
            promptpayQrDataUrl={null}
          />
        </div>
      </div>
    </div>
  );
}
