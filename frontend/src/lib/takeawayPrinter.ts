import { Capacitor, registerPlugin } from "@capacitor/core";
import type { TakeawayReceipt } from "@/lib/takeawayApi";
import type { WapMenu, WapOrder } from "@/lib/wapApi";
import {
  buildEscPosReceiptBytes,
  buildEscPosCashDrawerPulse,
  buildEscPosTakeawayReceiptBytes,
  buildEscPosPreparationBytes,
  buildEscPosLongTestBytes,
  buildEscPosTextReceiptBytes,
  buildEscPosWapOrderSlipBytes,
  getEscPosPrinterStatus,
  printEscPosBytes,
  type EscPosReceiptBranch,
  type EscPosReceiptCompany,
} from "@/lib/escPosPrinter";
import type { SaleOrder } from "@/types/pos";

export type TakeawayPrinterDevice = { name: string; address: string };

type TakeawayPrinterNative = {
  requestBluetoothPermission(): Promise<void>;
  pairedDevices(): Promise<{ devices: TakeawayPrinterDevice[] }>;
  printBase64(options: { address: string; data: string }): Promise<void>;
  getCapabilities(options: { address: string }): Promise<{ protocolVersion: number; autoCutter: string; cutCommand: string }>;
  testCutter(options: { address: string }): Promise<{ testId: string; outcome: string }>;
  confirmCutter(options: { address: string; testId?: string; fullCut: boolean }): Promise<void>;
  printBatch(options: { address: string; jobId: string; copies: Array<{ copyType: "customer" | "preparation"; data: string }> }): Promise<{ outcome: string }>;
};

const nativePrinter = registerPlugin<TakeawayPrinterNative>("TakeawayPrinter");
const PRINTER_KEY = "foodchainservice-takeaway-printer";

export function isNativeTakeawayPrinterAvailable(): boolean {
  return Capacitor.isNativePlatform() && Capacitor.getPlatform() === "android";
}

export function savedTakeawayPrinter(): TakeawayPrinterDevice | null {
  const raw = window.localStorage.getItem(PRINTER_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as TakeawayPrinterDevice;
    return parsed.address ? parsed : null;
  } catch {
    return null;
  }
}

export function saveTakeawayPrinter(device: TakeawayPrinterDevice): void {
  window.localStorage.setItem(PRINTER_KEY, JSON.stringify(device));
}

export async function takeawayCutterCapability(): Promise<boolean> {
  const printer = savedTakeawayPrinter();
  if (!printer || !isNativeTakeawayPrinterAvailable()) return false;
  try {
    const status = await nativePrinter.getCapabilities({ address: printer.address });
    return status.protocolVersion >= 2 && status.autoCutter === "operator_verified_full_cut";
  } catch { return false; }
}

export async function testTakeawayCutter(): Promise<string> {
  const printer = savedTakeawayPrinter();
  if (!printer || !isNativeTakeawayPrinterAvailable()) throw new Error("ต้องเลือกเครื่องพิมพ์ Bluetooth ใน Android ก่อน");
  return (await nativePrinter.testCutter({ address: printer.address })).testId;
}

export async function confirmTakeawayCutter(fullCut: boolean, testId?: string): Promise<void> {
  const printer = savedTakeawayPrinter();
  if (!printer) throw new Error("ยังไม่ได้เลือกเครื่องพิมพ์");
  await nativePrinter.confirmCutter({ address: printer.address, testId, fullCut });
}

export async function printTakeawayBatch(receipt: TakeawayReceipt, copies: Array<"customer" | "preparation">, attemptId: string): Promise<void> {
  if (!await takeawayCutterCapability()) throw new Error("ยังยืนยันการตัดกระดาษจริงไม่ได้ กรุณาทดสอบ Auto Cutter ในตั้งค่าเครื่องพิมพ์");
  const printer = savedTakeawayPrinter()!;
  const documents = [];
  for (const copyType of copies) {
    const bytes = copyType === "customer" ? await buildEscPosTakeawayReceiptBytes(receipt, "customer") : await buildEscPosPreparationBytes(receipt);
    documents.push({ copyType, data: encodeBase64(bytes) });
  }
  // Exactly ONE native call, ONE socket, customer + full cut + preparation + full cut.
  await nativePrinter.printBatch({ address: printer.address, jobId: attemptId, copies: documents });
}

export async function pairedTakeawayPrinters(): Promise<TakeawayPrinterDevice[]> {
  if (!isNativeTakeawayPrinterAvailable()) return [];
  await nativePrinter.requestBluetoothPermission();
  return (await nativePrinter.pairedDevices()).devices;
}

function encodeBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const value of bytes) binary += String.fromCharCode(value);
  return window.btoa(binary);
}

async function printNativeBytes(bytes: Uint8Array): Promise<boolean> {
  const printer = savedTakeawayPrinter();
  if (!printer || !isNativeTakeawayPrinterAvailable()) return false;
  await nativePrinter.printBase64({ address: printer.address, data: encodeBase64(bytes) });
  return true;
}

async function configuredTransport(): Promise<"native" | "web" | null> {
  if (isNativeTakeawayPrinterAvailable() && savedTakeawayPrinter()) return "native";
  return (await getEscPosPrinterStatus()).paired ? "web" : null;
}

async function sendConfiguredBytes(bytes: Uint8Array, transport: "native" | "web"): Promise<void> {
  if (transport === "native") {
    if (!await printNativeBytes(bytes)) throw new Error("ยังไม่ได้เลือกเครื่องพิมพ์ Bluetooth");
    return;
  }
  await printEscPosBytes(bytes);
}

function escPosText(lines: string[]): string {
  return `${lines.join("\n")}\n\n\n`;
}

export function takeawayReceiptText(
  receipt: TakeawayReceipt,
  copyType: "customer" | "merchant",
): string {
  const payload = receipt.payload;
  const rows = payload.items.flatMap((item) => [
    `${item.quantity} x ${item.name}`,
    `  ${item.sku}  ${Number(item.line_total).toFixed(2)}`,
  ]);
  return escPosText([
    "FOODCHAINSERVICE TAKEAWAY",
    copyType === "customer" ? "CUSTOMER RECEIPT" : "MERCHANT COPY",
    `QUEUE ${payload.queue_number ?? "OFF"}`,
    receipt.receipt_number,
    "--------------------------------",
    ...rows,
    "--------------------------------",
    `SUBTOTAL ${Number(payload.subtotal).toFixed(2)}`,
    `DISCOUNT ${Number(payload.discount_amount).toFixed(2)}`,
    `TAX      ${Number(payload.tax_amount).toFixed(2)}`,
    `TOTAL    ${Number(payload.total_amount).toFixed(2)}`,
    `PAYMENT  ${payload.payment_method.toUpperCase()}`,
    "PLEASE COLLECT AT THE COUNTER",
  ]);
}

export async function printTakeawayRaw(address: string, content: string): Promise<void> {
  const bytes = await buildEscPosTextReceiptBytes(content);
  await nativePrinter.printBase64({ address, data: encodeBase64(bytes) });
}

export async function printTakeawayReceipt(
  receipt: TakeawayReceipt,
  copyType: "customer" | "merchant",
): Promise<boolean> {
  const transport = await configuredTransport();
  if (!transport) return false;
  const bytes = await buildEscPosTakeawayReceiptBytes(receipt, copyType);
  await sendConfiguredBytes(bytes, transport);
  return true;
}

export async function printConfiguredSaleReceipt(
  order: SaleOrder,
  company: EscPosReceiptCompany,
  branch: EscPosReceiptBranch,
  cashier: string,
): Promise<boolean> {
  const transport = await configuredTransport();
  if (!transport) return false;
  const bytes = await buildEscPosReceiptBytes(order, company, branch, cashier);
  await sendConfiguredBytes(bytes, transport);
  return true;
}

export async function printConfiguredWapOrderSlip(
  order: WapOrder,
  type: "customer" | "kitchen",
  employeeName: string,
  menu: WapMenu | null,
  promptpayQrDataUrl?: string | null,
): Promise<boolean> {
  const transport = await configuredTransport();
  if (!transport) return false;
  const bytes = await buildEscPosWapOrderSlipBytes(order, type, employeeName, menu, promptpayQrDataUrl);
  await sendConfiguredBytes(bytes, transport);
  return true;
}

export async function printConfiguredLongReceiptTest(): Promise<boolean> {
  const transport = await configuredTransport();
  if (!transport) return false;
  const bytes = await buildEscPosLongTestBytes();
  await sendConfiguredBytes(bytes, transport);
  return true;
}

export async function openConfiguredCashDrawer(drawer: 0 | 1 = 0): Promise<boolean> {
  const transport = await configuredTransport();
  if (!transport) return false;
  await sendConfiguredBytes(buildEscPosCashDrawerPulse(drawer), transport);
  return true;
}
