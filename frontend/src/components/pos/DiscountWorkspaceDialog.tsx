import { BadgePercent, ShieldCheck, WifiOff } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

type Props = {
  open: boolean;
  subtotal: number;
  currentAmount: number;
  enabled: boolean;
  online: boolean;
  canOverride: boolean;
  cashierLimitPct: number;
  hardLimitPct: number;
  onOpenChange: (open: boolean) => void;
  onApply: (amount: number) => void;
};

function money(value: number): string {
  return new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(value);
}

export default function DiscountWorkspaceDialog({
  open,
  subtotal,
  currentAmount,
  enabled,
  online,
  canOverride,
  cashierLimitPct,
  hardLimitPct,
  onOpenChange,
  onApply,
}: Props): JSX.Element {
  const [mode, setMode] = useState<"amount" | "percent">("amount");
  const [value, setValue] = useState("0");

  useEffect(() => {
    if (!open) return;
    setMode("amount");
    setValue(String(currentAmount || 0));
  }, [currentAmount, open]);

  const preview = useMemo(() => {
    const raw = Math.max(0, Number(value) || 0);
    const requested = mode === "percent" ? subtotal * raw / 100 : raw;
    const hardMax = subtotal * Math.max(0, hardLimitPct) / 100;
    const amount = Math.min(requested, subtotal, hardMax);
    const percentage = subtotal > 0 ? amount * 100 / subtotal : 0;
    return {
      amount: Math.round(amount * 100) / 100,
      percentage,
      net: Math.max(0, subtotal - amount),
      exceedsCashier: percentage > cashierLimitPct,
      exceedsHard: requested > hardMax || requested > subtotal,
    };
  }, [cashierLimitPct, hardLimitPct, mode, subtotal, value]);

  const managerRequired = preview.exceedsCashier && !canOverride;
  const blocked = !enabled || subtotal <= 0 || preview.exceedsHard || (managerRequired && !online);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92dvh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl"><BadgePercent className="h-5 w-5 text-blue-600" />ส่วนลดทั้งบิล</DialogTitle>
          <DialogDescription>กำหนดเจตนาส่วนลดก่อนชำระ ยอดสุดท้ายและสิทธิ์จะถูกตรวจซ้ำโดย Server</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {!enabled ? <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-800">สาขาหรือสิทธิ์พนักงานไม่อนุญาตให้ใช้ส่วนลด</div> : null}
          {!online && managerRequired ? <div role="alert" className="flex gap-3 rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900"><WifiOff className="h-5 w-5 shrink-0" /><span>ส่วนลดนี้ต้องขอ Manager approval จึงใช้ขณะ Offline ไม่ได้</span></div> : null}

          <div className="grid grid-cols-2 gap-2" role="group" aria-label="รูปแบบส่วนลด">
            <Button className="h-12" variant={mode === "amount" ? "default" : "outline"} onClick={() => setMode("amount")}>จำนวนเงิน</Button>
            <Button className="h-12" variant={mode === "percent" ? "default" : "outline"} onClick={() => setMode("percent")}>เปอร์เซ็นต์</Button>
          </div>

          <label className="grid gap-2 text-sm font-bold text-slate-800">
            {mode === "amount" ? "ส่วนลด (บาท)" : "ส่วนลด (%)"}
            <Input
              className="h-14 text-xl font-bold"
              type="number"
              min={0}
              max={mode === "percent" ? 100 : subtotal}
              step={mode === "percent" ? 0.5 : 1}
              inputMode="decimal"
              value={value}
              onChange={(event) => setValue(event.target.value)}
            />
          </label>

          <div className="grid grid-cols-4 gap-2">
            {[5, 10, 15, 20].map((percentage) => (
              <button
                key={percentage}
                type="button"
                className="min-h-12 rounded-xl border border-slate-200 bg-white text-sm font-bold text-slate-700 hover:border-blue-300 hover:bg-blue-50"
                onClick={() => { setMode("percent"); setValue(String(percentage)); }}
              >
                {percentage}%
              </button>
            ))}
          </div>

          <div className="grid gap-3 sm:grid-cols-3" aria-live="polite">
            <div className="rounded-2xl border border-slate-200 p-4"><div className="text-xs font-semibold text-slate-500">ยอดก่อนลด</div><div className="mt-1 text-lg font-black">{money(subtotal)}</div></div>
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4"><div className="text-xs font-semibold text-amber-800">ส่วนลด</div><div className="mt-1 text-lg font-black text-amber-950">-{money(preview.amount)}</div><div className="text-xs text-amber-800">{preview.percentage.toFixed(2)}%</div></div>
            <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4"><div className="text-xs font-semibold text-blue-700">ยอดหลังลด</div><div className="mt-1 text-lg font-black text-blue-950">{money(preview.net)}</div></div>
          </div>

          {preview.exceedsHard ? <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-800">เกินเพดานสูงสุดของสาขา {hardLimitPct}% — Manager ก็อนุมัติเกินเพดานนี้ไม่ได้</div> : null}
          {managerRequired && !preview.exceedsHard ? <div className="flex gap-3 rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900"><ShieldCheck className="h-5 w-5 shrink-0" /><span>เกินเพดาน Cashier {cashierLimitPct}% ระบบจะขอ Manager คนอื่นอนุมัติเมื่อชำระเงิน</span></div> : null}
          <p className="rounded-xl bg-slate-100 px-4 py-3 text-xs text-slate-600">Structured discount reason ยังไม่มีในสัญญาปัจจุบัน จึงไม่แสดงช่องเหตุผลที่อาจทำให้เข้าใจผิดว่า Server บันทึกแล้ว เหตุผลจะถูกเก็บเมื่อเกิด Manager override เท่านั้น</p>
        </div>

        <DialogFooter>
          <Button className="h-12" variant="outline" onClick={() => onOpenChange(false)}>กลับ</Button>
          <Button className="h-14 min-w-40" disabled={blocked} onClick={() => { onApply(preview.amount); onOpenChange(false); }}>ใช้ส่วนลดนี้</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
