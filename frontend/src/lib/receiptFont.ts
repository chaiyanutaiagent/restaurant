export const RECEIPT_FONT_FAMILY = '"Receipt Noto Thai", "Noto Sans Thai", Thonburi, Tahoma, sans-serif';
let ready: Promise<void> | undefined;

// Pixel probe catches blank canvas and the same missing-glyph box for Thai letters.
// The bundled OFL font is available offline; system Android Thai is the fallback.
export function assertThaiReceiptGlyphs(): void {
  const canvas = document.createElement("canvas");
  canvas.width = 64; canvas.height = 64;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("ไม่สามารถตรวจฟอนต์ไทยสำหรับพิมพ์ได้");
  const fingerprints = ["ก", "ข", "ญ", "฿"].map(glyph => {
    context.clearRect(0, 0, 64, 64);
    context.font = `400 32px ${RECEIPT_FONT_FAMILY}`;
    context.fillStyle = "#000";
    context.fillText(glyph, 4, 42);
    const pixels = context.getImageData(0, 0, 64, 64).data;
    const alpha = Array.from({ length: 64 * 64 }, (_, i) => pixels[i * 4 + 3]);
    if (!alpha.some(value => value > 0)) throw new Error("ฟอนต์ไทยยังไม่พร้อม กรุณาลองพิมพ์ใหม่");
    return alpha.join(",");
  });
  if (new Set(fingerprints).size !== fingerprints.length) throw new Error("อุปกรณ์ไม่มีฟอนต์ไทยสำหรับพิมพ์");
}

export function ensureReceiptFontReady(): Promise<void> {
  if (!ready) ready = (async () => {
    const font = new FontFace("Receipt Noto Thai", `url(${new URL("../assets/fonts/NotoSansThai.ttf", import.meta.url).href})`, { weight: "100 900" });
    try { document.fonts.add(await font.load()); } catch { /* Verify system fallback below. */ }
    await document.fonts.ready;
    await Promise.all([400, 700, 800].map(weight => document.fonts.load(`${weight} 24px ${RECEIPT_FONT_FAMILY}`, "กุ้งหมูย่าง ฿123.45")));
    assertThaiReceiptGlyphs();
  })().catch(error => { ready = undefined; throw error; });
  return ready;
}
