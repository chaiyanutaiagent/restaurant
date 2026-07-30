import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { AxiosError } from "axios";
import { AlertTriangle, ChefHat, Clock, Phone, Plus, ReceiptText, Trash2, User, UtensilsCrossed } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/use-toast";
import { authApi } from "@/lib/api";
import { formatThaiCurrency } from "@/lib/cartUtils";

type SessionItem = {
  id: string; product_name: string; qty: number;
  unit_price: number; special_request: string | null; status: string;
};
type SessionOrder = { id: string; order_number?: string; status: string; source: string; items: SessionItem[] };
type SessionData = {
  id: string; status: string; queue_number: number | null; table_name: string | null;
  customer_name: string | null; customer_phone: string | null;
  opened_at: string; closed_at: string | null; orders: SessionOrder[];
  pending_count?: number; cooking_count?: number; ready_count?: number; served_count?: number; qr_pending_count?: number;
};

type MenuProduct = { id: string; name: string; selling_price: number; category_name: string | null };
type ApiErrorBody = { detail?: string; error?: string };
type CancelTarget =
  | { type: "order"; id: string; label: string }
  | { type: "item"; id: string; label: string };

const STATUS_BADGE: Record<string, string> = {
  pending: "bg-amber-100 text-amber-700",
  cooking: "bg-blue-100 text-blue-700",
  done:    "bg-emerald-100 text-emerald-700",
  served:  "bg-slate-100 text-slate-600",
  cancelled: "bg-red-100 text-red-600",
};
const STATUS_LABEL: Record<string, string> = {
  pending: "รอทำ", cooking: "กำลังทำ", done: "เสร็จแล้ว", served: "เสิร์ฟแล้ว", cancelled: "ยกเลิก",
};
const SESSION_LABEL: Record<string, string> = {
  open: "กำลังสั่ง",
  bill_requested: "เรียกบิลแล้ว",
  closed: "ปิดแล้ว",
};
const SOURCE_LABEL: Record<string, string> = {
  qr_self: "ลูกค้าสั่งเอง (QR)",
  staff: "Staff สั่ง",
  kiosk: "รับเอง / กลับบ้าน",
};
const STATUS_GROUPS = ["pending", "cooking", "done", "served"] as const;

function getErrorMessage(error: unknown): string {
  const axiosError = error as AxiosError<ApiErrorBody>;
  return axiosError.response?.data?.detail ?? axiosError.response?.data?.error ?? (error instanceof Error ? error.message : "ไม่สามารถทำรายการได้");
}

export default function SessionDetailPage(): JSX.Element {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [addOrderOpen, setAddOrderOpen] = useState(false);
  const [orderCart, setOrderCart] = useState<{ product: MenuProduct; qty: number; special_request: string }[]>([]);
  const [menuSearch, setMenuSearch] = useState("");
  const [cancelTarget, setCancelTarget] = useState<CancelTarget | null>(null);
  const [cancelReason, setCancelReason] = useState("");

  const sessionQuery = useQuery({
    queryKey: ["session-detail", sessionId],
    queryFn: async () =>
      (await authApi.get(`/restaurant/sessions/${sessionId}/detail`)).data.data as SessionData,
    enabled: Boolean(sessionId),
    refetchInterval: 10_000,
  });

  const menuQuery = useQuery({
    queryKey: ["menu-products"],
    queryFn: async () =>
      (await authApi.get("/products?product_type=menu_item&is_active=true&limit=200")).data.data as MenuProduct[],
    enabled: addOrderOpen,
  });

  const addOrderMutation = useMutation({
    mutationFn: async () => {
      await authApi.post(`/restaurant/sessions/${sessionId}/orders`, {
        items: orderCart.map((c) => ({
          product_id: c.product.id,
          qty: c.qty,
          special_request: c.special_request || null,
        })),
        note: null,
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["session-detail"] });
      toast({ title: "เพิ่มออเดอร์แล้ว" });
      setAddOrderOpen(false);
      setOrderCart([]);
    },
    onError: (error) => toast({ title: "เพิ่มออเดอร์ไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" }),
  });

  const cancelMutation = useMutation({
    mutationFn: async () => {
      if (!cancelTarget) {
        throw new Error("ไม่พบรายการที่ต้องการยกเลิก");
      }
      const reason = cancelReason.trim();
      if (!reason) {
        throw new Error("กรุณาระบุเหตุผลการยกเลิก");
      }
      const url = cancelTarget.type === "order"
        ? `/restaurant/orders/${cancelTarget.id}/cancel`
        : `/restaurant/order-items/${cancelTarget.id}/cancel`;
      await authApi.post(url, { reason });
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["session-detail"] }),
        queryClient.invalidateQueries({ queryKey: ["kitchen-tickets"] }),
        queryClient.invalidateQueries({ queryKey: ["pickup-queue"] }),
      ]);
      toast({ title: "ยกเลิกแล้ว" });
      setCancelTarget(null);
      setCancelReason("");
    },
    onError: (error) => {
      toast({ title: "ยกเลิกไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
    },
  });

  const itemStatusMutation = useMutation({
    mutationFn: async ({ itemId, status }: { itemId: string; status: string }) => {
      await authApi.patch(`/restaurant/order-items/${itemId}/status`, { status });
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["session-detail"] }),
        queryClient.invalidateQueries({ queryKey: ["kitchen-tickets"] }),
        queryClient.invalidateQueries({ queryKey: ["pickup-queue"] }),
      ]);
      toast({ title: "อัปเดตสถานะแล้ว" });
    },
    onError: (error) => {
      toast({ title: "อัปเดตสถานะไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
    },
  });

  const session = sessionQuery.data;
  if (!session && !sessionQuery.isLoading) {
    return <div className="p-8 text-center text-slate-400">ไม่พบ session</div>;
  }

  const allItems = session?.orders.flatMap((o) =>
    o.status !== "cancelled" ? o.items.filter((item) => item.status !== "cancelled") : []
  ) ?? [];
  const itemsWithOrder = session?.orders.flatMap((order) =>
    order.status !== "cancelled"
      ? order.items
          .filter((item) => item.status !== "cancelled")
          .map((item) => ({ ...item, order_id: order.id, order_number: order.order_number, source: order.source }))
      : []
  ) ?? [];
  const groupedItems = STATUS_GROUPS.reduce<Record<string, typeof itemsWithOrder>>((acc, status) => {
    acc[status] = itemsWithOrder.filter((item) => item.status === status);
    return acc;
  }, {});
  const totalAmount = allItems.reduce((s, i) => s + i.unit_price * i.qty, 0);
  const pendingCount = allItems.filter((item) => item.status === "pending").length;
  const cookingCount = allItems.filter((item) => item.status === "cooking").length;
  const readyCount = allItems.filter((item) => item.status === "done").length;
  const servedCount = allItems.filter((item) => item.status === "served").length;
  const products = (menuQuery.data ?? []).filter((p) =>
    !menuSearch || p.name.toLowerCase().includes(menuSearch.toLowerCase())
  );

  function addToCart(product: MenuProduct): void {
    setOrderCart((prev) => {
      const ex = prev.find((c) => c.product.id === product.id);
      return ex
        ? prev.map((c) => c.product.id === product.id ? { ...c, qty: c.qty + 1 } : c)
        : [...prev, { product, qty: 1, special_request: "" }];
    });
  }

  return (
    <div>
      <PageHeader
        title={
          session
            ? [
                session.table_name ? `โต๊ะ ${session.table_name}` : null,
                session.queue_number ? `คิว ${String(session.queue_number).padStart(3, "0")}` : null,
              ].filter(Boolean).join(" — ") || "Session"
            : "..."
        }
        subtitle={session ? `${SESSION_LABEL[session.status] ?? session.status}${session.customer_name ? ` · ${session.customer_name}` : ""}` : undefined}
        actions={
          session?.status !== "closed" ? (
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setAddOrderOpen(true)}>
                <Plus className="mr-1 h-4 w-4" /> สั่งเพิ่ม (Staff)
              </Button>
              <Button
                className="bg-emerald-600 hover:bg-emerald-700"
                onClick={() => navigate(`/restaurant/session/${sessionId}/checkout`)}
              >
                <ReceiptText className="mr-1 h-4 w-4" /> รวมบิล
              </Button>
            </div>
          ) : undefined
        }
      />

      <div className="p-6 space-y-6">
        {/* Session meta */}
        {session && (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
            {[
              { label: "สถานะ", value: SESSION_LABEL[session.status] ?? session.status },
              { label: "เปิดเมื่อ", value: new Date(session.opened_at).toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" }) },
              { label: "รายการ", value: `${allItems.length} รายการ` },
              { label: "ยอดรวม", value: formatThaiCurrency(totalAmount) },
              { label: "รอ/ทำ", value: `${pendingCount + cookingCount}` },
              { label: "พร้อม/เสิร์ฟ", value: `${readyCount + servedCount}` },
            ].map((s) => (
              <div key={s.label} className="rounded-2xl border border-slate-200 bg-white p-4">
                <p className="text-xs text-slate-400">{s.label}</p>
                <p className="mt-1 font-bold text-slate-900">{s.value}</p>
              </div>
            ))}
          </div>
        )}

        {session && (session.qr_pending_count ?? 0) > 0 ? (
          <div className="flex items-center gap-3 rounded-2xl border border-orange-200 bg-orange-50 px-5 py-4 text-orange-800">
            <AlertTriangle className="h-5 w-5" />
            <div>
              <p className="font-bold">มีออเดอร์ใหม่จาก QR {session.qr_pending_count} รายการ</p>
              <p className="text-sm">ตรวจรายการและให้ครัวเริ่มทำจาก Kitchen Display หรือเปลี่ยนสถานะที่รายการนี้</p>
            </div>
          </div>
        ) : null}

        {session && (session.customer_name || session.customer_phone) && (
          <div className="flex flex-wrap gap-3 rounded-2xl border border-slate-200 bg-white px-5 py-4 text-sm text-slate-600">
            {session.customer_name ? <span className="inline-flex items-center gap-2"><User className="h-4 w-4" /> {session.customer_name}</span> : null}
            {session.customer_phone ? <span className="inline-flex items-center gap-2"><Phone className="h-4 w-4" /> {session.customer_phone}</span> : null}
          </div>
        )}

        {allItems.length > 0 ? (
          <div className="grid gap-3 xl:grid-cols-4">
            {STATUS_GROUPS.map((status) => (
              <section key={status} className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
                <div className={`flex items-center justify-between border-b border-slate-100 px-4 py-3 ${STATUS_BADGE[status]}`}>
                  <span className="font-bold">{STATUS_LABEL[status]}</span>
                  <span className="rounded-full bg-white/70 px-2 py-0.5 text-xs font-bold">
                    {groupedItems[status].reduce((sum, item) => sum + item.qty, 0)}
                  </span>
                </div>
                <div className="space-y-2 p-3">
                  {groupedItems[status].length === 0 ? (
                    <p className="py-6 text-center text-sm text-slate-400">ไม่มีรายการ</p>
                  ) : null}
                  {groupedItems[status].map((item) => (
                    <div key={item.id} className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="font-semibold text-slate-900">{item.product_name}</p>
                          <p className="mt-0.5 text-xs text-slate-500">
                            {SOURCE_LABEL[item.source] ?? item.source}{item.order_number ? ` · ${item.order_number}` : ""}
                          </p>
                        </div>
                        <span className="shrink-0 text-lg font-black text-slate-950">x{item.qty}</span>
                      </div>
                      {item.special_request ? (
                        <p className="mt-2 rounded-lg bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-800">{item.special_request}</p>
                      ) : null}
                      <div className="mt-3 flex flex-wrap gap-2">
                        {session?.status !== "closed" && item.status === "done" ? (
                          <button
                            type="button"
                            onClick={() => itemStatusMutation.mutate({ itemId: item.id, status: "served" })}
                            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-700"
                          >
                            เสิร์ฟแล้ว
                          </button>
                        ) : null}
                        {session?.status !== "closed" && item.status !== "served" ? (
                          <button
                            type="button"
                            onClick={() => setCancelTarget({ type: "item", id: item.id, label: item.product_name })}
                            className="rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-bold text-red-600 hover:bg-red-50"
                          >
                            ยกเลิก
                          </button>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </div>
        ) : null}

        {/* Orders */}
        {session?.orders.map((order) => (
          <div key={order.id} className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
            <div className="border-b border-slate-100 bg-slate-50 px-5 py-3 flex items-center gap-3">
              <ChefHat className="h-4 w-4 text-slate-400" />
              <span className="text-sm font-medium text-slate-600">
                {SOURCE_LABEL[order.source] ?? order.source}
              </span>
              {order.source === "qr_self" && order.items.some((item) => item.status === "pending") ? (
                <span className="rounded-full bg-orange-500 px-2 py-0.5 text-xs font-bold text-white">QR ใหม่</span>
              ) : null}
              {order.order_number ? <span className="text-xs text-slate-400">{order.order_number}</span> : null}
              <span className={`ml-auto rounded-full px-2 py-0.5 text-xs ${order.status === "cancelled" ? "bg-red-100 text-red-600" : "bg-slate-100 text-slate-500"}`}>
                {order.status}
              </span>
              {session.status !== "closed" && order.status !== "cancelled" && order.items.some((item) => item.status !== "served" && item.status !== "cancelled") ? (
                <button
                  type="button"
                  onClick={() => setCancelTarget({ type: "order", id: order.id, label: order.order_number ?? "ออเดอร์นี้" })}
                  className="rounded-lg border border-red-200 bg-white px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50"
                >
                  ยกเลิกออเดอร์
                </button>
              ) : null}
            </div>
            <table className="w-full text-sm">
              <tbody className="divide-y divide-slate-100">
                {order.items.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50">
                    <td className="px-5 py-3">
                      <p className="font-medium text-slate-900">{item.product_name}</p>
                      {item.special_request && (
                        <p className="text-xs text-amber-600">{item.special_request}</p>
                      )}
                    </td>
                    <td className="px-5 py-3 text-center text-slate-600">×{item.qty}</td>
                    <td className="px-5 py-3 text-right font-medium text-slate-900">
                      {formatThaiCurrency(item.unit_price * item.qty)}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <span className={`rounded-full px-2 py-0.5 text-xs ${STATUS_BADGE[item.status] ?? "bg-slate-100 text-slate-500"}`}>
                        {STATUS_LABEL[item.status] ?? item.status}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-right">
                      {session.status !== "closed" && item.status === "done" && order.status !== "cancelled" ? (
                        <button
                          type="button"
                          onClick={() => itemStatusMutation.mutate({ itemId: item.id, status: "served" })}
                          className="mr-2 rounded-lg border border-emerald-200 px-2 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-50"
                        >
                          เสิร์ฟแล้ว
                        </button>
                      ) : null}
                      {session.status !== "closed" && item.status !== "served" && item.status !== "cancelled" && order.status !== "cancelled" ? (
                        <button
                          type="button"
                          onClick={() => setCancelTarget({ type: "item", id: item.id, label: item.product_name })}
                          className="rounded-lg border border-red-200 px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50"
                        >
                          ยกเลิก
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}

        {(session?.orders.length ?? 0) === 0 && !sessionQuery.isLoading && (
          <div className="rounded-2xl border border-dashed border-slate-200 py-12 text-center text-slate-400">
            <UtensilsCrossed className="mx-auto mb-2 h-8 w-8" />
            ยังไม่มีรายการอาหาร
          </div>
        )}

        {/* Total */}
        {allItems.length > 0 && (
          <div className="rounded-2xl bg-slate-950 px-5 py-4 flex justify-between items-center text-white">
            <span className="font-semibold text-slate-200">ยอดรวมทั้งหมด</span>
            <span className="text-2xl font-black">{formatThaiCurrency(totalAmount)}</span>
          </div>
        )}
      </div>

      {/* Add Order Sheet */}
      {addOrderOpen && (
        <div className="fixed inset-0 z-40 flex flex-col bg-white">
          <div className="flex items-center justify-between border-b px-5 py-4">
            <h2 className="text-lg font-bold">สั่งเพิ่ม (Staff)</h2>
            <Button variant="ghost" onClick={() => { setAddOrderOpen(false); setOrderCart([]); }}>
              ปิด
            </Button>
          </div>
          <div className="flex flex-1 overflow-hidden">
            {/* Product list */}
            <div className="flex-1 overflow-y-auto p-4 space-y-2 border-r">
              <input
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm mb-3"
                placeholder="ค้นหาเมนู..."
                value={menuSearch}
                onChange={(e) => setMenuSearch(e.target.value)}
                autoFocus
              />
              {products.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => addToCart(p)}
                  className="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white p-3 text-left hover:border-slate-400 hover:bg-slate-50"
                >
                  <div>
                    <p className="font-medium text-slate-900">{p.name}</p>
                    {p.category_name && <p className="text-xs text-slate-400">{p.category_name}</p>}
                  </div>
                  <span className="font-bold text-emerald-700">{formatThaiCurrency(p.selling_price)}</span>
                </button>
              ))}
            </div>
            {/* Cart */}
            <div className="flex w-72 flex-col border-l">
              <div className="flex-1 overflow-y-auto p-4 space-y-2">
                {orderCart.length === 0 && (
                  <p className="text-center text-slate-400 py-8 text-sm">เลือกเมนูด้านซ้าย</p>
                )}
                {orderCart.map((c) => (
                  <div key={c.product.id} className="rounded-xl border border-slate-200 p-3">
                    <div className="flex items-center justify-between">
                      <p className="font-medium text-slate-900 text-sm">{c.product.name}</p>
                      <button type="button" onClick={() => setOrderCart((p) => p.filter((x) => x.product.id !== c.product.id))}>
                        <Trash2 className="h-4 w-4 text-red-400" />
                      </button>
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <button type="button" onClick={() => setOrderCart((p) => p.map((x) => x.product.id === c.product.id ? { ...x, qty: Math.max(1, x.qty - 1) } : x))}
                        className="h-7 w-7 rounded-full border text-slate-600">−</button>
                      <span className="w-6 text-center font-bold text-sm">{c.qty}</span>
                      <button type="button" onClick={() => setOrderCart((p) => p.map((x) => x.product.id === c.product.id ? { ...x, qty: x.qty + 1 } : x))}
                        className="h-7 w-7 rounded-full bg-slate-950 text-white">+</button>
                      <span className="ml-auto text-sm font-semibold text-emerald-700">{formatThaiCurrency(c.product.selling_price * c.qty)}</span>
                    </div>
                    <input className="mt-2 w-full rounded-lg border border-slate-200 px-2 py-1 text-xs"
                      placeholder="หมายเหตุ" value={c.special_request}
                      onChange={(e) => setOrderCart((p) => p.map((x) => x.product.id === c.product.id ? { ...x, special_request: e.target.value } : x))} />
                  </div>
                ))}
              </div>
              <div className="border-t p-4">
                <div className="mb-3 flex justify-between font-bold">
                  <span>รวม</span>
                  <span className="text-emerald-700">{formatThaiCurrency(orderCart.reduce((s, c) => s + c.product.selling_price * c.qty, 0))}</span>
                </div>
                <Button
                  className="w-full bg-slate-950 hover:bg-slate-800"
                  disabled={orderCart.length === 0 || addOrderMutation.isPending}
                  onClick={() => addOrderMutation.mutate()}
                >
                  {addOrderMutation.isPending ? "กำลังส่ง..." : "ส่งออเดอร์ไปครัว"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      <Dialog open={Boolean(cancelTarget)} onOpenChange={(open) => { if (!open) { setCancelTarget(null); setCancelReason(""); } }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>ยกเลิก{cancelTarget?.type === "order" ? "ออเดอร์" : "รายการ"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="rounded-xl border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-700">
              {cancelTarget?.label}
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700">เหตุผลการยกเลิก</label>
              <textarea
                className="mt-1 min-h-[96px] w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder="เช่น ลูกค้าเปลี่ยนใจ, สั่งผิด, ของหมด"
                value={cancelReason}
                onChange={(event) => setCancelReason(event.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setCancelTarget(null); setCancelReason(""); }}>ยกเลิก</Button>
            <Button variant="destructive" disabled={!cancelReason.trim() || cancelMutation.isPending} onClick={() => cancelMutation.mutate()}>
              {cancelMutation.isPending ? "กำลังยกเลิก..." : "ยืนยันยกเลิก"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
