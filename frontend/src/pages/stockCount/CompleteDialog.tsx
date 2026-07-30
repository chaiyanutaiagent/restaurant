import { useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";
import { stockCountApi } from "@/lib/stockCountApi";
import { formatThaiCurrency } from "@/lib/cartUtils";
import type { CountSession } from "@/types/stockCount";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  session: CountSession;
  onCompleted: () => Promise<void> | void;
};

export default function CompleteDialog({ open, onOpenChange, session, onCompleted }: Props): JSX.Element {
  const { toast } = useToast();
  const [applyAdjustments, setApplyAdjustments] = useState(true);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const countedItems = session.items.filter((item) => item.actual_qty !== null);
  const uncountedItems = session.items.filter((item) => item.actual_qty === null);
  const varianceItems = useMemo(
    () => session.items.filter((item) => item.actual_qty !== null && Number(item.variance_qty ?? 0) !== 0),
    [session.items]
  );
  const totalVarianceValue = varianceItems.reduce(
    (sum, item) => sum + Math.abs(Number(item.variance_value ?? 0)),
    0
  );

  async function handleComplete(): Promise<void> {
    if (uncountedItems.length > 0) {
      toast({
        title: "ยังมีสินค้าที่ยังไม่ได้นับ",
        description: `ค้างอยู่ ${uncountedItems.length} รายการ`,
        variant: "destructive"
      });
      return;
    }

    setSubmitting(true);
    try {
      await stockCountApi.completeSession(session.id, {
        apply_adjustments: applyAdjustments,
        note: note || undefined
      });
      toast({ title: "ปิด Session แล้ว" });
      onOpenChange(false);
      await onCompleted();
    } catch (error) {
      toast({
        title: "ปิด Session ไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>บันทึกและปิด Session</DialogTitle>
          <DialogDescription>ตรวจสอบความครบถ้วนก่อนยืนยันปิด session</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
            <p className="font-medium text-gray-900">นับแล้ว {countedItems.length} จาก {session.total_items} รายการ</p>
            {uncountedItems.length > 0 ? (
              <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                <p className="font-medium">สินค้าที่ยังไม่ได้นับ: {uncountedItems.length} รายการ</p>
                <div className="mt-2 space-y-1">
                  {uncountedItems.slice(0, 5).map((item) => (
                    <p key={item.id}>- {item.product_name}</p>
                  ))}
                </div>
              </div>
            ) : null}
          </div>

          <div className="rounded-lg border border-gray-200 p-4">
            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                checked={applyAdjustments}
                onChange={(event) => setApplyAdjustments(event.target.checked)}
              />
              <div className="text-sm">
                <p className="font-medium text-gray-900">ปรับสต็อกอัตโนมัติ</p>
                <p className="text-gray-500">
                  {applyAdjustments
                    ? "เปิด: ระบบจะปรับสต็อกตามผลที่นับจริง"
                    : "ปิด: บันทึกผลการนับโดยไม่ปรับสต็อก"}
                </p>
              </div>
            </label>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">หมายเหตุ</label>
            <textarea
              className="min-h-24 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="หมายเหตุเพิ่มเติม"
            />
          </div>

          {varianceItems.length > 0 ? (
            <div className="rounded-lg border border-orange-200 bg-orange-50 p-4">
              <p className="font-medium text-orange-900">พบผลต่าง {varianceItems.length} รายการ</p>
              <div className="mt-3 space-y-2 text-sm">
                {varianceItems.map((item) => (
                  <div key={item.id} className="flex items-center justify-between gap-3">
                    <span className="truncate">{item.product_name}</span>
                    <span className="font-medium">
                      ผลต่าง {Number(item.variance_qty ?? 0)} | {formatThaiCurrency(Math.abs(Number(item.variance_value ?? 0)))}
                    </span>
                  </div>
                ))}
              </div>
              <p className="mt-3 font-semibold text-orange-900">
                Total variance value: {formatThaiCurrency(totalVarianceValue)}
              </p>
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            ปิด
          </Button>
          <Button onClick={() => void handleComplete()} disabled={submitting || uncountedItems.length > 0}>
            {submitting ? "กำลังบันทึก..." : "ยืนยันปิด Session"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
