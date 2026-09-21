import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowDownToLine, ArrowUpFromLine, Banknote, CheckCircle2, Loader2, LockKeyhole, RefreshCw, ShieldCheck, WifiOff } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import ManagerApprovalDialog from "@/components/approval/ManagerApprovalDialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/approvalApi";
import { formatThaiCurrency } from "@/lib/cartUtils";
import { posApi } from "@/lib/posApi";
import type { CashierShift, PosShiftSummary } from "@/types/pos";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  shift: CashierShift;
  online: boolean;
  operatorLabel?: string;
  cashMovementApprovalThreshold: number;
  varianceSoftThreshold: number;
  varianceApprovalThreshold: number;
  canCreateCashMovement: boolean;
  canHandover: boolean;
  onShiftUpdated: (shift: CashierShift) => void;
  onClosed: (shift: CashierShift) => void;
  onHandover: (shift: CashierShift) => void;
};

type CloseReason = "count_short" | "count_over" | "change_error" | "cash_movement" | "other";
type MovementReason = "change_fund" | "cash_drop" | "petty_cash" | "supplier_payment" | "correction" | "other";
const DENOMINATIONS = [1000, 500, 100, 50, 20, 10, 5, 2, 1, 0.5, 0.25];
const PAYMENT_LABELS: Record<string, string> = { cash: "เงินสด", promptpay: "PromptPay", credit_card: "บัตรเครดิต", bank_transfer: "โอนเงิน", other: "อื่น ๆ" };

function requestKey(prefix: string): string {
  const suffix = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}:${suffix}`;
}

export default function CloseShiftDialog({
  open, onOpenChange, shift, online, operatorLabel, cashMovementApprovalThreshold,
  varianceSoftThreshold, varianceApprovalThreshold, canCreateCashMovement, canHandover,
  onShiftUpdated, onClosed, onHandover,
}: Props): JSX.Element {
  const [step, setStep] = useState<"summary" | "count" | "movement">("summary");
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [reasonCode, setReasonCode] = useState<CloseReason | "">("");
  const [note, setNote] = useState("");
  const [closeMode, setCloseMode] = useState<"close" | "handover">("close");
  const [isSaving, setIsSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [movementType, setMovementType] = useState<"cash_in" | "cash_out">("cash_in");
  const [movementAmount, setMovementAmount] = useState(0);
  const [movementReasonCode, setMovementReasonCode] = useState<MovementReason>("change_fund");
  const [movementReason, setMovementReason] = useState("");
  const [movementKey, setMovementKey] = useState(() => requestKey("cash-movement"));
  const [closeKey, setCloseKey] = useState(() => requestKey("shift-close"));
  const [approval, setApproval] = useState<null | {
    action: "pos.cash_movement.approve" | "pos.shift.variance.approve";
    requestPayload: Record<string, unknown>;
    reason: string;
    description: string;
    onApproved: (token: string) => Promise<void>;
  }>(null);

  const summaryQuery = useQuery({
    queryKey: ["pos", "shift-summary", shift.id],
    queryFn: async () => (await posApi.getShiftSummary(shift.id)).data.data,
    enabled: open && online,
    refetchOnWindowFocus: true,
  });
  const summary = summaryQuery.data as PosShiftSummary | undefined;

  useEffect(() => {
    if (!open) return;
    setStep("summary"); setCounts({}); setReasonCode(""); setNote(""); setCloseMode("close"); setFormError("");
    setMovementKey(requestKey("cash-movement")); setCloseKey(requestKey("shift-close"));
  }, [open, shift.id]);

  const countedCash = useMemo(
    () => DENOMINATIONS.reduce((total, value) => total + value * (counts[String(value)] ?? 0), 0),
    [counts],
  );
  const expectedCash = Number(summary?.expected_cash ?? 0);
  const difference = Math.round((countedCash - expectedCash) * 100) / 100;
  const needsReason = difference !== 0;
  const needsManager = Math.abs(difference) >= varianceApprovalThreshold;
  const cashCount = DENOMINATIONS.map((denomination) => ({ denomination, quantity: counts[String(denomination)] ?? 0 })).filter((item) => item.quantity > 0);
  const closePayload = {
    closing_cash: countedCash,
    reason_code: needsReason ? (reasonCode || undefined) : undefined,
    note: note.trim() || undefined,
    cash_count: cashCount,
    expected_version: summary?.version,
    idempotency_key: closeKey,
  };

  async function refreshShift(): Promise<void> {
    const [, currentResult] = await Promise.all([summaryQuery.refetch(), posApi.getCurrentShift()]);
    if (currentResult.data.data) onShiftUpdated(currentResult.data.data);
  }

  function movementPayload() {
    return {
      movement_type: movementType,
      amount: movementAmount,
      reason_code: movementReasonCode,
      reason: movementReason.trim(),
      expected_shift_version: summary?.version ?? shift.version,
      idempotency_key: movementKey,
    };
  }

  async function executeMovement(approvalToken?: string): Promise<void> {
    setIsSaving(true); setFormError("");
    try {
      await posApi.createCashMovement(shift.id, { ...movementPayload(), approval_token: approvalToken });
      setMovementAmount(0); setMovementReason(""); setMovementKey(requestKey("cash-movement")); setStep("summary");
      await refreshShift();
    } catch (error) {
      setFormError(errorMessage(error, "บันทึกรายการเงินสดไม่สำเร็จ"));
      if (approvalToken) throw error;
    } finally { setIsSaving(false); }
  }

  async function handleMovement(): Promise<void> {
    if (!summary || movementAmount <= 0 || movementReason.trim().length < 3) {
      setFormError("กรอกจำนวนเงินและเหตุผลอย่างน้อย 3 ตัวอักษร"); return;
    }
    if (movementAmount >= cashMovementApprovalThreshold) {
      setApproval({
        action: "pos.cash_movement.approve",
        requestPayload: { shift_id: shift.id, ...movementPayload() },
        reason: movementReason.trim(),
        description: `รายการ ${formatThaiCurrency(movementAmount)} ถึงเกณฑ์ที่ต้องให้ Manager อนุมัติ`,
        onApproved: async (token) => { setApproval(null); await executeMovement(token); },
      });
      return;
    }
    await executeMovement();
  }

  async function executeClose(approvalToken?: string): Promise<void> {
    if (!summary) return;
    setIsSaving(true); setFormError("");
    try {
      if (closeMode === "handover") {
        const response = await posApi.handoverShift(shift.id, { ...closePayload, approval_token: approvalToken });
        onHandover(response.data.data.shift);
      } else {
        const response = await posApi.closeShift(shift.id, { ...closePayload, approval_token: approvalToken });
        onClosed(response.data.data);
      }
      onOpenChange(false);
    } catch (error) {
      setFormError(errorMessage(error, "ปิดกะไม่สำเร็จ กรุณาโหลดสรุปจาก Server แล้วลองใหม่"));
      if (approvalToken) throw error;
    } finally { setIsSaving(false); }
  }

  async function handleClose(): Promise<void> {
    if (!online || !summary?.can_close) { setFormError("ยังปิดกะไม่ได้ กรุณาออนไลน์และแก้รายการค้างทั้งหมดก่อน"); return; }
    if (needsReason && (!reasonCode || note.trim().length < 3)) { setFormError("เมื่อเงินนับได้ไม่ตรง ต้องเลือกสาเหตุและใส่หมายเหตุอย่างน้อย 3 ตัวอักษร"); return; }
    if (needsManager) {
      setApproval({
        action: "pos.shift.variance.approve", requestPayload: { shift_id: shift.id, ...closePayload },
        reason: note.trim() || "Approve shift variance",
        description: `เงินสดต่าง ${formatThaiCurrency(difference)} ต้องให้ Manager คนอื่นอนุมัติ`,
        onApproved: async (token) => { setApproval(null); await executeClose(token); },
      });
      return;
    }
    await executeClose();
  }

  const headerStatus = !online
    ? { label: "ออฟไลน์ — ดู cache ได้ แต่ปิดกะไม่ได้", className: "bg-amber-100 text-amber-800", icon: WifiOff }
    : summaryQuery.isLoading
      ? { label: "กำลังยืนยันยอดกับ Server", className: "bg-blue-100 text-blue-700", icon: Loader2 }
      : summary?.can_close
        ? { label: "Server พร้อมให้ปิดกะ", className: "bg-emerald-100 text-emerald-700", icon: CheckCircle2 }
        : { label: "มีรายการต้องจัดการก่อนปิดกะ", className: "bg-red-100 text-red-700", icon: AlertTriangle };
  const StatusIcon = headerStatus.icon;

  return <>
    <Dialog open={open} onOpenChange={(next) => !isSaving && onOpenChange(next)}>
      <DialogContent className="max-w-5xl p-0">
        <div className="border-b border-slate-200 px-5 py-5 pr-16 md:px-7">
          <DialogHeader className="mb-0"><DialogTitle className="text-xl">จัดการกะพนักงาน · {shift.shift_number}</DialogTitle><DialogDescription>{operatorLabel ?? "พนักงานประจำกะ"} · เปิด {new Date(shift.opened_at).toLocaleString("th-TH")}</DialogDescription></DialogHeader>
          <div className={`mt-3 inline-flex min-h-11 items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold ${headerStatus.className}`}><StatusIcon className={`h-4 w-4 ${summaryQuery.isLoading ? "animate-spin" : ""}`} />{headerStatus.label}</div>
        </div>
        <div className="grid min-h-[560px] md:grid-cols-[220px_minmax(0,1fr)]">
          <nav className="border-b border-slate-200 bg-slate-50 p-3 md:border-b-0 md:border-r">
            <div className="grid grid-cols-3 gap-2 md:grid-cols-1">
              {([["summary", "สรุปกะ", Banknote], ["count", "นับเงินสด", CheckCircle2], ["movement", "เงินเข้า / ออก", ArrowDownToLine]] as const).map(([value, label, Icon]) => <button key={value} type="button" onClick={() => { setStep(value); setFormError(""); }} disabled={value === "movement" && !canCreateCashMovement} className={`flex min-h-12 items-center justify-center gap-2 rounded-xl px-3 text-sm font-semibold md:justify-start ${step === value ? "bg-blue-600 text-white" : "bg-white text-slate-700 hover:bg-slate-100"} disabled:cursor-not-allowed disabled:opacity-40`}><Icon className="h-5 w-5" />{label}</button>)}
            </div>
            <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-600"><p className="font-semibold text-slate-900">กติกาความปลอดภัย</p><p className="mt-1">ยอดคาดหวังและตัวบล็อกมาจาก Server เท่านั้น และกะที่ปิดแล้วเปิดซ้ำไม่ได้</p></div>
          </nav>
          <main className="p-4 md:p-6">
            {!online ? <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">ดูข้อมูลกะที่บันทึกในเครื่องได้ แต่เงินเข้า/ออก การอนุมัติ ส่งมอบ และปิดกะต้องทำเมื่อออนไลน์</div> : null}
            {summaryQuery.isError ? <div className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"><span>โหลดสรุปจาก Server ไม่สำเร็จ จึงยังปิดกะไม่ได้</span><Button variant="outline" className="min-h-11" onClick={() => void summaryQuery.refetch()}><RefreshCw className="mr-2 h-4 w-4" />ลองใหม่</Button></div> : null}

            {step === "summary" ? <div className="space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="text-lg font-bold text-slate-950">สรุปจาก Server</h3><p className="text-sm text-slate-500">Version {summary?.version ?? shift.version} · ไม่ใช้ยอดคำนวณจากหน้าจอ</p></div><Button variant="outline" className="min-h-11" disabled={!online || summaryQuery.isFetching} onClick={() => void refreshShift()}><RefreshCw className={`mr-2 h-4 w-4 ${summaryQuery.isFetching ? "animate-spin" : ""}`} />โหลดใหม่</Button></div>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{[["ยอดขายสุทธิ", summary?.net_sales], ["เงินสดคาดหวัง", summary?.expected_cash], ["คืนเงิน", summary?.refund_total], ["Void", summary?.void_total]].map(([label, value]) => <div key={label} className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs font-semibold text-slate-500">{label}</p><p className="mt-2 text-xl font-black text-slate-950">{formatThaiCurrency(Number(value ?? 0))}</p></div>)}</div>
              <div className="grid gap-4 lg:grid-cols-2">
                <section className="rounded-2xl border border-slate-200 p-4"><h4 className="font-bold">ช่องทางชำระ</h4><div className="mt-3 space-y-2">{Object.entries(summary?.payment_totals ?? {}).length ? Object.entries(summary?.payment_totals ?? {}).map(([method, amount]) => <div key={method} className="flex min-h-11 items-center justify-between rounded-xl bg-slate-50 px-3 text-sm"><span>{PAYMENT_LABELS[method] ?? method}</span><strong>{formatThaiCurrency(Number(amount))}</strong></div>) : <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">ยังไม่มียอดชำระในกะนี้</p>}</div></section>
                <section className="rounded-2xl border border-slate-200 p-4"><h4 className="font-bold">ความพร้อมปิดกะ</h4><div className="mt-3 space-y-2">{summary?.blockers.length ? summary.blockers.map((blocker) => <div key={blocker.code} className="flex min-h-11 items-center justify-between gap-3 rounded-xl bg-red-50 px-3 text-sm text-red-800"><span>{blocker.message}</span><strong>{blocker.count}</strong></div>) : <div className="flex min-h-11 items-center gap-2 rounded-xl bg-emerald-50 px-3 text-sm font-semibold text-emerald-700"><CheckCircle2 className="h-4 w-4" />รายการขาย/คืนเงิน/พักบิล/Outbox กระทบยอดครบ</div>}<div className="flex min-h-11 items-center justify-between rounded-xl bg-slate-50 px-3 text-sm"><span>สมุดบัญชี</span><strong>{summary?.journal.state === "matched" ? "ตรงกัน" : summary?.journal.state === "not_applicable" ? "ไม่ใช้ในขอบเขตนี้" : "รอตรวจสอบ"}</strong></div></div></section>
              </div>
              <Button className="h-12 w-full text-base" disabled={!online || !summary?.can_close} onClick={() => setStep("count")}>ไปนับเงินสด</Button>
            </div> : null}

            {step === "count" ? <div className="space-y-5">
              <div><h3 className="text-lg font-bold">นับเงินจริงในลิ้นชัก</h3><p className="text-sm text-slate-500">เริ่มทุกชนิดที่ศูนย์ เพื่อให้นับจริงก่อนดูส่วนต่าง</p></div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">{DENOMINATIONS.map((denomination) => <label key={denomination} className="rounded-xl border border-slate-200 p-3 text-sm font-semibold"><span>฿{denomination.toLocaleString("th-TH")}</span><input aria-label={`จำนวน ${denomination} บาท`} inputMode="numeric" min={0} type="number" value={counts[String(denomination)] ?? 0} onChange={(event) => setCounts((current) => ({ ...current, [String(denomination)]: Math.max(0, Number(event.target.value) || 0) }))} className="mt-2 h-12 w-full rounded-lg border border-slate-300 px-3 text-right text-lg" /></label>)}</div>
              <div className="grid gap-3 sm:grid-cols-3"><div className="rounded-xl bg-slate-100 p-4"><p className="text-xs text-slate-500">นับได้</p><p className="text-xl font-black">{formatThaiCurrency(countedCash)}</p></div><div className="rounded-xl bg-blue-50 p-4"><p className="text-xs text-blue-600">Server คาดหวัง</p><p className="text-xl font-black text-blue-900">{formatThaiCurrency(expectedCash)}</p></div><div className={`rounded-xl p-4 ${difference === 0 ? "bg-emerald-50 text-emerald-800" : Math.abs(difference) >= varianceSoftThreshold ? "bg-red-50 text-red-800" : "bg-amber-50 text-amber-800"}`}><p className="text-xs">ส่วนต่าง</p><p className="text-xl font-black">{formatThaiCurrency(difference)}</p></div></div>
              {needsReason ? <div className="grid gap-3 sm:grid-cols-2"><label className="text-sm font-semibold">สาเหตุส่วนต่าง<select value={reasonCode} onChange={(event) => setReasonCode(event.target.value as CloseReason)} className="mt-2 h-12 w-full rounded-xl border border-slate-300 px-3"><option value="">เลือกสาเหตุ</option><option value="count_short">เงินขาด</option><option value="count_over">เงินเกิน</option><option value="change_error">ทอนเงินคลาดเคลื่อน</option><option value="cash_movement">รายการเงินเข้า/ออก</option><option value="other">อื่น ๆ</option></select></label><label className="text-sm font-semibold">หมายเหตุ<textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} className="mt-2 min-h-12 w-full rounded-xl border border-slate-300 px-3 py-3" placeholder="อธิบายอย่างน้อย 3 ตัวอักษร" /></label></div> : null}
              {needsManager ? <div className="flex items-center gap-2 rounded-xl bg-violet-50 p-4 text-sm font-semibold text-violet-800"><ShieldCheck className="h-5 w-5" />ส่วนต่างถึงเกณฑ์ {formatThaiCurrency(varianceApprovalThreshold)} ต้องให้ Manager คนอื่นอนุมัติ</div> : null}
              {canHandover ? <div className="grid gap-2 sm:grid-cols-2"><button type="button" onClick={() => { setCloseMode("close"); setCloseKey(requestKey("shift-close")); }} className={`min-h-12 rounded-xl border px-4 text-sm font-bold ${closeMode === "close" ? "border-blue-600 bg-blue-50 text-blue-800" : "border-slate-200"}`}>ปิดกะและกลับหน้าหลัก</button><button type="button" onClick={() => { setCloseMode("handover"); setCloseKey(requestKey("shift-handover")); }} className={`min-h-12 rounded-xl border px-4 text-sm font-bold ${closeMode === "handover" ? "border-violet-600 bg-violet-50 text-violet-800" : "border-slate-200"}`}>ส่งมอบ Counter และออกจากพนักงาน</button></div> : null}
              {formError ? <div role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-800">{formError}</div> : null}
              <DialogFooter><Button variant="outline" className="h-12" onClick={() => setStep("summary")}>ย้อนกลับ</Button><Button className="h-12" disabled={isSaving || !online || !summary?.can_close} onClick={() => void handleClose()}>{isSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <LockKeyhole className="mr-2 h-4 w-4" />}{closeMode === "handover" ? "ยืนยันปิดกะและส่งมอบ" : "ยืนยันปิดกะ"}</Button></DialogFooter>
            </div> : null}

            {step === "movement" ? <div className="space-y-5">
              <div><h3 className="text-lg font-bold">เงินเข้า / เงินออกระหว่างกะ</h3><p className="text-sm text-slate-500">ทุกครั้งบันทึกผู้ขอ เหตุผล ผู้อนุมัติ และรายการบัญชี</p></div>
              <div className="grid grid-cols-2 gap-2"><button type="button" onClick={() => { setMovementType("cash_in"); setMovementReasonCode("change_fund"); }} className={`min-h-14 rounded-xl border text-sm font-bold ${movementType === "cash_in" ? "border-emerald-600 bg-emerald-50 text-emerald-800" : "border-slate-200"}`}><ArrowDownToLine className="mr-2 inline h-5 w-5" />เงินเข้า</button><button type="button" onClick={() => { setMovementType("cash_out"); setMovementReasonCode("cash_drop"); }} className={`min-h-14 rounded-xl border text-sm font-bold ${movementType === "cash_out" ? "border-orange-600 bg-orange-50 text-orange-800" : "border-slate-200"}`}><ArrowUpFromLine className="mr-2 inline h-5 w-5" />เงินออก</button></div>
              <div className="grid gap-3 sm:grid-cols-2"><label className="text-sm font-semibold">จำนวนเงิน<input type="number" min={0.01} inputMode="decimal" value={movementAmount || ""} onChange={(event) => setMovementAmount(Math.max(0, Number(event.target.value) || 0))} className="mt-2 h-12 w-full rounded-xl border border-slate-300 px-3 text-lg" /></label><label className="text-sm font-semibold">ประเภทเหตุผล<select value={movementReasonCode} onChange={(event) => setMovementReasonCode(event.target.value as MovementReason)} className="mt-2 h-12 w-full rounded-xl border border-slate-300 px-3">{movementType === "cash_in" ? <><option value="change_fund">เติมเงินทอน</option><option value="correction">แก้ไขรายการ</option><option value="other">อื่น ๆ</option></> : <><option value="cash_drop">นำเงินเก็บเข้าตู้เซฟ</option><option value="petty_cash">เงินสดย่อย</option><option value="supplier_payment">จ่ายผู้ขาย</option><option value="correction">แก้ไขรายการ</option><option value="other">อื่น ๆ</option></>}</select></label></div>
              <label className="block text-sm font-semibold">เหตุผล<textarea value={movementReason} onChange={(event) => setMovementReason(event.target.value)} maxLength={500} className="mt-2 min-h-24 w-full rounded-xl border border-slate-300 px-3 py-3" placeholder="ระบุรายละเอียดอย่างน้อย 3 ตัวอักษร" /></label>
              {movementAmount >= cashMovementApprovalThreshold ? <div className="rounded-xl bg-violet-50 p-4 text-sm font-semibold text-violet-800"><ShieldCheck className="mr-2 inline h-5 w-5" />ถึงเกณฑ์ {formatThaiCurrency(cashMovementApprovalThreshold)} ต้องให้ Manager คนอื่นอนุมัติ</div> : null}
              {summary?.cash_movements.length ? <div className="max-h-40 space-y-2 overflow-y-auto rounded-xl border border-slate-200 p-3">{summary.cash_movements.map((item) => <div key={item.id} className="flex min-h-11 items-center justify-between rounded-lg bg-slate-50 px-3 text-sm"><span>{item.movement_type === "cash_in" ? "เงินเข้า" : "เงินออก"} · {item.reason}</span><strong className={item.movement_type === "cash_in" ? "text-emerald-700" : "text-orange-700"}>{formatThaiCurrency(Number(item.amount))}</strong></div>)}</div> : null}
              {formError ? <div role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-800">{formError}</div> : null}
              <Button className="h-12 w-full" disabled={!online || isSaving || !canCreateCashMovement} onClick={() => void handleMovement()}>{isSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}บันทึกรายการและกระทบยอด</Button>
            </div> : null}
          </main>
        </div>
      </DialogContent>
    </Dialog>
    {approval ? <ManagerApprovalDialog open onOpenChange={(next) => { if (!next) setApproval(null); }} action={approval.action} requestPayload={approval.requestPayload} reason={approval.reason} description={approval.description} onApproved={approval.onApproved} /> : null}
  </>;
}
