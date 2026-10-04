import type { WapMenu, WapOrder } from "@/lib/wapApi";

const paymentLabels: Record<string, string> = {
  cash: "เงินสด",
  promptpay: "PromptPay",
  credit_card: "บัตรเครดิต",
  bank_transfer: "โอนเงิน",
  other: "อื่นๆ",
};

function money(value: number | string): string {
  return Number(value || 0).toLocaleString("th-TH", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

type TakeawayOrderSlipProps = {
  order: WapOrder | null;
  type: "customer" | "kitchen";
  employeeName: string;
  menu: WapMenu | null;
  promptpayQrDataUrl?: string | null;
};

export default function TakeawayOrderSlip({
  order,
  type,
  employeeName,
  menu,
  promptpayQrDataUrl = null,
}: TakeawayOrderSlipProps): JSX.Element {
  if (!order) return <div />;

  const isKitchen = type === "kitchen";
  const shopName = menu?.brand_name?.trim() || "Restaurant POS";
  const branchName = menu?.branch_name?.trim() || "ไม่ระบุสาขา";
  const branchLabel = branchName.startsWith("สาขา") ? branchName : `สาขา ${branchName}`;

  return (
    <div className="w-[280px] bg-white p-4 font-mono text-[12px] text-black">
      <div className="text-center">
        <p className="text-sm font-bold">{isKitchen ? "สลิปครัว" : "สลิปลูกค้า"}</p>
        <p className={`${isKitchen ? "mt-3" : "mt-2"} text-5xl font-black`}>{order.queue_display ?? "-"}</p>
        <p className="mt-2 text-sm font-bold">{shopName}</p>
        <p className="mt-0.5 text-[11px]">{branchLabel}</p>
        <p className="mt-2">เลขขาย {order.sale_order_number}</p>
        <p>พนักงาน {employeeName}</p>
        <p>{order.created_at ? new Date(order.created_at).toLocaleString("th-TH") : ""}</p>
      </div>
      <div className="my-3 border-t border-dashed border-black" />
      {order.customer_name || order.customer_phone ? (
        <div className="mb-2">
          {order.customer_name ? <p>ลูกค้า: {order.customer_name}</p> : null}
          {order.customer_phone ? <p>โทร: {order.customer_phone}</p> : null}
        </div>
      ) : null}
      <div className="space-y-2">
        {order.items.map((item) => (
          <div key={`${type}-${item.product_id}-${item.special_request ?? ""}`}>
            <div className="flex justify-between gap-2">
              <span>{item.qty} x {item.product_name}</span>
              {!isKitchen ? <span>{money(Number(item.unit_price) * item.qty)}</span> : null}
            </div>
            {item.special_request ? <p className="pl-3">* {item.special_request}</p> : null}
          </div>
        ))}
      </div>
      {!isKitchen ? (
        <>
          <div className="my-3 border-t border-dashed border-black" />
          <div className="space-y-1">
            <div className="flex justify-between"><span>รวม</span><span>{money(order.total_amount)}</span></div>
            <div className="flex justify-between"><span>รับเงิน</span><span>{money(order.paid_amount)}</span></div>
            <div className="flex justify-between"><span>ทอน</span><span>{money(order.change_amount)}</span></div>
            <div className="flex justify-between"><span>ชำระโดย</span><span>{paymentLabels[order.payment_method] ?? order.payment_method}</span></div>
          </div>
          <div className="my-3 border-t border-dashed border-black" />
          <p className="text-center text-[11px]">นำสลิปนี้ไปรับสินค้าที่เคาน์เตอร์</p>
          {promptpayQrDataUrl ? (
            <>
              <div className="my-3 border-t border-dashed border-black" />
              <div className="text-center">
                <p className="font-bold">PromptPay {branchLabel}</p>
                <img src={promptpayQrDataUrl} alt={`QR PromptPay ${branchName}`} className="mx-auto mt-1 h-36 w-36" />
                <p className="font-bold">สแกนเพื่อชำระเงิน</p>
                <p className="text-[10px]">ยอดชำระ ฿{money(order.total_amount)}</p>
                {menu?.promptpay_name ? <p className="text-[10px]">ชื่อบัญชี {menu.promptpay_name}</p> : null}
              </div>
            </>
          ) : null}
        </>
      ) : (
        <>
          <div className="my-3 border-t border-dashed border-black" />
          <p className="text-center text-[11px]">ทำสินค้าแล้วส่งกลับเคาน์เตอร์</p>
        </>
      )}
    </div>
  );
}
