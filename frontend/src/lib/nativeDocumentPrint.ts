import { Capacitor, registerPlugin } from "@capacitor/core";

const printer = registerPlugin<{ printHtml(options: { html: string }): Promise<void> }>("PosDocumentPrint");
const available = () => import.meta.env.VITE_APP_SURFACE === "pos-uat" && Capacitor.isPluginAvailable("PosDocumentPrint");

async function printDocument(doc: Document): Promise<void> {
  const copy = doc.documentElement.cloneNode(true) as HTMLElement;
  const styles = Array.from(doc.styleSheets).map((sheet) => {
    try { return Array.from(sheet.cssRules).map((rule) => rule.cssText).join("\n"); }
    catch { return ""; }
  }).join("\n");
  const originals = doc.querySelectorAll("canvas");
  copy.querySelectorAll("canvas").forEach((canvas, index) => {
    const img = doc.createElement("img"); img.src = originals[index].toDataURL(); canvas.replaceWith(img);
  });
  copy.querySelectorAll("script,iframe,link,base,style").forEach((element) => element.remove());
  const style = doc.createElement("style"); style.textContent = styles; copy.querySelector("head")?.append(style);
  await printer.printHtml({ html: `<!doctype html>${copy.outerHTML}` });
}

// react-to-print supplies an already prepared receipt document, not the POS screen.
export const nativeReceiptPrint = available() ? async (frame: HTMLIFrameElement): Promise<void> => {
  if (!frame.contentDocument) throw new Error("ไม่พบเอกสารสำหรับพิมพ์");
  await printDocument(frame.contentDocument);
} : undefined;

export function installNativeDocumentPrint(): void {
  if (!available()) return;
  window.print = () => { void printDocument(document).catch((error) => window.alert(`เปิดหน้าพิมพ์ไม่ได้: ${error.message}`)); };
}
