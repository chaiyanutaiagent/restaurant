import { useMutation, useQuery } from "@tanstack/react-query";
import { Minus, Plus, ShoppingCart } from "lucide-react";
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
    mutationFn: () => takeawayPublicApi.createOrder(token, {
      idempotency_key: idempotencyKey,
      customer_name: customerName || null,
      items: cart.map((line) => ({ catalog_item_id: line.row.item.id, quantity: String(line.quantity) })),
    }),
    onSuccess: (response) => {
      if (response.data.data.pickup_token) {
        navigate(`/takeaway/pickup-status/${encodeURIComponent(response.data.data.pickup_token)}`);
      }
    },
  });
  const adjust = (row: TakeawayCatalogRow, delta: number): void => setCart((current) => {
    const found = current.find((line) => line.row.item.id === row.item.id);
    if (!found && delta > 0) return [...current, { row, quantity: 1 }];
    return current.map((line) => line.row.item.id === row.item.id ? { ...line, quantity: line.quantity + delta } : line).filter((line) => line.quantity > 0);
  });
  const items = (menuQuery.data?.items ?? []).filter((row) => row.is_available && (!categoryId || row.item.category_id === categoryId));
  const total = useMemo(() => cart.reduce((sum, line) => sum + Number(line.row.effective_price) * line.quantity * (1 + Number(line.row.item.tax_rate ?? 0) / 100), 0), [cart]);

  if (menuQuery.isError) return <main className="grid min-h-screen place-items-center bg-slate-950 p-6 text-center text-white"><div><p className="text-3xl font-black">QR หมดอายุหรือร้านยังไม่เปิดรับออเดอร์</p><p className="mt-3 text-slate-400">กรุณาติดต่อพนักงานหน้าร้าน</p></div></main>;
  return <main className="min-h-screen bg-slate-100 pb-36">
    <header className="sticky top-0 z-10 bg-slate-950 px-5 py-4 text-white shadow-xl"><p className="text-xs font-black uppercase tracking-[0.25em] text-emerald-400">Foodchainservice Take away</p><h1 className="mt-1 text-xl font-black">{menuQuery.data?.branch_name ?? "กำลังโหลดเมนู…"}</h1></header>
    <div className="mx-auto max-w-5xl p-4">
      <div className="flex gap-2 overflow-x-auto py-2"><button onClick={() => setCategoryId(null)} className={`min-w-fit rounded-full px-4 py-2 text-sm font-bold ${categoryId === null ? "bg-emerald-500" : "bg-white"}`}>ทั้งหมด</button>{(menuQuery.data?.categories ?? []).map((category) => <button key={category.id} onClick={() => setCategoryId(category.id)} className={`min-w-fit rounded-full px-4 py-2 text-sm font-bold ${categoryId === category.id ? "bg-emerald-500" : "bg-white"}`}>{String(category.name)}</button>)}</div>
      <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-3">{items.map((row) => <button key={row.item.id} onClick={() => adjust(row, 1)} className="min-h-36 rounded-2xl bg-white p-4 text-left shadow-sm"><p className="font-black">{row.item.name}</p><p className="mt-8 text-lg font-black text-emerald-700">{money(Number(row.effective_price))}</p></button>)}</div>
    </div>
    {cart.length ? <section className="fixed inset-x-0 bottom-0 z-20 border-t bg-white p-4 shadow-2xl"><div className="mx-auto flex max-w-5xl flex-wrap items-center gap-3"><div className="flex flex-1 gap-2 overflow-x-auto">{cart.map((line) => <div key={line.row.item.id} className="flex min-w-fit items-center gap-2 rounded-xl bg-slate-100 px-3 py-2"><button onClick={() => adjust(line.row, -1)}><Minus className="h-4 w-4" /></button><span className="text-sm font-bold">{line.row.item.name} × {line.quantity}</span><button onClick={() => adjust(line.row, 1)}><Plus className="h-4 w-4" /></button></div>)}</div><input value={customerName} onChange={(event) => setCustomerName(event.target.value)} placeholder="ชื่อลูกค้า (ถ้ามี)" className="rounded-xl border px-3 py-3" /><button disabled={orderMutation.isPending} onClick={() => orderMutation.mutate()} className="flex items-center gap-2 rounded-xl bg-emerald-500 px-5 py-3 font-black"><ShoppingCart className="h-5 w-5" />สั่ง {money(total)}</button></div>{orderMutation.isError ? <p className="mx-auto mt-2 max-w-5xl text-sm font-bold text-rose-600">ส่งออเดอร์ไม่สำเร็จ กรุณาตรวจรายการหรือติดต่อพนักงาน</p> : null}</section> : null}
  </main>;
}
