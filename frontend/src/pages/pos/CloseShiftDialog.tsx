import { useEffect, useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { formatThaiCurrency } from "@/lib/cartUtils";
import type { CashierShift } from "@/types/pos";

type CloseShiftDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  shift: CashierShift;
  expectedCashNow?: number;
  paymentSummary?: Array<{ method: string; amount: number }>;
  onConfirm: (closingCash: number, note: string) => Promise<void>;
};

export default function CloseShiftDialog({
  open,
  onOpenChange,
  shift,
  expectedCashNow,
  paymentSummary = [],
  onConfirm,
}: CloseShiftDialogProps): JSX.Element {
  const expectedCashValue = Number(expectedCashNow ?? shift.expected_cash ?? shift.opening_cash);
  const [closingCash, setClosingCash] = useState(expectedCashValue);
  const [note, setNote] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    setClosingCash(expectedCashValue);
  }, [expectedCashValue, shift.id]);

  const difference = useMemo(
    () => Number(closingCash) - expectedCashValue,
    [closingCash, expectedCashValue],
  );

  async function handleConfirm(): Promise<void> {
    setIsSaving(true);
    try {
      await onConfirm(closingCash, note);
      onOpenChange(false);
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>ปิดกะ</DialogTitle>
          <DialogDescription>ตรวจสอบยอดก่อนปิดกะขาย</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-lg bg-gray-50 p-3">กะ: {shift.shift_number}</div>
            <div className="rounded-lg bg-gray-50 p-3">เปิดเมื่อ: {new Date(shift.opened_at).toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" })} น.</div>
            <div className="rounded-lg bg-gray-50 p-3">ยอดขายรวม: {formatThaiCurrency(Number(shift.total_sales))}</div>
            <div className="rounded-lg bg-gray-50 p-3">จำนวนบิล: {shift.total_orders}</div>
            <div className="rounded-lg bg-gray-50 p-3">ยกเลิก: {shift.total_voids} บิล</div>
            <div className="rounded-lg bg-gray-50 p-3">เงินสดที่คาดไว้: {formatThaiCurrency(expectedCashValue)}</div>
          </div>

          {paymentSummary.length > 0 ? (
            <div className="rounded-lg border border-slate-200 p-3">
              <div className="mb-2 text-sm font-medium">สรุปยอดตามช่องทางชำระ</div>
              <div className="grid gap-2 sm:grid-cols-2">
                {paymentSummary.map((item) => (
                  <div key={item.method} className="rounded-md bg-slate-50 px-3 py-2 text-sm">
                    {item.method}: {formatThaiCurrency(item.amount)}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="space-y-2">
            <label className="text-sm font-medium">เงินสดที่นับได้</label>
            <input
              type="number"
              className="h-11 w-full rounded-md border border-gray-300 px-3"
              value={closingCash}
              onChange={(event) => setClosingCash(Number(event.target.value))}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">หมายเหตุ</label>
            <textarea
              className="min-h-24 w-full rounded-md border border-gray-300 px-3 py-2"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </div>

          <div className={`rounded-lg px-4 py-3 text-sm font-medium ${difference === 0 ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
            ส่วนต่าง: {formatThaiCurrency(difference)}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>ยกเลิก</Button>
          <Button onClick={() => void handleConfirm()} disabled={isSaving}>ปิดกะ</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
