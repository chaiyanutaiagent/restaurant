import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChefHat, ChevronRight, Loader2, Ticket, Utensils } from "lucide-react";
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
  filterMenuProducts,
  type MobileCartItem,
  type MobileMenuItem
} from "@/pages/restaurant/components/MobileOrdering";

type MenuItem = MobileMenuItem;
type QSMenu = {
  branch_name: string;
  fb_service_mode: string;
  queue_prefix: string;
  categories: { id: string; name: string }[];
  products: MenuItem[];
};
type CartItem = MobileCartItem<MenuItem>;
type OrderResult = { session_id: string; queue_number: number | null; queue_display: string | null };
type OrderStatus = { session_id: string; queue_number: number | null; session_status: string; items: { id: string; product_name: string; qty: number; status: string; special_request?: string | null }[] };

const STATUS_LABEL: Record<string, { label: string; color: string }> = {
  pending: { label: "รอรับออเดอร์", color: "bg-amber-100 text-amber-800" },
  cooking: { label: "กำลังเตรียม", color: "bg-sky-100 text-sky-800" },
  done: { label: "พร้อมรับ", color: "bg-emerald-100 text-emerald-800" },
  served: { label: "รับแล้ว", color: "bg-slate-100 text-slate-600" },
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

function readCartCache(token?: string): CartItem[] {
  if (!token) return [];
  const raw = localStorage.getItem(`qs-cart-${token}`);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as CartItem[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    localStorage.removeItem(`qs-cart-${token}`);
    return [];
  }
}

export default function QuickServicePage(): JSX.Element {
  const { token } = useParams<{ token: string }>();
  const queryClient = useQueryClient();
  const audioRef = useRef<AudioContext | null>(null);
  const notifiedDoneSessionRef = useRef<string | null>(null);

  const [cart, setCart] = useState<CartItem[]>(() => readCartCache(token));
  const [cartOpen, setCartOpen] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [orderResult, setOrderResult] = useState<OrderResult | null>(() => {
    const raw = localStorage.getItem(`qs-order-${token}`);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as OrderResult;
    } catch {
      localStorage.removeItem(`qs-order-${token}`);
      return null;
    }
  });
  const [note, setNote] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [customProduct, setCustomProduct] = useState<MenuItem | null>(null);
  const [customOptions, setCustomOptions] = useState<string[]>([]);
  const [customNote, setCustomNote] = useState("");

  const menuQuery = useQuery({
    queryKey: ["qs-menu", token],
    queryFn: async () => (await axios.get(`/api/public/qs/${token}`)).data.data as QSMenu,
    enabled: Boolean(token)
  });

  const statusQuery = useQuery({
    queryKey: ["qs-status", orderResult?.session_id],
    queryFn: async () =>
      (await axios.get(`/api/public/qs/${token}/status?session_id=${orderResult!.session_id}`)).data.data as OrderStatus,
    enabled: Boolean(orderResult?.session_id),
    refetchInterval: 7_000
  });

  const orderStatus = statusQuery.data;
  const menu = menuQuery.data;

  useEffect(() => {
    if (!token) return;
    if (cart.length > 0) {
      localStorage.setItem(`qs-cart-${token}`, JSON.stringify(cart));
    } else {
      localStorage.removeItem(`qs-cart-${token}`);
    }
  }, [cart, token]);

  useEffect(() => {
    const items = orderStatus?.items ?? [];
    const allDone = items.length > 0 && items.every((item) => item.status === "done" || item.status === "served");
    if (!allDone) return;
    if (orderStatus?.session_id === notifiedDoneSessionRef.current) return;
    notifiedDoneSessionRef.current = orderStatus?.session_id ?? null;

    if (!audioRef.current) audioRef.current = new AudioContext();
    const ctx = audioRef.current;
    [0, 0.25, 0.5].forEach((offset, index) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = [660, 880, 1100][index];
      gain.gain.setValueAtTime(0.35, ctx.currentTime + offset);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + offset + 0.35);
      osc.start(ctx.currentTime + offset);
      osc.stop(ctx.currentTime + offset + 0.35);
    });
  }, [orderStatus]);

  const orderMutation = useMutation({
    mutationFn: async () => {
      const params = new URLSearchParams();
      if (customerName.trim()) params.set("customer_name", customerName.trim());
      if (customerPhone.trim()) params.set("customer_phone", customerPhone.trim());
      const res = await axios.post(`/api/public/qs/${token}/orders?${params}`, {
        items: cart.map((item) => ({ product_id: item.product.id, qty: item.qty, special_request: item.special_request || null })),
        note: note || null
      });
      return res.data.data as OrderResult;
    },
    onSuccess: (result) => {
      setOrderResult(result);
      localStorage.setItem(`qs-order-${token}`, JSON.stringify(result));
      setCart([]);
      setCartOpen(false);
      setNote("");
      setCustomerName("");
      setCustomerPhone("");
      queryClient.invalidateQueries({ queryKey: ["qs-status"] });
    }
  });

  const visibleProducts = useMemo(
    () => filterMenuProducts(menu?.products ?? [], selectedCategory, searchTerm),
    [menu?.products, searchTerm, selectedCategory]
  );

  function buildSpecialRequest(options: string[], customText: string): string {
    return [...options, customText.trim()].filter(Boolean).join(", ");
  }

  function addToCart(product: MenuItem, specialRequest = ""): void {
    setCart((prev) => {
      const existing = prev.find((item) => item.product.id === product.id);
      return existing
        ? prev.map((item) => item.product.id === product.id ? { ...item, qty: item.qty + 1, special_request: specialRequest || item.special_request } : item)
        : [...prev, { product, qty: 1, special_request: specialRequest }];
    });
  }

  function updateQty(id: string, delta: number): void {
    setCart((prev) => prev.map((item) => item.product.id === id ? { ...item, qty: item.qty + delta } : item).filter((item) => item.qty > 0));
  }

  function removeFromCart(productId: string): void {
    setCart((prev) => prev.filter((item) => item.product.id !== productId));
  }

  function updateItemNote(productId: string, value: string): void {
    setCart((prev) => prev.map((item) => item.product.id === productId ? { ...item, special_request: value } : item));
  }

  const cartCount = cart.reduce((sum, item) => sum + item.qty, 0);
  const cartTotal = cart.reduce((sum, item) => sum + item.product.selling_price * item.qty, 0);
  const allDone = (orderStatus?.items ?? []).length > 0 && (orderStatus?.items ?? []).every((item) => item.status === "done" || item.status === "served");
  const orderError = getErrorMessage(orderMutation.error);

  if (menuQuery.isLoading) {
    return <div className="flex min-h-screen items-center justify-center bg-slate-50"><Loader2 className="h-8 w-8 animate-spin text-slate-700" /></div>;
  }
  if (!menu) {
    return <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4 text-center"><p className="text-slate-500">ไม่พบ QR นี้</p></div>;
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
              <p className="truncate text-xl font-bold text-slate-950">สั่งอาหารรับเอง</p>
              <p className="text-xs text-slate-500">ส่งออเดอร์แล้วรอเรียกคิวที่เคาน์เตอร์</p>
            </div>
            {orderResult?.queue_display ? (
              <div className="shrink-0 rounded-2xl bg-slate-950 px-3 py-2 text-center text-white">
                <span className="block text-[10px] font-medium uppercase text-slate-300">Queue</span>
                <span className="text-xl font-bold">{orderResult.queue_display}</span>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <main className="mx-auto max-w-lg">
        <section className="mx-4 mt-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-700">
              <Ticket className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-slate-950">สั่งล่วงหน้าแล้วรับที่เคาน์เตอร์</p>
              <p className="mt-0.5 text-sm text-slate-500">กรอกชื่อไว้เพื่อให้พนักงานเรียกได้ง่ายขึ้น</p>
            </div>
          </div>
        </section>

        {orderError ? (
          <section className="mx-4 mt-4 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm font-medium text-red-700">
            {orderError}
          </section>
        ) : null}

        {orderResult && !orderStatus && statusQuery.isLoading ? (
          <section className="mx-4 mt-4 rounded-2xl border border-sky-200 bg-sky-50 p-4 shadow-sm">
            <div className="flex items-center gap-3 text-sky-800">
              <Loader2 className="h-5 w-5 animate-spin" />
              <div>
                <p className="font-bold">กำลังโหลดสถานะคิว</p>
                <p className="text-xs text-sky-700">รอสักครู่ ระบบกำลังตรวจรายการล่าสุดของคิว {orderResult.queue_display ?? "-"}</p>
              </div>
            </div>
          </section>
        ) : null}

        {orderResult && orderStatus ? (
          <section className={`mx-4 mt-4 rounded-2xl border p-4 shadow-sm ${allDone ? "border-emerald-200 bg-emerald-50" : "border-sky-200 bg-sky-50"}`}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className={`text-base font-bold ${allDone ? "text-emerald-900" : "text-sky-900"}`}>
                  {allDone ? "พร้อมรับที่เคาน์เตอร์" : "สถานะออเดอร์"}
                </p>
                <p className={`mt-0.5 text-xs ${allDone ? "text-emerald-700" : "text-sky-700"}`}>
                  อัปเดตอัตโนมัติทุก 7 วินาที
                </p>
              </div>
              <span className={`rounded-2xl px-3 py-2 text-center text-sm font-bold ${allDone ? "bg-emerald-600 text-white" : "bg-slate-950 text-white"}`}>
                คิว {orderResult.queue_display ?? "-"}
              </span>
            </div>
            {allDone ? (
              <div className="mt-3 flex items-center gap-2 rounded-xl bg-white px-3 py-2 text-emerald-800">
                <CheckCircle2 className="h-5 w-5" />
                <span className="font-semibold">นำเลขคิวไปแจ้งพนักงานที่เคาน์เตอร์</span>
              </div>
            ) : null}
            <StatusList items={orderStatus.items} labels={STATUS_LABEL} />
            <button
              type="button"
              className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-sky-700"
              onClick={() => {
                localStorage.removeItem(`qs-order-${token}`);
                setOrderResult(null);
              }}
            >
              สั่งรอบใหม่ <ChevronRight className="h-4 w-4" />
            </button>
          </section>
        ) : null}

        {!orderResult ? (
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

      {!cartOpen ? <CartBar count={cartCount} total={cartTotal} onOpen={() => setCartOpen(true)} /> : null}
      <CartSheet
        open={cartOpen}
        title="ตรวจสอบออเดอร์"
        subtitle={`${cartCount} รายการสำหรับรับเองที่เคาน์เตอร์`}
        cart={cart}
        note={note}
        notePlaceholder="หมายเหตุรวม เช่น ขอช้อนเพิ่ม"
        submitLabel="ส่งออเดอร์"
        isSubmitting={orderMutation.isPending}
        extraFields={
          <div className="space-y-3">
            <div>
              <p className="mb-1 text-xs font-medium text-slate-500">ชื่อผู้สั่ง (ไม่บังคับ)</p>
              <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400" placeholder="เช่น คุณแจ้" value={customerName} onChange={(event) => setCustomerName(event.target.value)} />
            </div>
            <div>
              <p className="mb-1 text-xs font-medium text-slate-500">เบอร์โทร (ไม่บังคับ)</p>
              <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400" inputMode="tel" placeholder="สำหรับติดตามคิว" value={customerPhone} onChange={(event) => setCustomerPhone(event.target.value)} />
            </div>
          </div>
        }
        onClose={() => setCartOpen(false)}
        onRemove={removeFromCart}
        onQtyChange={updateQty}
        onItemNoteChange={updateItemNote}
        onNoteChange={setNote}
        onSubmit={() => orderMutation.mutate()}
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
