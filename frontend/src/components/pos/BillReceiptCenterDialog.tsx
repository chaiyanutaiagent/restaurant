import {
  AlertTriangle,
  FileText,
  Loader2,
  Printer,
  RotateCcw,
  Search,
  ShieldX,
  WifiOff,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { SaleOrder } from "@/types/pos";

type Props = {
  open: boolean;
  orders: SaleOrder[];
  isLoading: boolean;
  isError: boolean;
  isRefreshing: boolean;
  updatedAt: number;
  online: boolean;
  canVoid: boolean;
  canRefund: boolean;
  refundUnavailableReason?: string;
  onOpenChange: (open: boolean) => void;
  onRetry: () => void;
  onPrint: (order: SaleOrder) => void;
  onVoid: (order: SaleOrder) => void;
  onRefund: (order: SaleOrder) => void;
};

type StatusFilter = "all" | "completed" | "partially_refunded" | "refunded" | "voided";

const STATUS_LABEL: Record<string, string> = {
  completed: "ชำระแล้ว",
  partially_refunded: "คืนบางส่วน",
  refunded: "คืนครบแล้ว",
  voided: "Void แล้ว",
  pending_sync: "รอซิงก์",
};

const STATUS_STYLE: Record<string, string> = {
  completed: "bg-emerald-100 text-emerald-800",
  partially_refunded: "bg-amber-100 text-amber-900",
  refunded: "bg-blue-100 text-blue-800",
  voided: "bg-slate-200 text-slate-700",
  pending_sync: "bg-orange-100 text-orange-800",
};

function money(value: number | string): string {
  return new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(Number(value));
}

function dateTime(value: string): string {
  return new Intl.DateTimeFormat("th-TH", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function voidEligibility(order: SaleOrder): { allowed: boolean; reason: string } {
  if (order.status !== "completed") {
    return { allowed: false, reason: "Void ได้เฉพาะบิลชำระแล้วที่ยังไม่ถูกแก้ไข" };
  }
  const positivePayments = order.payments.filter((payment) => Number(payment.amount) > 0);
  if (positivePayments.length === 0) {
    return { allowed: false, reason: "ไม่พบ Payment ที่ Server ยืนยันสำหรับ Void" };
  }
  const unsafe = positivePayments.find(
    (payment) => !["authorized", "pending"].includes(payment.settlement_state || "unknown"),
  );
  if (unsafe) {
    return { allowed: false, reason: "Payment รับเงินจริงแล้วหรือไม่ทราบผล ให้ใช้ Refund แทน" };
  }
  return { allowed: true, reason: "Payment ยังอยู่ในสถานะที่ Server อนุญาตให้ Void" };
}

function refundEligibility(order: SaleOrder): { allowed: boolean; reason: string } {
  if (!["completed", "partially_refunded"].includes(order.status)) {
    return { allowed: false, reason: "สถานะบิลนี้ไม่รองรับ Refund" };
  }
  const hasRemainingItem = order.items.some(
    (item) => Number(item.qty) - Number(item.refunded_qty ?? 0) > 0,
  );
  if (!hasRemainingItem) {
    return { allowed: false, reason: "รายการในบิลถูกคืนครบแล้ว" };
  }
  return { allowed: true, reason: "Server จะคำนวณยอดคืนจากบิลเดิมอีกครั้ง" };
}

export default function BillReceiptCenterDialog({
  open,
  orders,
  isLoading,
  isError,
  isRefreshing,
  updatedAt,
  online,
  canVoid,
  canRefund,
  refundUnavailableReason,
  onOpenChange,
  onRetry,
  onPrint,
  onVoid,
  onRefund,
}: Props): JSX.Element {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const term = query.trim().toLocaleLowerCase("th-TH");
    return orders.filter((order) => {
      if (status !== "all" && order.status !== status) return false;
      if (!term) return true;
      const haystack = [
        order.order_number,
        order.customer_name,
        order.customer_phone,
        ...order.items.map((item) => `${item.product_name} ${item.sku || ""}`),
      ].filter(Boolean).join(" ").toLocaleLowerCase("th-TH");
      return haystack.includes(term);
    });
  }, [orders, query, status]);

  useEffect(() => {
    if (!open) return;
    if (!selectedId || !filtered.some((order) => order.id === selectedId)) {
      setSelectedId(filtered[0]?.id ?? null);
    }
  }, [filtered, open, selectedId]);

  const selected = filtered.find((order) => order.id === selectedId) ?? null;
  const voidState = selected ? voidEligibility(selected) : null;
  const refundState = selected ? refundEligibility(selected) : null;
  const salePayments = selected?.payments.filter((payment) => Number(payment.amount) >= 0) ?? [];
  const refundPayments = selected?.payments.filter((payment) => Number(payment.amount) < 0) ?? [];
  const refundableAmount = selected
    ? Math.max(Number(selected.total_amount) - Number(selected.refund_amount ?? 0), 0)
    : 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[94dvh] w-[calc(100vw-1.5rem)] max-w-6xl flex-col overflow-hidden p-0">
        <DialogHeader className="border-b border-slate-200 px-5 py-5 pr-16 md:px-7">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <DialogTitle className="text-xl">ศูนย์บิลและใบเสร็จ</DialogTitle>
              <DialogDescription className="mt-1">
                บิลในกะปัจจุบัน · ค้นหา พิมพ์ซ้ำ และส่งคำขอ Void หรือ Refund ตามสถานะจริงจาก Server
              </DialogDescription>
            </div>
            <Button className="h-12 shrink-0" variant="outline" onClick={onRetry} disabled={!online || isRefreshing}>
              <RotateCcw className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`} />
              {isRefreshing ? "กำลังอัปเดต" : "ข้อมูลล่าสุด"}
            </Button>
          </div>
          <p className={`text-xs ${updatedAt > 0 && Date.now() - updatedAt > 60_000 ? "font-semibold text-amber-700" : "text-slate-500"}`}>
            {updatedAt > 0 ? `อัปเดต ${dateTime(new Date(updatedAt).toISOString())}${Date.now() - updatedAt > 60_000 ? " · ข้อมูลอาจเก่า กดอัปเดตก่อนทำรายการ" : ""}` : "ยังไม่ได้รับข้อมูลจาก Server"}
          </p>
        </DialogHeader>

        {!online ? (
          <div role="alert" className="mx-5 mt-4 flex min-h-12 items-center gap-3 rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-900 md:mx-7">
            <WifiOff className="h-5 w-5 shrink-0" />
            ออฟไลน์ — ดูข้อมูลที่โหลดแล้วและพิมพ์ได้ แต่ Void, Refund และ Manager approval ถูกปิด
          </div>
        ) : null}

        <div className="grid min-h-0 flex-1 md:grid-cols-[minmax(17rem,0.9fr)_minmax(0,1.6fr)]">
          <section className="flex min-h-0 flex-col border-b border-slate-200 bg-slate-50/70 md:border-b-0 md:border-r" aria-label="รายการบิล">
            <div className="space-y-3 border-b border-slate-200 p-4">
              <label className="relative block">
                <span className="sr-only">ค้นหาบิล ลูกค้า หรือสินค้า</span>
                <Search className="pointer-events-none absolute left-3 top-3.5 h-5 w-5 text-slate-400" />
                <Input
                  className="h-12 bg-white pl-10"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="ค้นหาเลขบิล ลูกค้า หรือสินค้า"
                />
              </label>
              <select
                aria-label="กรองสถานะบิล"
                className="h-12 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm font-semibold"
                value={status}
                onChange={(event) => setStatus(event.target.value as StatusFilter)}
              >
                <option value="all">ทุกสถานะ</option>
                <option value="completed">ชำระแล้ว</option>
                <option value="partially_refunded">คืนบางส่วน</option>
                <option value="refunded">คืนครบแล้ว</option>
                <option value="voided">Void แล้ว</option>
              </select>
            </div>

            <div className="min-h-52 flex-1 overflow-y-auto p-3 md:min-h-0">
              {isLoading ? (
                <div role="status" className="flex min-h-44 flex-col items-center justify-center gap-3 text-sm text-slate-500">
                  <Loader2 className="h-6 w-6 animate-spin" /> กำลังโหลดบิลจาก Server…
                </div>
              ) : isError ? (
                <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
                  <div className="flex items-center gap-2 font-bold"><AlertTriangle className="h-5 w-5" />โหลดบิลไม่สำเร็จ</div>
                  <p className="mt-2">ระบบยังไม่แสดงข้อมูลเก่าแทนผลลัพธ์ที่ไม่แน่นอน</p>
                  <Button className="mt-3 h-12" variant="outline" onClick={onRetry}><RotateCcw className="h-4 w-4" />ลองใหม่</Button>
                </div>
              ) : filtered.length === 0 ? (
                <div className="flex min-h-44 flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 px-4 text-center text-sm text-slate-500">
                  <FileText className="mb-3 h-8 w-8 text-slate-300" />
                  {orders.length === 0 ? "ยังไม่มีบิลในกะนี้" : "ไม่พบบิลที่ตรงกับคำค้นและตัวกรอง"}
                </div>
              ) : (
                <div className="space-y-2">
                  {filtered.map((order) => (
                    <button
                      key={order.id}
                      type="button"
                      onClick={() => setSelectedId(order.id)}
                      className={`min-h-20 w-full rounded-2xl border p-3 text-left transition ${selectedId === order.id ? "border-blue-500 bg-blue-50 ring-2 ring-blue-100" : "border-slate-200 bg-white hover:border-blue-200"}`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate font-bold text-slate-950">{order.order_number}</div>
                          <div className="mt-1 truncate text-xs text-slate-500">{order.customer_name || "ลูกค้าทั่วไป"} · {dateTime(order.created_at)}</div>
                        </div>
                        <div className="text-right">
                          <div className="font-bold text-slate-950">{money(order.total_amount)}</div>
                          <span className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold ${STATUS_STYLE[order.status] || "bg-slate-100 text-slate-700"}`}>
                            {STATUS_LABEL[order.status] || order.status}
                          </span>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </section>

          <section className="min-h-0 overflow-y-auto bg-white p-5 md:p-6" aria-label="รายละเอียดบิล">
            {!selected ? (
              <div className="flex min-h-72 flex-col items-center justify-center text-center text-slate-500">
                <FileText className="mb-3 h-10 w-10 text-slate-300" />
                <p className="font-semibold">เลือกบิลเพื่อดูรายละเอียด</p>
                <p className="mt-1 text-sm">การทำรายการเสี่ยงจะตรวจสิทธิ์และสถานะกับ Server อีกครั้ง</p>
              </div>
            ) : (
              <div className="space-y-5">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-xl font-black text-slate-950">{selected.order_number}</h3>
                      <span className={`rounded-full px-3 py-1 text-xs font-bold ${STATUS_STYLE[selected.status] || "bg-slate-100 text-slate-700"}`}>
                        {STATUS_LABEL[selected.status] || selected.status}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-slate-500">{dateTime(selected.created_at)} · {selected.customer_name || "ลูกค้าทั่วไป"}</p>
                  </div>
                  <div className="rounded-2xl bg-slate-950 px-5 py-4 text-right text-white">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">ยอดบิล</div>
                    <div className="mt-1 text-2xl font-black">{money(selected.total_amount)}</div>
                    {Number(selected.refund_amount ?? 0) > 0 ? <div className="mt-1 text-xs text-amber-300">คืนแล้ว {money(Number(selected.refund_amount ?? 0))}</div> : null}
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded-2xl border border-slate-200 p-4"><div className="text-xs font-semibold text-slate-500">ก่อนส่วนลด</div><div className="mt-1 font-bold">{money(selected.subtotal)}</div></div>
                  <div className="rounded-2xl border border-slate-200 p-4"><div className="text-xs font-semibold text-slate-500">ส่วนลด</div><div className="mt-1 font-bold text-amber-700">-{money(selected.discount_amount)}</div></div>
                  <div className="rounded-2xl border border-slate-200 p-4"><div className="text-xs font-semibold text-slate-500">VAT</div><div className="mt-1 font-bold">{money(selected.vat_amount)}</div></div>
                </div>

                <div className="rounded-2xl border border-slate-200">
                  <div className="border-b border-slate-200 px-4 py-3 font-bold text-slate-900">รายการสินค้า</div>
                  <div className="max-h-60 space-y-2 overflow-y-auto p-3">
                    {selected.items.map((item) => {
                      const remaining = Math.max(Number(item.qty) - Number(item.refunded_qty ?? 0), 0);
                      return (
                        <div key={item.id} className="flex items-start justify-between gap-4 rounded-xl bg-slate-50 p-3 text-sm">
                          <div className="min-w-0"><div className="font-semibold text-slate-900">{item.product_name}</div><div className="mt-1 text-xs text-slate-500">{money(item.unit_price)} × {item.qty}{Number(item.refunded_qty ?? 0) > 0 ? ` · คืนแล้ว ${item.refunded_qty}` : ""}</div></div>
                          <div className="text-right"><div className="font-bold">{money(item.subtotal)}</div><div className="mt-1 text-xs text-slate-500">คืนได้อีก {remaining}</div></div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="rounded-2xl border border-slate-200 p-4">
                    <div className="font-bold text-slate-900">การชำระเงิน</div>
                    <div className="mt-3 space-y-2">
                      {salePayments.map((payment) => <div key={payment.id} className="flex justify-between gap-3 rounded-xl bg-slate-50 p-3 text-sm"><span>{payment.payment_method}{payment.settlement_state ? ` · ${payment.settlement_state}` : ""}</span><strong>{money(payment.amount)}</strong></div>)}
                      {salePayments.length === 0 ? <p className="text-sm text-slate-500">ไม่มีข้อมูล Payment</p> : null}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
                    <div className="font-bold text-amber-950">Refund / Credit Note</div>
                    <div className="mt-2 flex justify-between text-sm text-amber-900"><span>คืนสะสม</span><strong>{money(Number(selected.refund_amount ?? 0))}</strong></div>
                    <div className="mt-1 flex justify-between text-sm text-amber-900"><span>คงเหลือคืนได้</span><strong>{money(refundableAmount)}</strong></div>
                    {refundPayments.length > 0 ? <div className="mt-3 text-xs text-amber-800">พบ Payment คืนเงิน {refundPayments.length} รายการ</div> : <div className="mt-3 text-xs text-amber-800">เอกสารภาษีจริงยังไม่เปิดใช้; UAT รองรับเฉพาะ NON-FISCAL ตามสถานะใน Refund workspace</div>}
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                    <Button className="h-12" variant="outline" onClick={() => onPrint(selected)}><Printer className="h-4 w-4" />เปิดใบเสร็จ</Button>
                    <Button className="h-12" variant="outline" disabled={!online || !canVoid || !voidState?.allowed} onClick={() => onVoid(selected)}>Void บิล</Button>
                    <Button className="h-12" disabled={!online || !canRefund || !refundState?.allowed} onClick={() => onRefund(selected)}>
                      {refundUnavailableReason ? "คืนสินค้า / คืนเงิน · WP57" : "คืนสินค้า / คืนเงิน"}
                    </Button>
                    <Button className="h-12" variant="outline" disabled title="ยังไม่มี Atomic exchange contract">แลกสินค้า · ยังไม่เปิดใช้</Button>
                  </div>
                  <div className="mt-3 space-y-1 text-xs text-slate-600">
                    {!canVoid || !canRefund ? <p className="flex items-center gap-2 text-amber-800"><ShieldX className="h-4 w-4" />บาง action ถูกปิดตามสิทธิ์ของพนักงาน</p> : null}
                    {refundUnavailableReason ? <p className="text-amber-800">Refund: {refundUnavailableReason}</p> : null}
                    {voidState && !voidState.allowed ? <p>Void: {voidState.reason}</p> : null}
                    {refundState && !refundState.allowed ? <p>Refund: {refundState.reason}</p> : null}
                    {!online ? <p>เชื่อมต่อ Server ก่อนทำ Void, Refund หรือขอ Manager approval</p> : null}
                  </div>
                </div>
              </div>
            )}
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
