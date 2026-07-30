import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { formatThaiCurrency, formatThaiDate } from "@/lib/cartUtils";
import type { ShiftSummary } from "@/types/report";

type ShiftSummaryDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  summary: ShiftSummary | null;
  onDownloadPdf: () => Promise<void>;
};

const PAYMENT_LABELS: Record<string, string> = {
  cash: "เงินสด",
  promptpay: "PromptPay",
  credit_card: "บัตรเครดิต",
  bank_transfer: "โอนเงิน",
  other: "อื่นๆ"
};

export default function ShiftSummaryDialog({
  open,
  onOpenChange,
  summary,
  onDownloadPdf
}: ShiftSummaryDialogProps): JSX.Element {
  if (!summary) {
    return <></>;
  }

  const expectedCash = Number(summary.shift.expected_cash ?? summary.shift.opening_cash);
  const closingCash = Number(summary.shift.closing_cash ?? 0);
  const cashDifference = Number(summary.shift.cash_difference ?? 0);
  const salesPreview = summary.sales.slice(-10).reverse();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>สรุปกะ {summary.shift.shift_number}</DialogTitle>
        </DialogHeader>

        <div className="space-y-6">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl border bg-white p-4">
              <p className="text-sm text-gray-500">ยอดขาย</p>
              <p className="mt-2 text-xl font-semibold">{formatThaiCurrency(Number(summary.daily_summary.total_amount))}</p>
            </div>
            <div className="rounded-xl border bg-white p-4">
              <p className="text-sm text-gray-500">จำนวนบิล</p>
              <p className="mt-2 text-xl font-semibold">{summary.daily_summary.total_orders}</p>
            </div>
            <div className="rounded-xl border bg-white p-4">
              <p className="text-sm text-gray-500">ยกเลิก</p>
              <p className="mt-2 text-xl font-semibold">{summary.voided.length}</p>
            </div>
            <div className="rounded-xl border bg-white p-4">
              <p className="text-sm text-gray-500">เงินสดส่วนต่าง</p>
              <p className={`mt-2 text-xl font-semibold ${cashDifference === 0 ? "text-green-600" : "text-red-600"}`}>
                {formatThaiCurrency(cashDifference)}
              </p>
            </div>
          </div>

          <div className="rounded-xl border bg-white p-4">
            <div className="grid gap-2 text-sm md:grid-cols-2">
              <p>พนักงาน: <span className="font-medium">{summary.cashier_name}</span></p>
              <p>สาขา: <span className="font-medium">{summary.branch_name}</span></p>
              <p>คลัง: <span className="font-medium">{summary.location_name}</span></p>
              <p>เปิดกะ: <span className="font-medium">{formatThaiDate(summary.shift.opened_at)}</span></p>
              <p>ปิดกะ: <span className="font-medium">{summary.shift.closed_at ? formatThaiDate(summary.shift.closed_at) : "ยังเปิดอยู่"}</span></p>
            </div>
          </div>

          <div className="rounded-xl border bg-white p-4">
            <h3 className="font-semibold text-gray-900">วิธีชำระเงิน</h3>
            <div className="mt-3 space-y-2 text-sm">
              {Object.entries(summary.by_payment_method).map(([method, amount]) => (
                <div key={method} className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2">
                  <span>{PAYMENT_LABELS[method] ?? method}</span>
                  <span className="font-medium">{formatThaiCurrency(Number(amount))}</span>
                </div>
              ))}
              <div className="flex items-center justify-between border-t pt-3 font-semibold">
                <span>รวม</span>
                <span>{formatThaiCurrency(Number(summary.daily_summary.total_amount))}</span>
              </div>
            </div>
          </div>

          {summary.shift.status === "closed" ? (
            <div className="rounded-xl border bg-white p-4">
              <h3 className="font-semibold text-gray-900">กระทบยอดเงินสด</h3>
              <div className="mt-3 grid gap-2 text-sm md:grid-cols-2">
                <p>เงินเปิดลิ้นชัก: <span className="font-medium">{formatThaiCurrency(Number(summary.shift.opening_cash))}</span></p>
                <p>ยอดเงินสดจากขาย: <span className="font-medium">{formatThaiCurrency(Number(summary.by_payment_method.cash ?? 0))}</span></p>
                <p>รวมที่คาดไว้: <span className="font-medium">{formatThaiCurrency(expectedCash)}</span></p>
                <p>เงินที่นับได้: <span className="font-medium">{formatThaiCurrency(closingCash)}</span></p>
                <p className={cashDifference === 0 ? "text-green-600" : "text-red-600"}>
                  ส่วนต่าง: <span className="font-medium">{formatThaiCurrency(cashDifference)}</span>
                </p>
              </div>
            </div>
          ) : null}

          <div className="rounded-xl border bg-white p-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-gray-900">รายการบิลล่าสุด</h3>
              <span className="text-sm text-gray-500">ดูตัวอย่าง 10 รายการจาก {summary.sales.length} บิล</span>
            </div>
            <div className="mt-3 overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-500">
                    <th className="px-2 py-2">เลขบิล</th>
                    <th className="px-2 py-2">เวลา</th>
                    <th className="px-2 py-2">ยอด</th>
                    <th className="px-2 py-2">วิธีชำระ</th>
                    <th className="px-2 py-2">สถานะ</th>
                  </tr>
                </thead>
                <tbody>
                  {salesPreview.map((order) => (
                    <tr key={order.id} className="border-b last:border-0">
                      <td className="px-2 py-2 font-mono">{order.order_number}</td>
                      <td className="px-2 py-2">{formatThaiDate(order.created_at)}</td>
                      <td className="px-2 py-2 text-right">{formatThaiCurrency(Number(order.total_amount))}</td>
                      <td className="px-2 py-2">{PAYMENT_LABELS[order.payments[0]?.payment_method ?? "other"] ?? "อื่นๆ"}</td>
                      <td className="px-2 py-2">{order.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            ปิด
          </Button>
          <Button onClick={() => void onDownloadPdf()}>พิมพ์ PDF</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
