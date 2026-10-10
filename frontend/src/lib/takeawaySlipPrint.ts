// Isolated iframe styles only. Do not change the proven POS/Restaurant styles.
export const TAKEAWAY_SLIP_PRINT_CSS = `
html, body { margin:0 !important; padding:0 !important; width:80mm !important;
  height:auto !important; overflow:visible !important; background:white !important; }
.takeaway-thermal-sheet, .takeaway-thermal-sheet * { visibility:visible !important; box-sizing:border-box !important; }
.takeaway-thermal-sheet { display:block !important; position:static !important;
  width:64mm !important; max-width:64mm !important; height:auto !important; max-height:none !important;
  margin:0 8mm !important; padding:2mm 0 15mm !important; overflow:visible !important;
  color:black !important; background:white !important; box-shadow:none !important;
  font-size:11px !important; line-height:1.3 !important; overflow-wrap:anywhere; }
.takeaway-thermal-sheet > div { width:100% !important; max-width:100% !important; padding:0 !important; }
.takeaway-thermal-sheet .flex > * { min-width:0; }
.takeaway-thermal-sheet .flex > :last-child:not(:only-child) { flex-shrink:0; max-width:100%; }
.takeaway-thermal-sheet p { white-space:pre-wrap; }
.takeaway-thermal-sheet img { max-width:100% !important; object-fit:contain; }
.takeaway-thermal-sheet [data-ordering-qr] { width:48mm !important; height:48mm !important; margin:3mm auto !important; display:block; }
`;

export async function waitForSlipImages(root: HTMLElement): Promise<void> {
  await root.ownerDocument.fonts.ready;
  await Promise.all(Array.from(root.querySelectorAll('img')).map(async image => {
    await image.decode();
    if (!image.naturalWidth) throw new Error('รูปหรือ QR ยังไม่พร้อม กรุณาลองพิมพ์ใหม่');
  }));
}

export async function printTakeawaySlipFrame(frame: HTMLIFrameElement): Promise<void> {
  const doc = frame.contentDocument;
  const win = frame.contentWindow;
  const root = doc?.querySelector<HTMLElement>('.takeaway-thermal-sheet');
  if (!doc || !win || !root) throw new Error('ไม่พบเอกสารสำหรับพิมพ์');
  await waitForSlipImages(root);
  const height = Math.max(root.scrollHeight, root.getBoundingClientRect().height) * 25.4 / 96;
  const pageHeight = Math.ceil((height + 2) / 5) * 5; // includes 15mm feed, no 300mm cap
  const style = doc.createElement('style');
  style.dataset.takeawaySlipPage = 'true';
  style.textContent = `@page { size:80mm ${pageHeight}mm; margin:0; }`;
  doc.head.appendChild(style);
  win.focus();
  win.print();
}
