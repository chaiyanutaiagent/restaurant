import { AlertTriangle, CheckCircle2, Minus, Plus, RefreshCcw, ShieldCheck, WifiOff } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import ManagerApprovalDialog from "@/components/approval/ManagerApprovalDialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { useToast } from "@/components/ui/use-toast";
import { posApi } from "@/lib/posApi";
import type { CashierShift, RefundOperation, RefundQuote, SaleOrder } from "@/types/pos";

type Props = {
  open: boolean;
  order: SaleOrder | null;
  shift: CashierShift | null;
  online: boolean;
  onOpenChange: (open: boolean) => void;
  onCompleted: () => Promise<void> | void;
};

type ReasonCode = "customer_request" | "wrong_item" | "quality_issue" | "duplicate_charge" | "payment_error" | "other";
type ProviderScenario = "succeeded" | "failed" | "processing_then_succeeded" | "unknown_then_succeeded" | "unknown_persistent";

const UAT_SIMULATOR_ENABLED = import.meta.env.DEV || import.meta.env.VITE_REFUND_UAT_SIMULATOR === "true";

function money(value: number | string): string {
  return new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(Number(value));
}

function message(error: unknown): string {
  const candidate = error as { response?: { data?: { detail?: string | { message?: string } } }; message?: string };
  const detail = candidate.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.message) return detail.message;
  return candidate.message || "ไม่สามารถทำรายการได้ กรุณาลองใหม่";
}

const statusCopy: Record<string, { title: string; detail: string; tone: string }> = {
  requested: { title: "รับคำขอแล้ว", detail: "กำลังส่งคำขอไปยังช่องทางชำระเงิน", tone: "bg-blue-50 text-blue-800" },
  processing: { title: "Provider กำลังดำเนินการ", detail: "ยังไม่ถือว่าคืนเงินสำเร็จ กรุณาตรวจสอบสถานะ", tone: "bg-blue-50 text-blue-800" },
  cash_due: { title: "พร้อมคืนเงินสด", detail: "คืนเงินจริงให้ลูกค้าก่อนกดยืนยัน", tone: "bg-amber-50 text-amber-900" },
  succeeded: { title: "คืนเงินสำเร็จ", detail: "กำลังจัดทำเอกสารและกระทบยอด", tone: "bg-emerald-50 text-emerald-800" },
  completed: { title: "ปิดรายการครบแล้ว", detail: "Payment, Ledger และเอกสารที่เกี่ยวข้องถูกกระทบยอดแล้ว", tone: "bg-emerald-50 text-emerald-800" },
  failed: { title: "Provider ปฏิเสธรายการ", detail: "ยังไม่มี Payment ติดลบ สต๊อก หรือ Credit Note", tone: "bg-red-50 text-red-800" },
  unknown: { title: "ไม่ทราบผลจาก Provider", detail: "ห้ามกดคืนซ้ำ ให้ตรวจสอบกับ Server ก่อน", tone: "bg-amber-50 text-amber-900" },
  needs_reconciliation: { title: "ต้องตรวจสอบโดยผู้จัดการ", detail: "มี payment leg บางส่วนสำเร็จ ห้าม retry อัตโนมัติ", tone: "bg-red-50 text-red-800" },
  tax_pending: { title: "คืนเงินแล้ว · เอกสารรอตรวจ", detail: "Credit Note ยังไม่เสร็จ รายการยังปิดกะไม่ได้", tone: "bg-amber-50 text-amber-900" }
};

export default function RefundWorkspaceDialog({ open, order, shift, online, onOpenChange, onCompleted }: Props): JSX.Element {
  const { toast } = useToast();
  const [qty, setQty] = useState<Record<string, number>>({});
  const [reasonCode, setReasonCode] = useState<ReasonCode>("customer_request");
  const [reasonNote, setReasonNote] = useState("");
  const [stockDisposition, setStockDisposition] = useState<"none" | "sellable">("none");
  const [scenario, setScenario] = useState<ProviderScenario>("succeeded");
  const [quote, setQuote] = useState<RefundQuote | null>(null);
  const [operation, setOperation] = useState<RefundOperation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [approvalOpen, setApprovalOpen] = useState(false);
  const [executeKey, setExecuteKey] = useState("");

  useEffect(() => {
    if (!open || !order) return;
    setQty(Object.fromEntries(order.items.map((item) => [item.id, 0])));
    setReasonCode("customer_request");
    setReasonNote("");
    setStockDisposition("none");
    setScenario("succeeded");
    setQuote(null);
    setOperation(null);
    setError(null);
    setApprovalOpen(false);
    setExecuteKey(crypto.randomUUID());
  }, [open, order]);

  const selectedCount = useMemo(() => Object.values(qty).filter((value) => value > 0).length, [qty]);
  const approvalPayload = quote && order ? {
    quote_id: quote.id,
    quote_hash: quote.quote_hash,
    order_id: order.id,
    expected_order_version: quote.order_version,
    total_amount: Number(quote.totals.total_amount),
    reason_code: reasonCode,
    reason_note: reasonNote.trim() || undefined,
    stock_disposition: stockDisposition,
    provider_scenario: scenario,
    idempotency_key: executeKey
  } : null;

  async function createQuote(): Promise<void> {
    if (!order || !shift || selectedCount === 0) {
      setError("เลือกอย่างน้อย 1 รายการและต้องมีกะที่เปิดอยู่");
      return;
    }
    if (!online) {
      setError("Refund ทำแบบ Offline ไม่ได้ กรุณาเชื่อมต่อ Server");
      return;
    }
    if (reasonCode === "other" && reasonNote.trim().length < 3) {
      setError("กรุณาระบุเหตุผลเพิ่มเติมอย่างน้อย 3 ตัวอักษร");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await posApi.createRefundQuote({
        order_id: order.id,
        shift_id: shift.id,
        items: order.items
          .filter((item) => (qty[item.id] || 0) > 0)
          .map((item) => ({ order_item_id: item.id, qty: qty[item.id] })),
        reason_code: reasonCode,
        reason_note: reasonNote.trim() || undefined,
        stock_disposition: stockDisposition,
        currency: "THB",
        idempotency_key: `refund-quote-${crypto.randomUUID()}`
      });
      setQuote(response.data.data);
    } catch (caught) {
      setError(message(caught));
    } finally {
      setBusy(false);
    }
  }

  async function execute(approvalToken: string): Promise<void> {
    if (!approvalPayload) return;
    setBusy(true);
    setError(null);
    try {
      const response = await posApi.executeRefund({ ...approvalPayload, approval_token: approvalToken });
      setOperation(response.data.data);
      setApprovalOpen(false);
      if (response.data.data.status === "completed") await onCompleted();
    } catch (caught) {
      setError(message(caught));
      throw caught;
    } finally {
      setBusy(false);
    }
  }

  async function action(kind: "cash" | "inquire" | "retry" | "tax"): Promise<void> {
    if (!operation) return;
    setBusy(true);
    setError(null);
    const payload = { expected_version: operation.row_version, idempotency_key: `refund-${kind}-${crypto.randomUUID()}` };
    try {
      const response = kind === "cash"
        ? await posApi.confirmCashRefund(operation.id, payload)
        : kind === "inquire"
          ? await posApi.inquireRefund(operation.id, payload)
          : kind === "retry"
            ? await posApi.retryRefund(operation.id, payload)
            : await posApi.retryRefundTax(operation.id, payload);
      setOperation(response.data.data);
      if (response.data.data.status === "completed") {
        toast({ title: "คืนเงินและกระทบยอดครบแล้ว", description: `อ้างอิง ${response.data.data.id.slice(0, 8)}` });
        await onCompleted();
      }
    } catch (caught) {
      setError(message(caught));
    } finally {
      setBusy(false);
    }
  }

  const status = operation ? statusCopy[operation.status] : null;

  return (
    <>
      <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
        <DialogContent className="max-h-[92vh] max-w-4xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-xl">คืนสินค้า / คืนเงิน</DialogTitle>
            <DialogDescription>
              {order ? `บิล ${order.order_number} · Server จะคำนวณยอดและ VAT จากบิลเดิม` : "เลือกรายการจากประวัติบิล"}
            </DialogDescription>
          </DialogHeader>

          {!online ? (
            <div role="alert" className="flex gap-3 rounded-2xl bg-red-50 p-4 text-red-800">
              <WifiOff className="mt-0.5 h-5 w-5 shrink-0" />
              <div><div className="font-semibold">Offline — ปิดการคืนเงินชั่วคราว</div><div className="text-sm">Refund, approval, provider และ Credit Note ต้องยืนยันกับ Server</div></div>
            </div>
          ) : null}

          {!quote && order ? (
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                {order.items.map((item) => {
                  const available = Math.max(Number(item.qty) - Number(item.refunded_qty || 0), 0);
                  const current = qty[item.id] || 0;
                  return (
                    <div key={item.id} className="rounded-2xl border border-slate-200 p-4">
                      <div className="font-semibold text-slate-900">{item.product_name}</div>
                      <div className="mt-1 text-sm text-slate-500">คืนได้ {available} · คืนสะสม {item.refunded_qty || 0}</div>
                      <div className="mt-3 flex items-center justify-end gap-3">
                        <Button aria-label={`ลดจำนวน ${item.product_name}`} className="h-12 w-12" variant="outline" disabled={current <= 0} onClick={() => setQty((value) => ({ ...value, [item.id]: Math.max(0, current - 1) }))}><Minus /></Button>
                        <output aria-live="polite" className="min-w-10 text-center text-xl font-bold">{current}</output>
                        <Button aria-label={`เพิ่มจำนวน ${item.product_name}`} className="h-12 w-12" variant="outline" disabled={current >= available} onClick={() => setQty((value) => ({ ...value, [item.id]: Math.min(available, current + 1) }))}><Plus /></Button>
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <label className="grid gap-2 text-sm font-medium">เหตุผล
                  <select className="h-12 rounded-xl border border-slate-300 bg-white px-3" value={reasonCode} onChange={(event) => setReasonCode(event.target.value as ReasonCode)}>
                    <option value="customer_request">ลูกค้าขอคืน</option><option value="wrong_item">สินค้าผิด</option>
                    <option value="quality_issue">คุณภาพสินค้า</option><option value="duplicate_charge">เรียกเก็บซ้ำ</option>
                    <option value="payment_error">การชำระเงินผิดพลาด</option><option value="other">อื่น ๆ</option>
                  </select>
                </label>
                <label className="grid gap-2 text-sm font-medium">ปลายทางสินค้า
                  <select className="h-12 rounded-xl border border-slate-300 bg-white px-3" value={stockDisposition} onChange={(event) => setStockDisposition(event.target.value as "none" | "sellable")}>
                    <option value="none">ไม่คืนสต๊อก / อาหารหรือบริการ</option><option value="sellable">คืนเข้าสต๊อกขายได้</option>
                  </select>
                </label>
              </div>
              <label className="grid gap-2 text-sm font-medium">รายละเอียดเพิ่มเติม
                <textarea className="min-h-24 rounded-xl border border-slate-300 p-3" maxLength={500} value={reasonNote} onChange={(event) => setReasonNote(event.target.value)} />
              </label>
            </div>
          ) : null}

          {quote && !operation ? (
            <div className="space-y-4">
              <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4">
                <div className="text-sm font-semibold text-blue-900">ยอดคืนจาก Server</div>
                <div className="mt-1 text-3xl font-bold text-blue-950">{money(quote.totals.total_amount)}</div>
                <div className="mt-2 text-sm text-blue-800">ก่อน VAT {money(quote.totals.subtotal_amount)} · VAT {money(quote.totals.vat_amount)} · ปัดเศษ {money(quote.totals.rounding_amount)}</div>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {quote.payment_allocations.map((leg) => (
                  <div key={leg.original_payment_id} className="rounded-2xl border border-slate-200 p-4">
                    <div className="font-semibold">{leg.leg_type === "cash" ? "คืนเงินสด" : `คืนผ่าน ${leg.provider_name || leg.payment_method}`}</div>
                    <div className="mt-1 text-xl font-bold">{money(leg.amount)}</div>
                    <div className="text-xs text-slate-500">อ้างอิง Payment เดิม · {leg.currency}</div>
                  </div>
                ))}
              </div>
              {UAT_SIMULATOR_ENABLED ? (
                <details className="rounded-xl border border-dashed border-slate-300 p-3 text-sm">
                  <summary className="cursor-pointer font-medium">UAT Provider simulator · Sandbox เท่านั้น</summary>
                  <select className="mt-3 h-12 w-full rounded-xl border border-slate-300 bg-white px-3" value={scenario} onChange={(event) => setScenario(event.target.value as ProviderScenario)}>
                    <option value="succeeded">สำเร็จ</option><option value="failed">ล้มเหลวแล้ว retry ได้</option>
                    <option value="processing_then_succeeded">กำลังทำ → inquiry สำเร็จ</option>
                    <option value="unknown_then_succeeded">ไม่ทราบผล → inquiry สำเร็จ</option>
                    <option value="unknown_persistent">ไม่ทราบผลต่อเนื่อง</option>
                  </select>
                </details>
              ) : null}
              <div className="flex items-start gap-3 rounded-2xl bg-amber-50 p-4 text-sm text-amber-900">
                <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" />รายการคืนเงินทุกยอดใช้ maker-checker ผู้ขอและผู้อนุมัติต้องเป็นคนละคน
              </div>
            </div>
          ) : null}

          {operation && status ? (
            <div className="space-y-4">
              <div role="status" className={`rounded-2xl p-5 ${status.tone}`}>
                <div className="flex items-center gap-2 text-lg font-bold">
                  {operation.status === "completed" ? <CheckCircle2 /> : <AlertTriangle />}{status.title}
                </div>
                <div className="mt-1 text-sm">{status.detail}</div>
                <div className="mt-3 text-2xl font-bold">{money(operation.total_amount)}</div>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {operation.payment_legs.map((leg) => (
                  <div key={leg.id} className="rounded-2xl border border-slate-200 p-4">
                    <div className="font-semibold">{leg.leg_type === "cash" ? "เงินสด" : leg.provider_name || leg.payment_method}</div>
                    <div className="mt-1">{money(leg.amount)} · <span className="font-medium">{leg.status}</span></div>
                    <div className="mt-1 text-xs text-slate-500">attempt {leg.attempt_count}{leg.provider_refund_ref ? ` · ${leg.provider_refund_ref}` : ""}</div>
                  </div>
                ))}
              </div>
              <div className="rounded-2xl border border-slate-200 p-4 text-sm">
                <div className="font-semibold">Credit Note / ภาษี</div>
                <div className="mt-1">{operation.tax ? operation.tax.status : "กำลังตรวจเอกสารเดิม"}</div>
                {operation.tax?.credit_note_id ? <div className="text-xs text-slate-500">UAT NON-FISCAL · {operation.tax.credit_note_id}</div> : null}
              </div>
            </div>
          ) : null}

          {error ? <div role="alert" className="rounded-2xl bg-red-50 p-4 text-sm text-red-800">{error}</div> : null}

          <DialogFooter className="gap-2 sm:gap-2">
            <Button className="h-12" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>ปิด</Button>
            {!quote ? <Button className="h-12" onClick={() => void createQuote()} disabled={busy || !online || selectedCount === 0}>{busy ? "กำลังคำนวณ..." : "ขอยอดคืนจาก Server"}</Button> : null}
            {quote && !operation ? <Button className="h-12" onClick={() => setApprovalOpen(true)} disabled={busy || !online}><ShieldCheck className="mr-2 h-4 w-4" />ขออนุมัติและคืนเงิน</Button> : null}
            {operation?.status === "cash_due" ? <Button className="h-12" onClick={() => void action("cash")} disabled={busy}>ยืนยันว่าคืนเงินสดแล้ว</Button> : null}
            {operation && ["processing", "unknown"].includes(operation.status) ? <Button className="h-12" onClick={() => void action("inquire")} disabled={busy}><RefreshCcw className="mr-2 h-4 w-4" />ตรวจสอบกับ Provider</Button> : null}
            {operation?.status === "failed" ? <Button className="h-12" onClick={() => void action("retry")} disabled={busy}><RefreshCcw className="mr-2 h-4 w-4" />Retry ที่ปลอดภัย</Button> : null}
            {operation?.status === "tax_pending" ? <Button className="h-12" onClick={() => void action("tax")} disabled={busy}><RefreshCcw className="mr-2 h-4 w-4" />ลองสร้าง Credit Note ใหม่</Button> : null}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {quote && approvalPayload ? (
        <ManagerApprovalDialog
          open={approvalOpen}
          onOpenChange={setApprovalOpen}
          action="pos.refund.create"
          requestPayload={approvalPayload}
          reason={reasonNote.trim() || reasonCode}
          description={`อนุมัติคืนเงินบิล ${order?.order_number || "-"} ${money(quote.totals.total_amount)}`}
          onApproved={execute}
        />
      ) : null}
    </>
  );
}
