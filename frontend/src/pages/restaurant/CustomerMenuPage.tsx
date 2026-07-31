import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChefHat,
  ChevronRight,
  Clock3,
  History,
  Loader2,
  ReceiptText,
  ShoppingBag,
  Utensils
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import {
  CartBar,
  CartSheet,
  CategoryTabs,
  ItemDetailSheet,
  MenuList,
  MenuSearch,
  StatusList,
  createMobileCartLineId,
  filterMenuProducts,
  formatCurrency,
  normalizeMobileCartItems,
  type MobileCartItem,
  type MobileMenuItem
} from "@/pages/restaurant/components/MobileOrdering";

type MenuItem = MobileMenuItem;

type MenuResponse = {
  session_id: string;
  queue_number: number | null;
  table_name: string | null;
  source_type: "dine_in" | "quick_service";
  branch_name: string;
  fb_service_mode: string;
  categories: { id: string; name: string }[];
  products: MenuItem[];
  session_status: string;
  opened_at: string;
  bill_at_table_enabled: boolean;
};

type CartItem = MobileCartItem<MenuItem>;

type OrderHistory = {
  id: string;
  order_number: string;
  status: string;
  note: string | null;
  created_at: string;
  subtotal: number;
  items: { id: string; product_name: string; qty: number; unit_price: number; status: string; special_request?: string | null }[];
};

type OrderStatus = {
  session_id: string;
  queue_number: number | null;
  session_status: string;
  items: { id: string; product_name: string; qty: number; unit_price: number; status: string; special_request?: string | null }[];
  orders: OrderHistory[];
  total_item_count: number;
  total_amount: number;
};

const STATUS_LABEL: Record<string, { label: string; color: string }> = {
  pending: { label: "รอรับออเดอร์", color: "bg-amber-100 text-amber-800" },
  cooking: { label: "กำลังทำ", color: "bg-sky-100 text-sky-800" },
  done: { label: "พร้อมเสิร์ฟ", color: "bg-emerald-100 text-emerald-800" },
  served: { label: "เสิร์ฟแล้ว", color: "bg-slate-100 text-slate-600" },
  cancelled: { label: "ยกเลิก", color: "bg-red-100 text-red-700" }
};

function getErrorMessage(error: unknown): string | null {
  if (!error) return null;
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail ?? error.response?.data?.error?.message;
    if (typeof detail === "string") return detail;
  }
  return error instanceof Error ? error.message : "ทำรายการไม่สำเร็จ";
}

function isNotFoundError(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 404;
}

function readCartCache(token?: string): CartItem[] {
  if (!token) return [];
  const raw = localStorage.getItem(`dining-cart-${token}`);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as CartItem[];
    return Array.isArray(parsed) ? normalizeMobileCartItems(parsed) : [];
  } catch {
    localStorage.removeItem(`dining-cart-${token}`);
    return [];
  }
}

function formatOrderTime(value: string): string {
  return new Intl.DateTimeFormat("th-TH", {
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

export default function CustomerMenuPage(): JSX.Element {
  const { token } = useParams<{ token: string }>();
  const queryClient = useQueryClient();
  const [cart, setCart] = useState<CartItem[]>(() => readCartCache(token));
  const [cartOpen, setCartOpen] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [showMenu, setShowMenu] = useState(true);
  const [note, setNote] = useState("");
  const [customProduct, setCustomProduct] = useState<MenuItem | null>(null);
  const [customOptions, setCustomOptions] = useState<string[]>([]);
  const [customNote, setCustomNote] = useState("");
  const audioRef = useRef<AudioContext | null>(null);
  const notifiedDoneSessionRef = useRef<string | null>(null);

  const menuQuery = useQuery({
    queryKey: ["public-menu", token],
    queryFn: async () => (await axios.get(`/api/public/menu/${token}`)).data.data as MenuResponse,
    enabled: Boolean(token)
  });

  const menu = menuQuery.data;
  const isTakeaway = menu?.source_type === "quick_service";
  const statusLabels = isTakeaway
    ? { ...STATUS_LABEL, done: { label: "พร้อมรับ", color: "bg-emerald-100 text-emerald-800" }, served: { label: "รับแล้ว", color: "bg-slate-100 text-slate-600" } }
    : STATUS_LABEL;

  useEffect(() => {
    if (!token) return;
    if (cart.length > 0) {
      localStorage.setItem(`dining-cart-${token}`, JSON.stringify(cart));
    } else {
      localStorage.removeItem(`dining-cart-${token}`);
    }
  }, [cart, token]);

  const statusQuery = useQuery({
    queryKey: ["order-status", token],
    queryFn: async () =>
      (await axios.get(`/api/public/menu/${token}/status`)).data.data as OrderStatus,
    enabled: Boolean(token && menu?.session_id),
    refetchInterval: 8_000,
    retry: false
  });

  useEffect(() => {
    const items = (statusQuery.data?.items ?? []).filter((item) => item.status !== "cancelled");
    const allDone = items.length > 0 && items.every((item) => item.status === "done" || item.status === "served");
    if (!allDone) return;
    if (statusQuery.data?.session_id === notifiedDoneSessionRef.current) return;
    notifiedDoneSessionRef.current = statusQuery.data?.session_id ?? null;

    if (!audioRef.current) audioRef.current = new AudioContext();
    const ctx = audioRef.current;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.8);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.8);
  }, [statusQuery.data]);

  const orderMutation = useMutation({
    mutationFn: async () => {
      const res = await axios.post(`/api/public/menu/${token}/orders`, {
        items: cart.map((item) => ({
          product_id: item.product.id,
          qty: item.qty,
          special_request: item.special_request || null
        })),
        note: note || null
      });
      return res.data.data as { session_id: string; queue_number: number | null };
    },
    onSuccess: () => {
      setCart([]);
      setCartOpen(false);
      setShowMenu(false);
      setNote("");
      queryClient.invalidateQueries({ queryKey: ["order-status"] });
    }
  });

  const billMutation = useMutation({
    mutationFn: async () => axios.post(`/api/public/menu/${token}/bill`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["order-status"] })
  });

  function buildSpecialRequest(options: string[], customText: string): string {
    return [...options, customText.trim()].filter(Boolean).join(", ");
  }

  function addToCart(product: MenuItem, specialRequest = ""): void {
    const normalizedRequest = specialRequest.trim();
    setCart((prev) => {
      const existing = prev.find(
        (item) =>
          item.product.id === product.id &&
          item.special_request.trim() === normalizedRequest
      );
      if (existing) {
        return prev.map((item) => item.line_id === existing.line_id ? {
          ...item,
          qty: item.qty + 1
        } : item);
      }
      return [...prev, {
        line_id: createMobileCartLineId(product.id),
        product,
        qty: 1,
        special_request: normalizedRequest
      }];
    });
  }

  function removeFromCart(lineId: string): void {
    setCart((prev) => prev.filter((item) => item.line_id !== lineId));
  }

  function updateItemNote(lineId: string, value: string): void {
    setCart((prev) => prev.map((item) => item.line_id === lineId ? { ...item, special_request: value } : item));
  }

  function updateQty(lineId: string, delta: number): void {
    setCart((prev) =>
      prev
        .map((item) => {
          if (item.line_id !== lineId) return item;
          const next = item.qty + delta;
          return next <= 0 ? null : { ...item, qty: next };
        })
        .filter(Boolean) as CartItem[]
    );
  }

  const visibleProducts = useMemo(
    () => filterMenuProducts(menu?.products ?? [], selectedCategory, searchTerm),
    [menu?.products, searchTerm, selectedCategory]
  );

  const cartTotal = cart.reduce((sum, item) => sum + item.product.selling_price * item.qty, 0);
  const cartCount = cart.reduce((sum, item) => sum + item.qty, 0);
  const orderStatus = statusQuery.data;
  const queueNum = orderStatus?.queue_number ?? menuQuery.data?.queue_number;
  const activeOrderItems = (orderStatus?.items ?? []).filter((item) => item.status !== "cancelled");
  const hasOrderItems = activeOrderItems.length > 0;
  const allDone = hasOrderItems && activeOrderItems.every((item) => item.status === "done" || item.status === "served");
  const canOrder = (orderStatus?.session_status ?? menu?.session_status) === "open";
  const orderError = getErrorMessage(orderMutation.error);
  const billError = getErrorMessage(billMutation.error);
  const sessionExpired = isNotFoundError(statusQuery.error);
  const statusError = sessionExpired ? null : getErrorMessage(statusQuery.error);
  const menuError = getErrorMessage(menuQuery.error);

  useEffect(() => {
    const currentStatus = statusQuery.data?.session_status ?? menu?.session_status;
    if (currentStatus && currentStatus !== "open") {
      setCartOpen(false);
    }
  }, [menu?.session_status, statusQuery.data?.session_status]);

  if (menuQuery.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <Loader2 className="h-8 w-8 animate-spin text-slate-700" />
      </div>
    );
  }

  if (!menu || sessionExpired) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4 text-center">
        <div>
          <p className="text-2xl font-bold text-slate-800">
            {sessionExpired
              ? "QR รอบนี้หมดอายุแล้ว"
              : menuQuery.isError
                ? "โหลดเมนูไม่สำเร็จ"
                : "ไม่พบเมนูนี้"}
          </p>
          <p className="mt-2 text-slate-500">
            {sessionExpired
              ? isTakeaway
                ? "คิวรับกลับนี้ถูกปิดแล้ว กรุณาติดต่อพนักงานหากต้องการความช่วยเหลือ"
                : "โต๊ะถูกปิดแล้ว กรุณาติดต่อพนักงานหากต้องการความช่วยเหลือ"
              : menuError ?? "QR อาจหมดอายุหรือไม่ถูกต้อง"}
          </p>
          {menuQuery.isError ? (
            <button
              type="button"
              className="mt-4 rounded-full bg-slate-950 px-4 py-2 text-sm font-semibold text-white"
              onClick={() => void menuQuery.refetch()}
            >
              ลองโหลดเมนูอีกครั้ง
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 pb-32">
      <div className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 px-4 py-3 shadow-sm backdrop-blur">
        <div className="mx-auto max-w-lg">
          <div className="flex items-center gap-2 text-xs font-semibold text-emerald-700">
            <Utensils className="h-3.5 w-3.5" />
            <span className="truncate">{menu.branch_name}</span>
          </div>
          <div className="mt-1 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-xl font-bold text-slate-950">
                {isTakeaway
                  ? `รับกลับ${queueNum ? ` · คิว ${String(queueNum).padStart(3, "0")}` : ""}`
                  : menu.table_name
                    ? `โต๊ะ ${menu.table_name}`
                    : "เมนูอาหาร"}
              </p>
              <p className="text-xs text-slate-500">เลือกเมนู ใส่หมายเหตุ แล้วส่งออเดอร์เข้าครัว</p>
            </div>
            {queueNum ? (
              <div className="shrink-0 rounded-2xl bg-slate-950 px-3 py-2 text-center text-white">
                <span className="block text-[10px] font-medium uppercase text-slate-300">Queue</span>
                <span className="text-xl font-bold">{String(queueNum).padStart(3, "0")}</span>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <main className="mx-auto max-w-lg">
        <section className="mx-4 mt-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-700">
              {isTakeaway ? <ShoppingBag className="h-5 w-5" /> : <ChefHat className="h-5 w-5" />}
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-slate-950">{isTakeaway ? "สั่งอาหารรับกลับได้ทันที" : "สั่งอาหารที่โต๊ะได้ทันที"}</p>
              <p className="mt-0.5 text-sm text-slate-500">
                {isTakeaway ? "QR นี้ใช้สำหรับคิวรับกลับของคุณเท่านั้น" : "เพิ่มรายการได้หลายรอบ ระบบจะรวมกับโต๊ะเดิม"}
              </p>
            </div>
          </div>
        </section>

        {orderError || billError || statusError ? (
          <section className="mx-4 mt-4 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm font-medium text-red-700">
            <p>{orderError || billError || statusError}</p>
            {statusError ? (
              <button
                type="button"
                className="mt-3 rounded-full bg-red-700 px-3 py-2 text-xs font-semibold text-white"
                onClick={() => void statusQuery.refetch()}
              >
                ลองโหลดสถานะอีกครั้ง
              </button>
            ) : null}
          </section>
        ) : null}

        {menu.session_id && !orderStatus && statusQuery.isLoading ? (
          <section className="mx-4 mt-4 rounded-2xl border border-sky-200 bg-sky-50 p-4 shadow-sm">
            <div className="flex items-center gap-3 text-sky-800">
              <Loader2 className="h-5 w-5 animate-spin" />
              <div>
                <p className="font-bold">กำลังโหลดสถานะออเดอร์</p>
                <p className="text-xs text-sky-700">รอสักครู่ ระบบกำลังตรวจรายการล่าสุดของ{isTakeaway ? "คิวนี้" : "โต๊ะนี้"}</p>
              </div>
            </div>
          </section>
        ) : null}

        {orderStatus && (hasOrderItems || orderStatus.session_status === "bill_requested") ? (
          <section className={`mx-4 mt-4 rounded-2xl border p-4 shadow-sm ${allDone ? "border-emerald-200 bg-emerald-50" : "border-sky-200 bg-sky-50"}`}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className={`text-base font-bold ${allDone ? "text-emerald-900" : "text-sky-900"}`}>
                  {orderStatus.session_status === "bill_requested" ? "เรียกบิลแล้ว" : allDone ? (isTakeaway ? "อาหารพร้อมรับแล้ว" : "อาหารพร้อมเสิร์ฟแล้ว") : "สถานะออเดอร์"}
                </p>
                <p className={`mt-0.5 text-xs ${allDone ? "text-emerald-700" : "text-sky-700"}`}>
                  อัปเดตอัตโนมัติทุก 8 วินาที
                </p>
              </div>
              {orderStatus.session_status === "open" && menu.bill_at_table_enabled ? (
                <button
                  type="button"
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-slate-950 px-3 py-2 text-xs font-semibold text-white disabled:opacity-60"
                  disabled={billMutation.isPending}
                  onClick={() => !billMutation.isPending && billMutation.mutate()}
                >
                  {billMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ReceiptText className="h-3.5 w-3.5" />}
                  เรียกบิล
                </button>
              ) : null}
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <div className="rounded-xl bg-white px-3 py-2">
                <p className="text-xs text-slate-500">จำนวนที่สั่ง</p>
                <p className="font-bold text-slate-950">{orderStatus.total_item_count} รายการ</p>
              </div>
              <div className="rounded-xl bg-white px-3 py-2 text-right">
                <p className="text-xs text-slate-500">ยอดรวมโดยประมาณ</p>
                <p className="font-bold text-emerald-700">{formatCurrency(Number(orderStatus.total_amount))}</p>
              </div>
            </div>
            {allDone ? (
              <div className="mt-3 flex items-center gap-2 rounded-xl bg-white px-3 py-2 text-emerald-800">
                <CheckCircle2 className="h-5 w-5" />
                <span className="font-semibold">{isTakeaway ? "กรุณารับอาหารที่เคาน์เตอร์" : "พนักงานจะนำอาหารไปเสิร์ฟที่โต๊ะ"}</span>
              </div>
            ) : null}
            {orderStatus.session_status === "bill_requested" ? (
              <div className="mt-3 flex items-center gap-2 rounded-xl bg-white px-3 py-2 text-slate-700">
                <Clock3 className="h-5 w-5" />
                <span className="font-semibold">พนักงานกำลังเตรียมปิดบิล ไม่สามารถสั่งเพิ่มได้</span>
              </div>
            ) : null}
            <button
              type="button"
              className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-sky-700"
              disabled={!canOrder}
              onClick={() => setShowMenu(true)}
            >
              สั่งเพิ่ม <ChevronRight className="h-4 w-4" />
            </button>
          </section>
        ) : null}

        {orderStatus?.orders.length ? (
          <section className="mx-4 mt-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-center gap-2">
              <History className="h-5 w-5 text-slate-700" />
              <div>
                <p className="font-bold text-slate-950">รายการที่สั่งในรอบนี้</p>
                <p className="text-xs text-slate-500">รวมทุกครั้งที่สั่งจาก QR ใบนี้</p>
              </div>
            </div>
            <div className="mt-4 space-y-4">
              {orderStatus.orders.map((order, index) => (
                <div key={order.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-950 text-xs font-bold text-white">
                        {index + 1}
                      </span>
                      <div>
                        <p className="text-sm font-bold text-slate-950">สั่งเวลา {formatOrderTime(order.created_at)} น.</p>
                        <p className="text-[11px] text-slate-500">{order.order_number}</p>
                      </div>
                    </div>
                    <span className="text-sm font-bold text-emerald-700">{formatCurrency(Number(order.subtotal))}</span>
                  </div>
                  {order.note ? (
                    <div className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">หมายเหตุ: {order.note}</div>
                  ) : null}
                  <StatusList items={order.items} labels={statusLabels} />
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {showMenu && canOrder ? (
          <>
            <MenuSearch value={searchTerm} onChange={setSearchTerm} />
            <CategoryTabs categories={menu.categories} selectedCategory={selectedCategory} onSelect={setSelectedCategory} />
            <MenuList products={visibleProducts} cart={cart} onAdd={addToCart} onQtyChange={updateQty} onCustomize={(product) => {
              setCustomProduct(product);
              setCustomOptions([]);
              setCustomNote("");
            }} />
          </>
        ) : null}
      </main>

      {!cartOpen && canOrder ? <CartBar count={cartCount} total={cartTotal} onOpen={() => setCartOpen(true)} /> : null}
      <CartSheet
        open={cartOpen}
        title="ตรวจสอบออเดอร์"
        subtitle={`${cartCount} รายการสำหรับ${isTakeaway ? "คิวรับกลับนี้" : menu.table_name ? `โต๊ะ ${menu.table_name}` : "ออเดอร์นี้"}`}
        cart={cart}
        note={note}
        notePlaceholder="หมายเหตุรวมสำหรับออเดอร์นี้"
        submitLabel="สั่งอาหาร"
        isSubmitting={orderMutation.isPending || !canOrder}
        onClose={() => setCartOpen(false)}
        onRemove={removeFromCart}
        onQtyChange={updateQty}
        onItemNoteChange={updateItemNote}
        onNoteChange={setNote}
        onSubmit={() => canOrder && orderMutation.mutate()}
      />
      <ItemDetailSheet
        product={customProduct}
        note={customNote}
        selectedOptions={customOptions}
        onNoteChange={setCustomNote}
        onToggleOption={(option) => setCustomOptions((prev) => prev.includes(option) ? prev.filter((item) => item !== option) : [...prev, option])}
        onClose={() => setCustomProduct(null)}
        onSubmit={() => {
          if (!customProduct) return;
          addToCart(customProduct, buildSpecialRequest(customOptions, customNote));
          setCustomProduct(null);
          setCustomOptions([]);
          setCustomNote("");
        }}
      />
    </div>
  );
}
