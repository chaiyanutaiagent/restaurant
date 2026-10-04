import { useMutation, useQuery } from "@tanstack/react-query";
import { ImageOff, Minus, Plus, Search, ShoppingCart } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { takeawayPublicApi, type TakeawayCatalogRow } from "@/lib/takeawayApi";

type CartLine = { row: TakeawayCatalogRow; quantity: number };

function money(value: number): string {
  return new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(value);
}

export default function TakeawayPublicOrderPage(): JSX.Element {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [cart, setCart] = useState<CartLine[]>([]);
  const [customerName, setCustomerName] = useState("");
  const [idempotencyKey] = useState(() => `public-order-${crypto.randomUUID()}`);
  const menuQuery = useQuery({
    queryKey: ["takeaway", "public-menu", token],
    queryFn: async () => (await takeawayPublicApi.orderingMenu(token)).data.data,
    enabled: Boolean(token),
    retry: 1,
  });
  const orderMutation = useMutation({
    mutationFn: () => {
      if (!menuQuery.data?.writes_enabled) throw new Error("ร้านยังไม่เปิดรับออเดอร์ออนไลน์");
      return takeawayPublicApi.createOrder(token, {
        idempotency_key: idempotencyKey,
        customer_name: customerName || null,
        items: cart.map((line) => ({ catalog_item_id: line.row.item.id, quantity: String(line.quantity) })),
      });
    },
    onSuccess: (response) => {
      if (response.data.data.pickup_token) {
        navigate(`/takeaway/pickup-status/${encodeURIComponent(response.data.data.pickup_token)}`);
      }
    },
  });
  const adjust = (row: TakeawayCatalogRow, delta: number): void => setCart((current) => {
    if (!row.is_available && delta > 0) return current;
    const found = current.find((line) => line.row.item.id === row.item.id);
    if (!found && delta > 0) return [...current, { row, quantity: 1 }];
    return current.map((line) => line.row.item.id === row.item.id ? { ...line, quantity: line.quantity + delta } : line).filter((line) => line.quantity > 0);
  });
  const items = (menuQuery.data?.items ?? []).filter((row) => {
    if (categoryId && row.item.category_id !== categoryId) return false;
    const needle = search.trim().toLowerCase();
    if (!needle) return true;
    return `${row.item.name} ${row.item.description ?? ""}`.toLowerCase().includes(needle);
  });
  const total = useMemo(() => cart.reduce((sum, line) => sum + Number(line.row.effective_price) * line.quantity * (1 + Number(line.row.item.tax_rate ?? 0) / 100), 0), [cart]);

  if (menuQuery.isError) return <main className="grid min-h-screen place-items-center bg-slate-950 p-6 text-center text-white"><div><p className="text-3xl font-black">QR หมดอายุหรือร้านยังไม่เปิดรับออเดอร์</p><p className="mt-3 text-slate-400">กรุณาติดต่อพนักงานหน้าร้าน</p></div></main>;
  return <main className="min-h-screen bg-slate-100 pb-36">
    <header className="sticky top-0 z-10 bg-slate-950 px-5 py-4 text-white shadow-xl"><p className="text-xs font-black uppercase tracking-[0.25em] text-emerald-400">Foodchainservice Take away</p><h1 className="mt-1 text-xl font-black">{menuQuery.data?.branch_name ?? "กำลังโหลดเมนู…"}</h1></header>
    <div className="mx-auto max-w-5xl p-4">
      {!menuQuery.isLoading && !menuQuery.data?.writes_enabled ? <div className="mb-3 rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm font-bold text-amber-950">กำลังเปิดให้ดูเมนูเพื่อทดสอบหน้าจอ ร้านยังไม่เปิดรับออเดอร์จริง</div> : null}
      <label className="relative mt-2 block"><Search className="pointer-events-none absolute left-4 top-3.5 h-5 w-5 text-slate-400" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="ค้นหาสินค้าหรือรายละเอียด" className="h-12 w-full rounded-2xl border border-slate-200 bg-white pl-12 pr-4 text-sm shadow-sm outline-none focus:border-emerald-500" /></label>
      <div className="flex gap-2 overflow-x-auto py-2"><button onClick={() => setCategoryId(null)} className={`min-w-fit rounded-full px-4 py-2 text-sm font-bold ${categoryId === null ? "bg-emerald-500" : "bg-white"}`}>ทั้งหมด</button>{(menuQuery.data?.categories ?? []).map((category) => <button key={category.id} onClick={() => setCategoryId(category.id)} className={`min-w-fit rounded-full px-4 py-2 text-sm font-bold ${categoryId === category.id ? "bg-emerald-500" : "bg-white"}`}>{String(category.name)}</button>)}</div>
      <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-3">{items.map((row) => <button key={row.item.id} disabled={!menuQuery.data?.writes_enabled || !row.is_available} onClick={() => adjust(row, 1)} className="overflow-hidden rounded-2xl bg-white text-left shadow-sm disabled:cursor-not-allowed disabled:opacity-65"><div className="relative aspect-[4/3] bg-slate-200">{row.item.image_url ? <img src={row.item.image_url} alt={row.item.name} className="h-full w-full object-cover" /> : <div className="grid h-full place-items-center text-slate-400"><ImageOff className="h-8 w-8" /></div>}<span className={`absolute right-2 top-2 rounded-full px-2 py-1 text-[11px] font-black ${row.is_available ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-700"}`}>{row.is_available ? "พร้อมขาย" : "หมดชั่วคราว"}</span></div><div className="p-4"><p className="line-clamp-2 font-black">{row.item.name}</p>{row.item.description ? <p className="mt-1 line-clamp-2 text-xs text-slate-500">{row.item.description}</p> : null}<p className="mt-4 text-lg font-black text-emerald-700">{money(Number(row.effective_price))}</p></div></button>)}</div>
      {!menuQuery.isLoading && items.length === 0 ? <div className="mt-3 rounded-2xl border border-dashed bg-white p-10 text-center text-slate-500">ไม่พบสินค้าในหมวดหรือคำค้นหานี้</div> : null}
    </div>
    {cart.length ? <section className="fixed inset-x-0 bottom-0 z-20 border-t bg-white p-4 shadow-2xl"><div className="mx-auto flex max-w-5xl flex-wrap items-center gap-3"><div className="flex flex-1 gap-2 overflow-x-auto">{cart.map((line) => <div key={line.row.item.id} className="flex min-w-fit items-center gap-2 rounded-xl bg-slate-100 px-3 py-2"><button onClick={() => adjust(line.row, -1)}><Minus className="h-4 w-4" /></button><span className="text-sm font-bold">{line.row.item.name} × {line.quantity}</span><button onClick={() => adjust(line.row, 1)}><Plus className="h-4 w-4" /></button></div>)}</div><input value={customerName} onChange={(event) => setCustomerName(event.target.value)} placeholder="ชื่อลูกค้า (ถ้ามี)" className="rounded-xl border px-3 py-3" /><button disabled={!menuQuery.data?.writes_enabled || orderMutation.isPending} onClick={() => orderMutation.mutate()} className="flex items-center gap-2 rounded-xl bg-emerald-500 px-5 py-3 font-black disabled:opacity-40"><ShoppingCart className="h-5 w-5" />{menuQuery.data?.writes_enabled ? `สั่ง ${money(total)}` : "ยังไม่เปิดรับออเดอร์"}</button></div>{orderMutation.isError ? <p className="mx-auto mt-2 max-w-5xl text-sm font-bold text-rose-600">ส่งออเดอร์ไม่สำเร็จ กรุณาตรวจรายการหรือติดต่อพนักงาน</p> : null}</section> : null}
  </main>;
}
