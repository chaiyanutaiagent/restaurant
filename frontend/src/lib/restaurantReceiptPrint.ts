export const RESTAURANT_RECEIPT_BOTTOM_FEED_MM = 15;

type ReceiptContent = {
  items: Array<{ product_name: string; special_request?: string | null }>;
  header?: string | null;
  footer?: string | null;
  note?: string | null;
  customerName?: string | null;
  customerPhone?: string | null;
  paymentReference?: string | null;
  hasLogo?: boolean;
};

// Conservative fallback; the print iframe is also measured at its actual 64mm
// printable width after fonts/images load. Do not cap long roll receipts.
export function estimateRestaurantReceiptPageHeightMm(content: ReceiptContent): number {
  const lines = (value?: string | null, width = 24) => value
    ? value.split('\n').reduce((sum, line) => sum + Math.max(1, Math.ceil(Array.from(line).length / width)), 0)
    : 0;
  const itemMm = content.items.reduce((sum, item) => sum + 3
    + Math.max(1, lines(item.product_name, 20)) * 4
    + 4 + lines(item.special_request, 24) * 3.5, 0);
  const extras = lines(content.header) * 5 + lines(content.footer) * 4
    + lines(content.note) * 4 + lines(content.customerName) * 4
    + lines(content.customerPhone) * 4 + lines(content.paymentReference) * 4;
  return Math.ceil((65 + itemMm + extras + (content.hasLogo ? 36 : 0)
    + RESTAURANT_RECEIPT_BOTTOM_FEED_MM) / 5) * 5;
}

// Scoped to Restaurant's isolated print iframe; Retail styles are unchanged.
export const RESTAURANT_RECEIPT_PRINT_CSS = `
  html, body { margin: 0 !important; padding: 0 !important; width: 80mm !important;
    height: auto !important; overflow: visible !important; background: white !important; }
  .restaurant-print-receipt, .restaurant-print-receipt * {
    visibility: visible !important; box-sizing: border-box !important; }
  .restaurant-print-receipt {
    position: static !important; display: block !important; width: 64mm !important;
    max-width: 64mm !important; height: auto !important; max-height: none !important;
    margin: 0 8mm !important; padding: 2mm 0 ${RESTAURANT_RECEIPT_BOTTOM_FEED_MM}mm !important;
    overflow: visible !important; border: 0 !important; border-radius: 0 !important;
    box-shadow: none !important; color: black !important; background: white !important;
    font-size: 11px !important; line-height: 1.3 !important; overflow-wrap: anywhere;
  }
  .restaurant-print-receipt .text-xs { font-size: 10px !important; line-height: 1.3 !important; }
  .restaurant-print-receipt .grid { grid-template-columns: minmax(0, 1fr) auto !important; gap: 2mm !important; }
  .restaurant-print-receipt .flex { gap: 2mm; }
  .restaurant-print-receipt .flex > *, .restaurant-print-receipt .grid > * { min-width: 0; }
  .restaurant-print-receipt p { white-space: pre-wrap; }
  .restaurant-print-receipt img { max-width: 100% !important; object-fit: contain; }
  .restaurant-receipt-footer { break-inside: avoid; }
`;

export async function printRestaurantReceipt(iframe: HTMLIFrameElement, estimatedHeightMm: number): Promise<void> {
  const doc = iframe.contentDocument;
  const win = iframe.contentWindow;
  const receipt = doc?.querySelector<HTMLElement>('.restaurant-print-receipt');
  if (!doc || !win || !receipt) throw new Error('ไม่พบใบเสร็จสำหรับพิมพ์');
  await doc.fonts.ready;
  await Promise.all(Array.from(receipt.querySelectorAll('img')).map(img => img.decode().catch(() => undefined)));
  // 96 CSS px = 25.4mm; scrollHeight includes the 15mm cutter feed padding.
  const measuredMm = Math.max(receipt.scrollHeight, receipt.getBoundingClientRect().height) * 25.4 / 96;
  const heightMm = Math.ceil((Math.max(estimatedHeightMm, measuredMm) + 2) / 5) * 5;
  const style = doc.createElement('style');
  style.dataset.restaurantReceiptPage = 'true';
  style.textContent = `@page { size: 80mm ${heightMm}mm; margin: 0; }`;
  doc.head.appendChild(style);
  win.focus();
  win.print();
}
