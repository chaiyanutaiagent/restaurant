// Test-only entry, not referenced by production HTML or routes.
import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { useReactToPrint } from "react-to-print";
import QRCode from "qrcode";
import TakeawayReceiptSlip from "../src/components/takeaway/TakeawayReceiptSlip";
import { Slip } from "../src/pages/restaurant/WapOrderPage";
import { printTakeawaySlipFrame, TAKEAWAY_SLIP_PRINT_CSS } from "../src/lib/takeawaySlipPrint";
import { buildEscPosTakeawayReceiptBytes, buildEscPosWapOrderSlipBytes } from "../src/lib/escPosPrinter";
import type { TakeawayReceipt } from "../src/lib/takeawayApi";
import type { WapOrder, WapMenu } from "../src/lib/wapApi";
import "../src/index.css";

const params = new URLSearchParams(location.search);
const count = params.get("long") ? 80 : 2;
const kind = params.get("kind") ?? "customer";
const name = count > 2 ? "หมูย่างกะทิชื่อสินค้าไทยยาวมากทดสอบการตัดบรรทัดพิเศษพร้อมข้าวเหนียว" : "หมูย่าง";
export const receipt = { id: "receipt", order_id: "order", receipt_number: "TR-PRINT-TEST", issued_at: "2026-10-10T12:00:00Z", print_count: 0,
  last_printed_at: null, last_printed_copy: null,
  payload: { order_number: "TW-PRINT-TEST", queue_number: 88, subtotal: "100", discount_amount: "0", tax_amount: "7", total_amount: "107", payment_method: "cash",
    items: Array.from({ length: count }, (_, i) => ({ sku: `TEST-${i}`, name, quantity: "1", line_total: "10" })) },
} as TakeawayReceipt;
export const order = { session_id: "session", order_id: "order", sale_order_id: "sale", sale_order_number: "SO-PRINT-TEST", queue_display: "088", total_amount: 107, paid_amount: 120, change_amount: 13,
  payment_method: "promptpay", created_at: receipt.issued_at, customer_name: "ลูกค้าทดสอบ", customer_phone: null,
  items: receipt.payload.items.map((item, i) => ({ product_id: `product-${i}`, product_name: item.name, qty: 1, unit_price: 10,
    special_request: count > 2 ? "ไม่ใส่กระเทียมและเครื่องปรุงรสจัด\nแยกน้ำซุปใส่ถุงต่างหาก" : "ไม่เผ็ด" })),
} as WapOrder;
const menu = { brand_name: "แบรนด์ทดสอบ", branch_name: "สาขาทดสอบ", promptpay_name: "บัญชีทดสอบ" } as WapMenu;
function Fixture() {
  const ref = useRef<HTMLDivElement>(null);
  const [qr, setQr] = useState<string | null>(null);
  useEffect(() => { void QRCode.toDataURL("https://example.invalid/test-only").then(setQr); }, []);
  const print = useReactToPrint({ contentRef: ref, pageStyle: TAKEAWAY_SLIP_PRINT_CSS, print: printTakeawaySlipFrame });
  useEffect(() => {
    (window as any).buildRaster = async (copy: "customer" | "merchant" | "kitchen" | "wap-customer") => {
      const texts: string[] = [];
      const original = CanvasRenderingContext2D.prototype.fillText;
      CanvasRenderingContext2D.prototype.fillText = function(text, ...args: [number, number, number?]) { texts.push(text); return original.call(this, text, ...args); };
      try {
        const bytes = copy === "kitchen" || copy === "wap-customer" ? await buildEscPosWapOrderSlipBytes(order, copy === "kitchen" ? "kitchen" : "customer", "Tester", menu, null)
          : await buildEscPosTakeawayReceiptBytes(receipt, copy);
        const widthBytes = bytes[6] + bytes[7] * 256;
        const height = bytes[8] + bytes[9] * 256;
        let lastInkRow = -1;
        for (let y = 0; y < height; y++) {
          if (bytes.subarray(10 + y * widthBytes, 10 + (y + 1) * widthBytes).some(v => v !== 0)) lastInkRow = y;
        }
        return { widthBytes, height, blankRows: height - lastInkRow - 1, footerText: texts.slice(-6), suffix: Array.from(bytes.slice(-7)), size: bytes.length };
      } finally { CanvasRenderingContext2D.prototype.fillText = original; }
    };
  }, []);
  return <><h1>DO NOT PRINT PAGE UI</h1><button disabled={!qr} onClick={() => print()}>Print fixture</button>
    <div ref={ref} className="takeaway-thermal-sheet">
      {kind.startsWith("wap") ? <Slip order={order} type={kind === "wap-kitchen" ? "kitchen" : "customer"} employeeName="Tester" menu={menu} promptpayQrDataUrl={kind === "wap-customer" ? qr : null} />
        : <TakeawayReceiptSlip receipt={receipt} copyType={kind === "merchant" ? "merchant" : "customer"} />}
    </div></>;
}
createRoot(document.getElementById("root")!).render(<Fixture />);
