import { forwardRef, useState } from "react";
import { formatThaiCurrency, formatThaiDate } from "@/lib/cartUtils";
import { Button } from "@/components/ui/button";
import IssueTaxInvoiceDialog from "@/pages/etax/IssueTaxInvoiceDialog";
import { useAuthStore } from "@/stores/auth.store";
import type { SaleOrder } from "@/types/pos";

type CompanyInfo = {
  name: string;
  website?: string | null;
  phone?: string | null;
};

type BranchInfo = {
  name: string;
  phone?: string | null;
};

type ReceiptViewProps = {
  order: SaleOrder;
  company: CompanyInfo;
  branch: BranchInfo;
  cashier: string;
};

const paymentLabels: Record<string, string> = {
  cash: "เงินสด",
  promptpay: "PromptPay",
  credit_card: "บัตรเครดิต",
  bank_transfer: "โอนเงิน",
  other: "อื่นๆ"
};

const orderStatusLabels: Record<SaleOrder["status"], string> = {
  completed: "ขายสำเร็จ",
  voided: "Void แล้ว",
  refunded: "คืนเงินเต็มบิล",
  partially_refunded: "คืนเงินบางส่วน",
  pending_sync: "รอซิงก์"
};

function getVatSummaryLabel(order: SaleOrder): string {
  const hasExcluded = order.items.some((item) => item.vat_type === "excluded");
  const hasIncluded = order.items.some((item) => item.vat_type === "included");
  const hasExempt = order.items.some((item) => item.vat_type === "exempt");

  if (hasIncluded && hasExcluded) return "มีทั้ง VAT รวมในราคาและ VAT แยกนอก";
  if (hasExcluded) return "VAT แยกนอก";
  if (hasIncluded) return "ราคารวม VAT";
  if (hasExempt) return "สินค้ายกเว้น VAT";
  return "VAT";
}

const ReceiptView = forwardRef<HTMLDivElement, ReceiptViewProps>(function ReceiptView(
  { order, company, branch, cashier },
  ref,
) {
  const [issueDialogOpen, setIssueDialogOpen] = useState(false);
  const canIssueTaxInvoice = useAuthStore((state) => state.hasPermission("accounting.etax.generate"));
  const refundedAmount = Number(order.refund_amount ?? 0);
  const paymentHistory = order.payments ?? [];
  const refundPayments = paymentHistory.filter((payment) => Number(payment.amount) < 0);
  const salePayments = paymentHistory.filter((payment) => Number(payment.amount) >= 0);

  return (
    <>
      <div ref={ref} className="mx-auto max-w-sm bg-white p-4 text-sm text-gray-900 print:max-w-none print:p-0">
        <div className="space-y-1 text-center">
          <h2 className="text-lg font-bold">{company.name}</h2>
          <p>{branch.name}{branch.phone ? ` • ${branch.phone}` : ""}</p>
          <p className="font-semibold">ใบเสร็จรับเงิน</p>
          <p>เลขที่: {order.order_number}</p>
          <p>วันที่: {formatThaiDate(order.created_at)} น.</p>
          <p>พนักงาน: {cashier}</p>
          <p>สถานะ: {orderStatusLabels[order.status] ?? order.status}</p>
        </div>

        <div className="mt-4 border-t border-dashed border-gray-300 pt-3">
          <div className="grid grid-cols-[1fr_auto_auto_auto] gap-2 text-xs font-semibold">
            <span>สินค้า</span>
            <span className="text-right">จำนวน</span>
            <span className="text-right">ราคา</span>
            <span className="text-right">รวม</span>
          </div>
          <div className="mt-2 space-y-2">
            {order.items.map((item) => (
              <div key={item.id} className="grid grid-cols-[1fr_auto_auto_auto] gap-2">
                <div>
                  <p>{item.product_name}</p>
                  {item.variant_name ? <p className="text-xs text-gray-500">{item.variant_name}</p> : null}
                  {Number(item.refunded_qty ?? 0) > 0 ? (
                    <p className="text-xs text-amber-700">
                      คืนแล้ว {item.refunded_qty} ชิ้น
                      {Number(item.refunded_amount ?? 0) > 0 ? ` • ${formatThaiCurrency(Number(item.refunded_amount ?? 0))}` : ""}
                    </p>
                  ) : null}
                </div>
                <span className="text-right">{item.qty}</span>
                <span className="text-right">{formatThaiCurrency(Number(item.unit_price))}</span>
                <span className="text-right">{formatThaiCurrency(Number(item.subtotal))}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-4 space-y-1 border-t border-dashed border-gray-300 pt-3">
          <div className="flex justify-between"><span>ยอดรวม</span><span>{formatThaiCurrency(Number(order.subtotal))}</span></div>
          <div className="flex justify-between"><span>ส่วนลด</span><span>{formatThaiCurrency(Number(order.discount_amount))}</span></div>
          <div className="flex justify-between"><span>{getVatSummaryLabel(order)}</span><span>{formatThaiCurrency(Number(order.vat_amount))}</span></div>
          <div className="flex justify-between border-t border-gray-300 pt-2 text-base font-bold">
            <span>สุทธิ</span>
            <span>{formatThaiCurrency(Number(order.total_amount))}</span>
          </div>
          {refundedAmount > 0 ? (
            <>
              <div className="flex justify-between text-amber-700"><span>คืนเงินสะสม</span><span>{formatThaiCurrency(refundedAmount)}</span></div>
              <div className="flex justify-between"><span>สุทธิหลังหักคืน</span><span>{formatThaiCurrency(Number(order.total_amount) - refundedAmount)}</span></div>
            </>
          ) : null}
          <div className="flex justify-between"><span>รับเงิน</span><span>{formatThaiCurrency(Number(order.paid_amount))}</span></div>
          <div className="flex justify-between"><span>เงินทอน</span><span>{formatThaiCurrency(Number(order.change_amount))}</span></div>
          {order.customer_tax_id ? <div className="flex justify-between"><span>เลขผู้เสียภาษี</span><span>{order.customer_tax_id}</span></div> : null}
        </div>

        <div className="mt-4 border-t border-dashed border-gray-300 pt-3">
          <p className="font-semibold">การชำระเงิน</p>
          <div className="mt-2 space-y-1">
            {salePayments.map((payment) => (
              <div key={payment.id} className="flex items-start justify-between gap-3">
                <div>
                  <p>{paymentLabels[payment.payment_method] ?? "อื่นๆ"}</p>
                  {payment.reference_no ? <p className="text-xs text-gray-500">อ้างอิง: {payment.reference_no}</p> : null}
                </div>
                <p>{formatThaiCurrency(Number(payment.amount))}</p>
              </div>
            ))}
          </div>
          {refundPayments.length > 0 ? (
            <div className="mt-3 border-t border-dashed border-gray-300 pt-3">
              <p className="font-semibold text-amber-700">ประวัติคืนเงิน</p>
              <div className="mt-2 space-y-1">
                {refundPayments.map((payment) => (
                  <div key={payment.id} className="flex items-start justify-between gap-3 text-amber-700">
                    <div>
                      <p>{paymentLabels[payment.payment_method] ?? "อื่นๆ"}</p>
                      {payment.reference_no ? <p className="text-xs text-amber-700/80">อ้างอิง: {payment.reference_no}</p> : null}
                    </div>
                    <p>{formatThaiCurrency(Number(payment.amount))}</p>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        {order.note ? (
          <div className="mt-4 border-t border-dashed border-gray-300 pt-3">
            <p className="font-semibold">หมายเหตุ</p>
            <div className="mt-2 space-y-1 text-xs text-gray-600">
              {order.note.split("\n").filter(Boolean).map((line, index) => (
                <p key={`${order.id}-note-${index}`}>{line}</p>
              ))}
            </div>
          </div>
        ) : null}

        <div className="mt-4 border-t border-dashed border-gray-300 pt-3">
          <p className="font-semibold">ข้อมูลลูกค้า</p>
          <div className="mt-2 space-y-1 text-xs">
            <p>ชื่อลูกค้า: {order.customer_name || "ลูกค้าทั่วไป"}</p>
            {order.customer_phone ? <p>เบอร์โทร: {order.customer_phone}</p> : null}
            {order.customer_tax_id ? <p>เลขผู้เสียภาษี: {order.customer_tax_id}</p> : null}
          </div>
        </div>

        <div className="mt-4 border-t border-dashed border-gray-300 pt-3 text-center">
          <p>ขอบคุณที่ใช้บริการ</p>
          {company.website ? <p>{company.website}</p> : null}
          {company.phone ? <p>{company.phone}</p> : null}
        </div>

        {canIssueTaxInvoice ? (
          <div className="mt-4 border-t border-dashed border-gray-300 pt-3">
            <Button className="w-full" variant="outline" onClick={() => setIssueDialogOpen(true)}>
              ออกใบกำกับภาษี
            </Button>
          </div>
        ) : null}
      </div>

      <IssueTaxInvoiceDialog
        open={issueDialogOpen}
        onOpenChange={setIssueDialogOpen}
        initialSaleOrderId={order.id}
      />
    </>
  );
});

export default ReceiptView;
