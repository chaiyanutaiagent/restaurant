import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { AxiosError } from "axios";
import { AlertTriangle, ChefHat, Clock, Phone, Plus, ReceiptText, ShieldCheck, Trash2, User, UtensilsCrossed } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import ManagerApprovalDialog from "@/components/approval/ManagerApprovalDialog";
import { useToast } from "@/components/ui/use-toast";
import { authApi } from "@/lib/api";
import { formatThaiCurrency } from "@/lib/cartUtils";

type SessionItem = {
  id: string; product_id: string; product_name: string; qty: number;
  unit_price: number; special_request: string | null; status: string; row_version: number;
};
type SessionOrder = { id: string; order_number?: string; status: string; source: string; row_version: number; items: SessionItem[] };
type SessionData = {
  id: string; status: string; queue_number: number | null; table_name: string | null;
  customer_name: string | null; customer_phone: string | null;
  opened_at: string; closed_at: string | null; orders: SessionOrder[];
  pending_count?: number; cooking_count?: number; ready_count?: number; served_count?: number; qr_pending_count?: number;
};

type MenuProduct = { id: string; name: string; selling_price: number; category_name: string | null };
type ApiErrorDetail = { code?: string; message?: string; blockers?: string[]; current_order_version?: number; current_item_version?: number };
type ApiErrorBody = { detail?: string | ApiErrorDetail; error?: string };
type CancelTarget =
  | { type: "order"; id: string; label: string; orderVersion: number; idempotencyKey: string }
  | { type: "item"; id: string; label: string; orderVersion: number; itemVersion: number; idempotencyKey: string };

type CancellationReasonCode = "customer_changed_mind" | "wrong_item" | "duplicate_order" | "out_of_stock" | "quality_failed" | "kitchen_error" | "other";
type CancellationPreview = {
  stage_before: "pending" | "cooking" | "done";
  approval_required: boolean;
  approval_action: "fb.order.cancel_after_kitchen" | null;
  waste_disposition: "none" | "full";
  waste_ready: boolean;
  blockers: string[];
  bill_impact: { amount_removed: string };
  affected_items: { id: string; product_name: string; qty: number; status: string; station: string | null }[];
  waste_lines: { product_id: string; product_name: string; quantity: string; unit: string | null }[];
};
type CancellationRecord = {
  id: string;
  target_type: "item" | "order";
  stage_before: string;
  reason_code: CancellationReasonCode;
  reason_note: string | null;
  waste_disposition: "none" | "full";
  bill_impact: { amount_removed: string };
  created_at: string;
};

const CANCELLATION_REASONS: { code: CancellationReasonCode; label: string }[] = [
  { code: "customer_changed_mind", label: "ลูกค้าเปลี่ยนใจ" },
  { code: "wrong_item", label: "สั่งผิดรายการ" },
  { code: "duplicate_order", label: "ออเดอร์ซ้ำ" },
  { code: "out_of_stock", label: "วัตถุดิบหมด" },
  { code: "quality_failed", label: "คุณภาพไม่ผ่าน" },
  { code: "kitchen_error", label: "ครัวทำผิด" },
  { code: "other", label: "อื่น ๆ" },
];

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
  const detail = axiosError.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.message) return detail.blockers?.length ? `${detail.message}: ${detail.blockers.join(", ")}` : detail.message;
  return axiosError.response?.data?.error ?? (error instanceof Error ? error.message : "ไม่สามารถทำรายการได้");
}

function requestKey(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
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
  const [cancelReasonCode, setCancelReasonCode] = useState<CancellationReasonCode>("customer_changed_mind");
  const [cancelReasonNote, setCancelReasonNote] = useState("");
  const [approvalOpen, setApprovalOpen] = useState(false);
  const [reopenTarget, setReopenTarget] = useState<CancellationRecord | null>(null);
  const [reopenReason, setReopenReason] = useState("ลูกค้าขอเปิดรายการใหม่");
  const [reopenKey, setReopenKey] = useState("");

  function cancellationPayload(approvalToken?: string): Record<string, unknown> {
    if (!cancelTarget) throw new Error("ไม่พบรายการที่ต้องการยกเลิก");
    return {
      target_type: cancelTarget.type,
      target_id: cancelTarget.id,
      expected_order_version: cancelTarget.orderVersion,
      expected_item_version: cancelTarget.type === "item" ? cancelTarget.itemVersion : undefined,
      reason_code: cancelReasonCode,
      reason_note: cancelReasonNote.trim() || undefined,
      idempotency_key: cancelTarget.idempotencyKey,
      approval_token: approvalToken,
    };
  }

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

  const cancellationPreviewQuery = useQuery({
    queryKey: ["restaurant-cancellation-preview", cancelTarget?.id, cancelTarget?.orderVersion, cancelTarget?.type === "item" ? cancelTarget.itemVersion : null],
    queryFn: async () => (
      await authApi.post("/restaurant/cancellations/preview", cancellationPayload())
    ).data.data as CancellationPreview,
    enabled: Boolean(cancelTarget) && navigator.onLine,
    retry: false,
  });

  const cancellationHistoryQuery = useQuery({
    queryKey: ["restaurant-cancellations", sessionId],
    queryFn: async () => (
      await authApi.get(`/restaurant/cancellations?session_id=${sessionId}&limit=50`)
    ).data.data as CancellationRecord[],
    enabled: Boolean(sessionId),
    retry: false,
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
    mutationFn: async (approvalToken?: string) => {
      await authApi.post("/restaurant/cancellations", cancellationPayload(approvalToken));
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["session-detail"] }),
        queryClient.invalidateQueries({ queryKey: ["restaurant-cancellations"] }),
        queryClient.invalidateQueries({ queryKey: ["kitchen-tickets"] }),
        queryClient.invalidateQueries({ queryKey: ["pickup-queue"] }),
      ]);
      toast({ title: "ยกเลิกแล้ว" });
      setCancelTarget(null);
      setCancelReasonCode("customer_changed_mind");
      setCancelReasonNote("");
      setApprovalOpen(false);
    },
    onError: (error) => {
      toast({ title: "ยกเลิกไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
    },
  });

  const reopenMutation = useMutation({
    mutationFn: async (approvalToken: string) => {
      if (!reopenTarget) throw new Error("ไม่พบรายการยกเลิก");
      await authApi.post(`/restaurant/cancellations/${reopenTarget.id}/reopen`, {
        idempotency_key: reopenKey,
        reason: reopenReason.trim(),
        approval_token: approvalToken,
      });
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["session-detail"] }),
        queryClient.invalidateQueries({ queryKey: ["restaurant-cancellations"] }),
        queryClient.invalidateQueries({ queryKey: ["kitchen-tickets"] }),
      ]);
      toast({ title: "เปิดเป็นออเดอร์ใหม่แล้ว", description: "ระบบคำนวณราคาใหม่และส่ง ticket ใหม่ไปครัว" });
      setReopenTarget(null);
      setReopenKey("");
    },
    onError: (error) => toast({ title: "เปิดรายการใหม่ไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" }),
  });

  const itemStatusMutation = useMutation({
    mutationFn: async ({ itemId, status, expectedVersion }: { itemId: string; status: string; expectedVersion: number }) => {
      await authApi.patch(`/restaurant/order-items/${itemId}/status`, { status, expected_version: expectedVersion });
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
          .map((item) => ({
            ...item,
            order_id: order.id,
            order_number: order.order_number,
            order_version: order.row_version,
            source: order.source,
          }))
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
                            onClick={() => itemStatusMutation.mutate({ itemId: item.id, status: "served", expectedVersion: item.row_version })}
                            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-700"
                          >
                            เสิร์ฟแล้ว
                          </button>
                        ) : null}
                        {session?.status !== "closed" && item.status !== "served" ? (
                          <button
                            type="button"
                            onClick={() => setCancelTarget({
                              type: "item",
                              id: item.id,
                              label: item.product_name,
                              orderVersion: item.order_version,
                              itemVersion: item.row_version,
                              idempotencyKey: requestKey("cancel-item"),
                            })}
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
                  onClick={() => setCancelTarget({
                    type: "order",
                    id: order.id,
                    label: order.order_number ?? "ออเดอร์นี้",
                    orderVersion: order.row_version,
                    idempotencyKey: requestKey("cancel-order"),
                  })}
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
                          onClick={() => itemStatusMutation.mutate({ itemId: item.id, status: "served", expectedVersion: item.row_version })}
                          className="mr-2 rounded-lg border border-emerald-200 px-2 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-50"
                        >
                          เสิร์ฟแล้ว
                        </button>
                      ) : null}
                      {session.status !== "closed" && item.status !== "served" && item.status !== "cancelled" && order.status !== "cancelled" ? (
                        <button
                          type="button"
                          onClick={() => setCancelTarget({
                            type: "item",
                            id: item.id,
                            label: item.product_name,
                            orderVersion: order.row_version,
                            itemVersion: item.row_version,
                            idempotencyKey: requestKey("cancel-item"),
                          })}
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

        {(cancellationHistoryQuery.data?.length ?? 0) > 0 ? (
          <section className="rounded-2xl border border-slate-200 bg-white p-4" aria-labelledby="cancellation-history-title">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 id="cancellation-history-title" className="font-bold text-slate-950">ประวัติการยกเลิก</h2>
                <p className="text-sm text-slate-500">หลักฐานเดิมและ Waste จะไม่ถูกลบเมื่อเปิดเป็นออเดอร์ใหม่</p>
              </div>
              <span className="rounded-full bg-slate-100 px-3 py-1 text-sm font-bold text-slate-600">{cancellationHistoryQuery.data?.length}</span>
            </div>
            <div className="mt-3 grid gap-2 lg:grid-cols-2">
              {cancellationHistoryQuery.data?.map((record) => (
                <article key={record.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 p-3">
                  <div className="min-w-0 flex-1">
                    <p className="font-bold text-slate-900">
                      {CANCELLATION_REASONS.find((reason) => reason.code === record.reason_code)?.label ?? record.reason_code}
                    </p>
                    <p className="text-xs text-slate-500">
                      {STATUS_LABEL[record.stage_before] ?? record.stage_before} · ลดบิล {formatThaiCurrency(Number(record.bill_impact.amount_removed))}
                      {record.waste_disposition === "full" ? " · บันทึก Waste แล้ว" : " · ไม่เกิด Waste"}
                    </p>
                  </div>
                  {session?.status !== "closed" ? (
                    <button
                      type="button"
                      disabled={!navigator.onLine}
                      onClick={() => {
                        setReopenTarget(record);
                        setReopenReason("ลูกค้าขอเปิดรายการใหม่");
                        setReopenKey(requestKey("reopen-cancellation"));
                      }}
                      className="min-h-12 rounded-xl border border-blue-200 bg-blue-50 px-4 text-sm font-bold text-blue-800 hover:bg-blue-100 disabled:opacity-50"
                    >
                      เปิดเป็นออเดอร์ใหม่
                    </button>
                  ) : null}
                </article>
              ))}
            </div>
          </section>
        ) : null}

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

      <Dialog open={Boolean(cancelTarget)} onOpenChange={(open) => {
        if (!open && !cancelMutation.isPending) {
          setCancelTarget(null);
          setCancelReasonCode("customer_changed_mind");
          setCancelReasonNote("");
        }
      }}>
        <DialogContent className="max-h-[92dvh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-xl">ยกเลิก{cancelTarget?.type === "order" ? "ออเดอร์" : "รายการ"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 font-bold text-red-800">
              {cancelTarget?.label}
            </div>

            {!navigator.onLine ? (
              <div role="alert" className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm font-semibold text-amber-900">
                ออฟไลน์ — การยกเลิกต้องยืนยันกับ Server เพื่อป้องกันบิล สต๊อก และ KDS ไม่ตรงกัน
              </div>
            ) : cancellationPreviewQuery.isLoading ? (
              <div role="status" className="rounded-2xl border border-slate-200 p-5 text-center text-slate-500">
                กำลังตรวจสถานะครัวและผลกระทบ…
              </div>
            ) : cancellationPreviewQuery.isError ? (
              <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
                <p className="font-bold">ตรวจสอบรายการไม่ได้</p>
                <p className="mt-1">{getErrorMessage(cancellationPreviewQuery.error)}</p>
                <Button className="mt-3 h-12" variant="outline" onClick={() => void cancellationPreviewQuery.refetch()}>
                  ลองใหม่
                </Button>
              </div>
            ) : cancellationPreviewQuery.data ? (
              <div className="grid gap-3 sm:grid-cols-3" aria-live="polite">
                <div className="rounded-2xl border border-slate-200 p-4">
                  <p className="text-xs font-semibold text-slate-500">สถานะครัว</p>
                  <p className="mt-1 font-bold text-slate-950">{STATUS_LABEL[cancellationPreviewQuery.data.stage_before]}</p>
                </div>
                <div className="rounded-2xl border border-slate-200 p-4">
                  <p className="text-xs font-semibold text-slate-500">ผลกระทบบิล</p>
                  <p className="mt-1 font-bold text-slate-950">-{formatThaiCurrency(Number(cancellationPreviewQuery.data.bill_impact.amount_removed))}</p>
                </div>
                <div className={`rounded-2xl border p-4 ${cancellationPreviewQuery.data.waste_disposition === "full" ? "border-amber-200 bg-amber-50" : "border-emerald-200 bg-emerald-50"}`}>
                  <p className="text-xs font-semibold text-slate-500">วัตถุดิบ / Waste</p>
                  <p className="mt-1 font-bold text-slate-950">{cancellationPreviewQuery.data.waste_disposition === "full" ? "ตัด Waste เต็มตามสูตร" : "ไม่ตัด Waste"}</p>
                </div>
              </div>
            ) : null}

            {cancellationPreviewQuery.data?.approval_required ? (
              <div className="flex items-start gap-3 rounded-2xl border border-blue-200 bg-blue-50 p-4 text-blue-900">
                <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" />
                <div>
                  <p className="font-bold">ต้องให้ Manager คนอื่นอนุมัติ</p>
                  <p className="text-sm">รายการเริ่มทำแล้ว ระบบจะบันทึกผู้ขอ ผู้อนุมัติ Waste และประวัติ KDS</p>
                </div>
              </div>
            ) : null}

            {(cancellationPreviewQuery.data?.blockers.length ?? 0) > 0 ? (
              <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
                <p className="font-bold">ยังยกเลิกไม่ได้จนกว่าจะแก้ข้อมูล Waste/Stock</p>
                <ul className="mt-2 list-disc space-y-1 pl-5">
                  {cancellationPreviewQuery.data?.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
                </ul>
              </div>
            ) : null}

            <fieldset>
              <legend className="text-sm font-bold text-slate-800">เลือกเหตุผล</legend>
              <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
                {CANCELLATION_REASONS.map((reason) => (
                  <button
                    key={reason.code}
                    type="button"
                    onClick={() => setCancelReasonCode(reason.code)}
                    aria-pressed={cancelReasonCode === reason.code}
                    className={`min-h-14 rounded-xl border px-3 py-2 text-sm font-bold ${cancelReasonCode === reason.code ? "border-red-600 bg-red-600 text-white" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"}`}
                  >
                    {reason.label}
                  </button>
                ))}
              </div>
            </fieldset>
            <div>
              <label htmlFor="cancellation-reason-note" className="text-sm font-bold text-slate-800">
                หมายเหตุ {cancelReasonCode === "other" ? "(จำเป็น)" : "(ถ้ามี)"}
              </label>
              <textarea
                id="cancellation-reason-note"
                className="mt-1 min-h-[88px] w-full rounded-xl border border-slate-300 px-3 py-3 text-base"
                placeholder="รายละเอียดเพิ่มเติม"
                maxLength={500}
                value={cancelReasonNote}
                onChange={(event) => setCancelReasonNote(event.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button className="h-14" variant="outline" onClick={() => setCancelTarget(null)} disabled={cancelMutation.isPending}>กลับ</Button>
            <Button
              className="h-14 min-w-44 text-base font-bold"
              variant="destructive"
              disabled={
                !navigator.onLine
                || cancellationPreviewQuery.isLoading
                || cancellationPreviewQuery.isError
                || !cancellationPreviewQuery.data?.waste_ready
                || (cancelReasonCode === "other" && cancelReasonNote.trim().length === 0)
                || cancelMutation.isPending
              }
              onClick={() => {
                if (cancellationPreviewQuery.data?.approval_required) setApprovalOpen(true);
                else cancelMutation.mutate(undefined);
              }}
            >
              {cancelMutation.isPending ? "กำลังยืนยันกับ Server…" : cancellationPreviewQuery.data?.approval_required ? "ขออนุมัติ Manager" : "ยืนยันยกเลิก"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {cancelTarget && cancellationPreviewQuery.data?.approval_required ? (
        <ManagerApprovalDialog
          open={approvalOpen}
          onOpenChange={setApprovalOpen}
          action="fb.order.cancel_after_kitchen"
          requestPayload={cancellationPayload()}
          reason={cancelReasonNote.trim() || CANCELLATION_REASONS.find((reason) => reason.code === cancelReasonCode)?.label || "ยกเลิกรายการหลังครัวเริ่มทำ"}
          description="Manager ต้องเป็นคนละคนกับผู้ขอ ระบบจะตัด Waste และส่งเหตุการณ์ยกเลิกไป KDS เมื่ออนุมัติสำเร็จ"
          onApproved={async (approvalToken) => {
            await cancelMutation.mutateAsync(approvalToken);
          }}
        />
      ) : null}

      {reopenTarget ? (
        <ManagerApprovalDialog
          open={Boolean(reopenTarget)}
          onOpenChange={(open) => { if (!open && !reopenMutation.isPending) setReopenTarget(null); }}
          action="fb.order.cancel.reopen"
          requestPayload={{
            cancellation_id: reopenTarget.id,
            idempotency_key: reopenKey,
            reason: reopenReason,
          }}
          reason={reopenReason}
          description="Reopen จะสร้างออเดอร์และ KDS ticket ใหม่ด้วยราคาปัจจุบัน โดยไม่ลบประวัติหรือย้อน Waste เดิม"
          onApproved={async (approvalToken) => {
            await reopenMutation.mutateAsync(approvalToken);
          }}
        />
      ) : null}
    </div>
  );
}
