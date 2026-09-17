import { Capacitor, registerPlugin } from "@capacitor/core";
import type { TakeawayReceipt } from "@/lib/takeawayApi";

export type TakeawayPrinterDevice = { name: string; address: string };

type TakeawayPrinterNative = {
  requestBluetoothPermission(): Promise<void>;
  pairedDevices(): Promise<{ devices: TakeawayPrinterDevice[] }>;
  printBase64(options: { address: string; data: string }): Promise<void>;
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
  const printer = savedTakeawayPrinter();
  if (!printer || !isNativeTakeawayPrinterAvailable()) return false;
  await printTakeawayRaw(printer.address, takeawayReceiptText(receipt, copyType));
  return true;
}
