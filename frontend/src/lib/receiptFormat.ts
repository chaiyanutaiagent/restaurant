import type { SaleOrder } from "@/types/pos";

export const receiptPaymentLabels: Record<string, string> = {
  cash: "เงินสด",
  promptpay: "PromptPay",
  credit_card: "บัตรเครดิต",
  bank_transfer: "โอนเงิน",
  other: "อื่นๆ",
};

export const receiptOrderStatusLabels: Record<SaleOrder["status"], string> = {
  completed: "ขายสำเร็จ",
  voided: "Void แล้ว",
  refunded: "คืนเงินเต็มบิล",
  partially_refunded: "คืนเงินบางส่วน",
  pending_sync: "รอซิงก์",
};

const WEIGHT_UNIT_CODES = new Set([
  "kg", "kgs", "kilogram", "kilograms", "กก", "กิโลกรัม",
  "g", "gr", "gram", "grams", "กรัม",
  "mg", "milligram", "milligrams", "มก",
  "lb", "lbs", "pound", "pounds",
  "oz", "ounce", "ounces",
]);

export function isReceiptWeightUnit(unitCode: string | null): boolean {
  if (!unitCode) return false;
  const normalized = unitCode.trim().toLowerCase().replace(/[.\s_-]/g, "");
  return WEIGHT_UNIT_CODES.has(normalized);
}

export function formatReceiptQuantity(qty: number, unitCode: string | null): string {
  const value = Number(qty);
  if (!Number.isFinite(value)) return "0";
  return new Intl.NumberFormat("th-TH", isReceiptWeightUnit(unitCode)
    ? { minimumFractionDigits: 2, maximumFractionDigits: 2 }
    : { maximumFractionDigits: 0 }).format(value);
}

export function getReceiptVatSummaryLabel(order: SaleOrder): string {
  const hasExcluded = order.items.some((item) => item.vat_type === "excluded");
  const hasIncluded = order.items.some((item) => item.vat_type === "included");
  const hasExempt = order.items.some((item) => item.vat_type === "exempt");

  if (hasIncluded && hasExcluded) return "มีทั้ง VAT รวมในราคาและ VAT แยกนอก";
  if (hasExcluded) return "VAT แยกนอก";
  if (hasIncluded) return "ราคารวม VAT";
  if (hasExempt) return "สินค้ายกเว้น VAT";
  return "VAT";
}
