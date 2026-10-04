import type { TakeawayReceipt } from "@/lib/takeawayApi";

const paymentLabels: Record<string, string> = {
  cash: "เงินสด",
  promptpay: "PromptPay",
  card: "บัตร",
  credit: "เครดิต",
  other: "อื่น ๆ",
};

function money(value: string | number): string {
  return Number(value || 0).toLocaleString("th-TH", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export default function TakeawayReceiptSlip({
  receipt,
  copyType,
}: {
  receipt: TakeawayReceipt | null;
  copyType: "customer" | "merchant";
}): JSX.Element {
  if (!receipt) return <div />;
  const payload = receipt.payload;
  return (
    <div className="w-[280px] bg-white p-4 font-mono text-[12px] text-black">
      <div className="text-center">
        <p className="text-sm font-black">Foodchainservice Takeaway</p>
        <p className="mt-1 font-bold">{copyType === "customer" ? "ใบเสร็จลูกค้า" : "สำเนาร้าน"}</p>
        <p className="mt-3 text-5xl font-black">{payload.queue_number ?? "OFF"}</p>
        <p className="mt-2">{receipt.receipt_number}</p>
        <p>{new Date(receipt.issued_at).toLocaleString("th-TH")}</p>
      </div>
      <div className="my-3 border-t border-dashed border-black" />
      <div className="space-y-2">
        {payload.items.map((item, index) => (
          <div key={`${item.sku}-${index}`}>
            <div className="flex justify-between gap-2">
              <span>{item.quantity} x {item.name}</span>
              <span>{money(item.line_total)}</span>
            </div>
            <p className="text-[10px] text-slate-600">{item.sku}</p>
          </div>
        ))}
      </div>
      <div className="my-3 border-t border-dashed border-black" />
      <div className="space-y-1">
        <div className="flex justify-between"><span>ก่อนภาษี</span><span>{money(payload.subtotal)}</span></div>
        <div className="flex justify-between"><span>ส่วนลด</span><span>-{money(payload.discount_amount)}</span></div>
        <div className="flex justify-between"><span>ภาษี</span><span>{money(payload.tax_amount)}</span></div>
        <div className="flex justify-between text-sm font-black"><span>สุทธิ</span><span>{money(payload.total_amount)}</span></div>
        <div className="flex justify-between"><span>ชำระโดย</span><span>{paymentLabels[payload.payment_method] ?? payload.payment_method}</span></div>
      </div>
      <div className="my-3 border-t border-dashed border-black" />
      <p className="text-center">นำเลขคิวไปรับสินค้าที่เคาน์เตอร์</p>
      {receipt.print_count > 0 ? <p className="mt-1 text-center text-[10px]">พิมพ์ซ้ำครั้งที่ {receipt.print_count + 1}</p> : null}
    </div>
  );
}
