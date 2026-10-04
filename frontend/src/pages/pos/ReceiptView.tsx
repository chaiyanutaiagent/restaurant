import { forwardRef, useState } from "react";
import { formatThaiCurrency, formatThaiDate } from "@/lib/cartUtils";
import { Button } from "@/components/ui/button";
import IssueTaxInvoiceDialog from "@/pages/etax/IssueTaxInvoiceDialog";
import { useAuthStore } from "@/stores/auth.store";
import type { SaleOrder } from "@/types/pos";
import {
  formatReceiptQuantity,
  getReceiptVatSummaryLabel,
  receiptOrderStatusLabels,
  receiptPaymentLabels,
} from "@/lib/receiptFormat";

type CompanyInfo = {
  name: string;
  website?: string | null;
  phone?: string | null;
  logo_url?: string | null;
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
      <div ref={ref} className="pos-print-receipt mx-auto max-w-sm bg-white p-4 text-sm text-gray-900 print:max-w-none print:p-0">
        <div className="space-y-1 text-center print:space-y-0.5">
          {company.logo_url ? (
            <img src={company.logo_url} alt={`โลโก้ ${company.name}`} className="mx-auto mb-2 h-32 max-w-80 object-contain grayscale contrast-200 print:mb-1 print:h-16" />
          ) : null}
          <h2 className="text-lg font-bold print:text-sm print:leading-tight">{company.name}</h2>
          <p>{branch.name}{branch.phone ? ` • ${branch.phone}` : ""}</p>
          <p className="font-semibold">ใบเสร็จรับเงิน</p>
          <p>เลขที่: {order.order_number}</p>
          <p>วันที่: {formatThaiDate(order.created_at)} น.</p>
          <p>พนักงาน: {cashier}</p>
          <p>สถานะ: {receiptOrderStatusLabels[order.status] ?? order.status}</p>
        </div>

        <div className="mt-4 border-t border-dashed border-gray-300 pt-3 print:mt-2 print:pt-1.5">
          <table className="w-full table-fixed text-xs leading-tight">
            <colgroup>
              <col className="w-[40%]" />
              <col className="w-[14%]" />
              <col className="w-[23%]" />
              <col className="w-[23%]" />
            </colgroup>
            <thead>
              <tr className="font-semibold">
                <th className="pb-1 text-left">สินค้า</th>
                <th className="pb-1 text-right">จำนวน</th>
                <th className="pb-1 text-right">ราคา</th>
                <th className="pb-1 text-right">รวม</th>
              </tr>
            </thead>
            <tbody>
              {order.items.map((item) => (
                <tr key={item.id} className="align-top [&:not(:first-child)>td]:pt-1.5 print:[&:not(:first-child)>td]:pt-1">
                  <td className="break-words pr-1">
                    <p>{item.product_name}</p>
                    {item.variant_name ? <p className="text-xs text-gray-500">{item.variant_name}</p> : null}
                    {Number(item.refunded_qty ?? 0) > 0 ? (
                      <p className="text-xs text-amber-700">
                        คืนแล้ว {formatReceiptQuantity(Number(item.refunded_qty), item.unit_code)}{item.unit_code ? ` ${item.unit_code}` : ""}
                        {Number(item.refunded_amount ?? 0) > 0 ? ` • ${formatThaiCurrency(Number(item.refunded_amount ?? 0))}` : ""}
                      </p>
                    ) : null}
                  </td>
                  <td className="whitespace-nowrap text-right tabular-nums">{formatReceiptQuantity(Number(item.qty), item.unit_code)}</td>
                  <td className="whitespace-nowrap text-right tabular-nums">{formatThaiCurrency(Number(item.unit_price))}</td>
                  <td className="whitespace-nowrap text-right tabular-nums">{formatThaiCurrency(Number(item.subtotal))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-4 space-y-1 border-t border-dashed border-gray-300 pt-3 print:mt-2 print:space-y-0.5 print:pt-1.5">
          <div className="flex justify-between"><span>ยอดรวม</span><span>{formatThaiCurrency(Number(order.subtotal))}</span></div>
          <div className="flex justify-between"><span>ส่วนลด</span><span>{formatThaiCurrency(Number(order.discount_amount))}</span></div>
          <div className="flex justify-between"><span>{getReceiptVatSummaryLabel(order)}</span><span>{formatThaiCurrency(Number(order.vat_amount))}</span></div>
          <div className="flex justify-between border-t border-gray-300 pt-2 text-base font-bold print:pt-1 print:text-xs">
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

        <div className="mt-4 border-t border-dashed border-gray-300 pt-3 print:mt-2 print:pt-1.5">
          <p className="font-semibold">การชำระเงิน</p>
          <div className="mt-2 space-y-1 print:mt-1 print:space-y-0.5">
            {salePayments.map((payment) => (
              <div key={payment.id} className="flex items-start justify-between gap-3">
                <div>
                  <p>{receiptPaymentLabels[payment.payment_method] ?? "อื่นๆ"}</p>
                  {payment.reference_no ? <p className="text-xs text-gray-500">อ้างอิง: {payment.reference_no}</p> : null}
                </div>
                <p>{formatThaiCurrency(Number(payment.amount))}</p>
              </div>
            ))}
          </div>
          {refundPayments.length > 0 ? (
            <div className="mt-3 border-t border-dashed border-gray-300 pt-3 print:mt-1.5 print:pt-1.5">
              <p className="font-semibold text-amber-700">ประวัติคืนเงิน</p>
              <div className="mt-2 space-y-1 print:mt-1 print:space-y-0.5">
                {refundPayments.map((payment) => (
                  <div key={payment.id} className="flex items-start justify-between gap-3 text-amber-700">
                    <div>
                      <p>{receiptPaymentLabels[payment.payment_method] ?? "อื่นๆ"}</p>
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
          <div className="mt-4 border-t border-dashed border-gray-300 pt-3 print:mt-2 print:pt-1.5">
            <p className="font-semibold">หมายเหตุ</p>
            <div className="mt-2 space-y-1 text-xs text-gray-600 print:mt-1 print:space-y-0.5">
              {order.note.split("\n").filter(Boolean).map((line, index) => (
                <p key={`${order.id}-note-${index}`}>{line}</p>
              ))}
            </div>
          </div>
        ) : null}

        <div className="mt-4 border-t border-dashed border-gray-300 pt-3 print:mt-2 print:pt-1.5">
          <p className="font-semibold">ข้อมูลลูกค้า</p>
          <div className="mt-2 space-y-1 text-xs print:mt-1 print:space-y-0.5">
            <p>ชื่อลูกค้า: {order.customer_name || "ลูกค้าทั่วไป"}</p>
            {order.customer_phone ? <p>เบอร์โทร: {order.customer_phone}</p> : null}
            {order.customer_tax_id ? <p>เลขผู้เสียภาษี: {order.customer_tax_id}</p> : null}
          </div>
        </div>

        <div className="mt-4 border-t border-dashed border-gray-300 pt-3 text-center print:mt-2 print:pt-1.5">
          <p>ขอบคุณที่ใช้บริการ</p>
          {company.website ? <p>{company.website}</p> : null}
          {company.phone ? <p>{company.phone}</p> : null}
        </div>

        {canIssueTaxInvoice ? (
          <div className="mt-4 border-t border-dashed border-gray-300 pt-3 print:hidden">
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
