import { Capacitor, registerPlugin } from "@capacitor/core";
import type { TakeawayReceipt } from "@/lib/takeawayApi";
import type { WapMenu, WapOrder } from "@/lib/wapApi";
import {
  buildEscPosReceiptBytes,
  buildEscPosCashDrawerPulse,
  buildEscPosTakeawayReceiptBytes,
  buildEscPosLongTestBytes,
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
};

const nativePrinter = registerPlugin<TakeawayPrinterNative>("TakeawayPrinter");
const PRINTER_KEY = "foodchainservice-takeaway-printer";

export function isNativeTakeawayPrinterAvailable(): boolean {
  return Capacitor.isNativePlatform() && Capacitor.getPlatform() === "android"
    && Capacitor.isPluginAvailable("TakeawayPrinter");
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
  const init = new Uint8Array([0x1b, 0x40]);
  const body = new TextEncoder().encode(content);
  const cut = new Uint8Array([0x1d, 0x56, 0x41, 0x10]);
  const bytes = new Uint8Array(init.length + body.length + cut.length);
  bytes.set(init, 0);
  bytes.set(body, init.length);
  bytes.set(cut, init.length + body.length);
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
  const bytes = buildEscPosLongTestBytes();
  await sendConfiguredBytes(bytes, transport);
  return true;
}

export async function openConfiguredCashDrawer(drawer: 0 | 1 = 0): Promise<boolean> {
  const transport = await configuredTransport();
  if (!transport) return false;
  await sendConfiguredBytes(buildEscPosCashDrawerPulse(drawer), transport);
  return true;
}
