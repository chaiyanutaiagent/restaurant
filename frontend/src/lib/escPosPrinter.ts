import { formatThaiCurrency, formatThaiDate } from "@/lib/cartUtils";
import {
  formatReceiptQuantity,
  getReceiptVatSummaryLabel,
  receiptOrderStatusLabels,
  receiptPaymentLabels,
} from "@/lib/receiptFormat";
import type { SaleOrder } from "@/types/pos";
import type { TakeawayReceipt } from "@/lib/takeawayApi";
import type { WapMenu, WapOrder } from "@/lib/wapApi";

const PHOMARK_VENDOR_ID = 0x0418;
const PHOMARK_PRODUCT_ID = 0x5011;
const SAVED_PRINTER_KEY = "pos-escpos-usb-printer";
const PAPER_DOTS = 576;
const CONTENT_LEFT = 32;
const CONTENT_RIGHT = 544;
const CONTENT_WIDTH = CONTENT_RIGHT - CONTENT_LEFT;
const FONT_FAMILY = 'Arial, "Noto Sans Thai", Thonburi, sans-serif';

type UsbEndpointLike = {
  direction: "in" | "out";
  endpointNumber: number;
  type: "bulk" | "interrupt" | "isochronous";
};

type UsbAlternateLike = {
  alternateSetting: number;
  interfaceClass: number;
  endpoints: UsbEndpointLike[];
};

type UsbInterfaceLike = {
  interfaceNumber: number;
  alternate: UsbAlternateLike;
  alternates: UsbAlternateLike[];
};

type UsbConfigurationLike = {
  configurationValue: number;
  interfaces: UsbInterfaceLike[];
};

type UsbDeviceLike = {
  vendorId: number;
  productId: number;
  productName?: string;
  manufacturerName?: string;
  serialNumber?: string;
  opened: boolean;
  configuration: UsbConfigurationLike | null;
  configurations: UsbConfigurationLike[];
  open(): Promise<void>;
  close(): Promise<void>;
  selectConfiguration(configurationValue: number): Promise<void>;
  claimInterface(interfaceNumber: number): Promise<void>;
  releaseInterface(interfaceNumber: number): Promise<void>;
  selectAlternateInterface(interfaceNumber: number, alternateSetting: number): Promise<void>;
  transferOut(endpointNumber: number, data: BufferSource): Promise<{ status: string }>;
};

type UsbManagerLike = {
  getDevices(): Promise<UsbDeviceLike[]>;
  requestDevice(options: { filters: Array<{ vendorId?: number; productId?: number; classCode?: number }> }): Promise<UsbDeviceLike>;
};

type NavigatorWithUsb = Navigator & { usb?: UsbManagerLike };

export type EscPosPrinterInfo = {
  name: string;
  serialNumber: string | null;
  vendorId: number;
  productId: number;
};

export type EscPosPrinterStatus = {
  supported: boolean;
  paired: boolean;
  printer: EscPosPrinterInfo | null;
};

export type EscPosReceiptCompany = {
  name: string;
  website?: string | null;
  phone?: string | null;
  logo_url?: string | null;
};

export type EscPosReceiptBranch = {
  name: string;
  phone?: string | null;
};

type TextOperation = {
  kind: "text";
  text: string;
  x: number;
  y: number;
  align: CanvasTextAlign;
  size: number;
  weight: number;
  color: string;
};

type RuleOperation = { kind: "rule"; y: number };
type ImageOperation = { kind: "image"; image: HTMLImageElement; x: number; y: number; width: number; height: number };
type DrawOperation = TextOperation | RuleOperation | ImageOperation;

function usbManager(): UsbManagerLike | null {
  if (typeof navigator === "undefined") return null;
  return (navigator as NavigatorWithUsb).usb ?? null;
}

function isEscPosPrinterDevice(device: UsbDeviceLike): boolean {
  if (device.vendorId === PHOMARK_VENDOR_ID && device.productId === PHOMARK_PRODUCT_ID) return true;
  return device.configurations.some((configuration) => configuration.interfaces.some((usbInterface) =>
    usbInterface.alternates.some((alternate) => alternate.interfaceClass === 7
      && alternate.endpoints.some((endpoint) => endpoint.direction === "out" && endpoint.type === "bulk"))));
}

function cleanUsbDescriptor(value: string | undefined): string {
  return value?.replace(/[\u0000-\u001f\u007f]/g, "").trim() ?? "";
}

function printerInfo(device: UsbDeviceLike): EscPosPrinterInfo {
  return {
    name: cleanUsbDescriptor(device.productName) || cleanUsbDescriptor(device.manufacturerName) || "PHOMARK POS-80",
    serialNumber: cleanUsbDescriptor(device.serialNumber) || null,
    vendorId: device.vendorId,
    productId: device.productId,
  };
}

function savedPrinterInfo(): Partial<EscPosPrinterInfo> | null {
  try {
    return JSON.parse(window.localStorage.getItem(SAVED_PRINTER_KEY) ?? "null") as Partial<EscPosPrinterInfo> | null;
  } catch {
    return null;
  }
}

function savePrinter(device: UsbDeviceLike): void {
  window.localStorage.setItem(SAVED_PRINTER_KEY, JSON.stringify(printerInfo(device)));
}

async function pairedDevice(): Promise<UsbDeviceLike | null> {
  const manager = usbManager();
  if (!manager) return null;
  const devices = (await manager.getDevices()).filter(isEscPosPrinterDevice);
  if (devices.length === 0) return null;
  const saved = savedPrinterInfo();
  return devices.find((device) =>
    (!saved?.vendorId || device.vendorId === saved.vendorId)
    && (!saved?.productId || device.productId === saved.productId)
    && (!saved?.serialNumber || cleanUsbDescriptor(device.serialNumber) === saved.serialNumber)) ?? devices[0];
}

export function isEscPosUsbSupported(): boolean {
  return Boolean(usbManager());
}

export async function getEscPosPrinterStatus(): Promise<EscPosPrinterStatus> {
  if (!isEscPosUsbSupported()) return { supported: false, paired: false, printer: null };
  const device = await pairedDevice();
  return { supported: true, paired: Boolean(device), printer: device ? printerInfo(device) : null };
}

function findBulkOutEndpoint(configuration: UsbConfigurationLike): {
  interfaceNumber: number;
  alternateSetting: number;
  endpointNumber: number;
} {
  const candidates: Array<{
    interfaceNumber: number;
    alternateSetting: number;
    endpointNumber: number;
    printerClass: boolean;
  }> = [];

  for (const usbInterface of configuration.interfaces) {
    for (const alternate of usbInterface.alternates) {
      const endpoint = alternate.endpoints.find((item) => item.direction === "out" && item.type === "bulk");
      if (endpoint) {
        candidates.push({
          interfaceNumber: usbInterface.interfaceNumber,
          alternateSetting: alternate.alternateSetting,
          endpointNumber: endpoint.endpointNumber,
          printerClass: alternate.interfaceClass === 7,
        });
      }
    }
  }

  const selected = candidates.find((item) => item.printerClass) ?? candidates[0];
  if (!selected) throw new Error("ไม่พบช่องส่งข้อมูลของเครื่องพิมพ์ USB");
  return selected;
}

async function withPrinter<T>(device: UsbDeviceLike, action: (device: UsbDeviceLike, endpointNumber: number) => Promise<T>): Promise<T> {
  let claimedInterface: number | null = null;
  try {
    if (!device.opened) await device.open();
    if (!device.configuration) {
      const configurationValue = device.configurations[0]?.configurationValue ?? 1;
      await device.selectConfiguration(configurationValue);
    }
    if (!device.configuration) throw new Error("เปิดการเชื่อมต่อเครื่องพิมพ์ไม่สำเร็จ");

    const endpoint = findBulkOutEndpoint(device.configuration);
    await device.claimInterface(endpoint.interfaceNumber);
    claimedInterface = endpoint.interfaceNumber;
    const activeInterface = device.configuration.interfaces.find((item) => item.interfaceNumber === endpoint.interfaceNumber);
    if (activeInterface?.alternate.alternateSetting !== endpoint.alternateSetting) {
      await device.selectAlternateInterface(endpoint.interfaceNumber, endpoint.alternateSetting);
    }
    return await action(device, endpoint.endpointNumber);
  } finally {
    if (claimedInterface !== null) {
      await device.releaseInterface(claimedInterface).catch(() => undefined);
    }
    if (device.opened) await device.close().catch(() => undefined);
  }
}

export async function connectEscPosUsbPrinter(): Promise<EscPosPrinterInfo> {
  const manager = usbManager();
  if (!manager) throw new Error("Chrome เครื่องนี้ไม่รองรับการเชื่อมเครื่องพิมพ์ USB โดยตรง");
  const device = await manager.requestDevice({
    filters: [
      { classCode: 7 },
      { vendorId: PHOMARK_VENDOR_ID, productId: PHOMARK_PRODUCT_ID },
    ],
  });
  await withPrinter(device, async () => undefined);
  savePrinter(device);
  return printerInfo(device);
}

function setFont(context: CanvasRenderingContext2D, size: number, weight: number): void {
  context.font = `${weight} ${size}px ${FONT_FAMILY}`;
}

function wrapText(context: CanvasRenderingContext2D, value: string, maxWidth: number, size: number, weight: number): string[] {
  setFont(context, size, weight);
  const lines: string[] = [];
  for (const paragraph of value.replace(/\r/g, "").split("\n")) {
    if (!paragraph) {
      lines.push("");
      continue;
    }
    let line = "";
    for (const character of Array.from(paragraph)) {
      const candidate = `${line}${character}`;
      if (line && context.measureText(candidate).width > maxWidth) {
        lines.push(line.trimEnd());
        line = character.trimStart();
      } else {
        line = candidate;
      }
    }
    if (line || lines.length === 0) lines.push(line.trimEnd());
  }
  return lines;
}

class ReceiptComposer {
  readonly operations: DrawOperation[] = [];
  y = 10;

  constructor(readonly measureContext: CanvasRenderingContext2D) {}

  spacer(height: number): void {
    this.y += height;
  }

  text(value: string, options: {
    x?: number;
    align?: CanvasTextAlign;
    size?: number;
    weight?: number;
    color?: string;
    lineHeight?: number;
  } = {}): void {
    const size = options.size ?? 21;
    this.operations.push({
      kind: "text",
      text: value,
      x: options.x ?? CONTENT_LEFT,
      y: this.y + size,
      align: options.align ?? "left",
      size,
      weight: options.weight ?? 400,
      color: options.color ?? "#000000",
    });
    this.y += options.lineHeight ?? Math.ceil(size * 1.28);
  }

  textAt(value: string, x: number, baselineY: number, options: {
    align?: CanvasTextAlign;
    size?: number;
    weight?: number;
    color?: string;
  } = {}): void {
    this.operations.push({
      kind: "text",
      text: value,
      x,
      y: baselineY,
      align: options.align ?? "left",
      size: options.size ?? 21,
      weight: options.weight ?? 400,
      color: options.color ?? "#000000",
    });
  }

  centered(value: string, size = 21, weight = 400, lineHeight?: number): void {
    this.text(value, { x: PAPER_DOTS / 2, align: "center", size, weight, lineHeight });
  }

  wrapped(value: string, maxWidth = CONTENT_WIDTH, options: {
    x?: number;
    align?: CanvasTextAlign;
    size?: number;
    weight?: number;
    color?: string;
    lineHeight?: number;
  } = {}): void {
    const size = options.size ?? 21;
    const weight = options.weight ?? 400;
    for (const line of wrapText(this.measureContext, value, maxWidth, size, weight)) {
      this.text(line, { ...options, size, weight });
    }
  }

  rule(): void {
    this.y += 5;
    this.operations.push({ kind: "rule", y: this.y });
    this.y += 10;
  }

  pair(label: string, value: string, options: { size?: number; weight?: number; color?: string } = {}): void {
    const size = options.size ?? 21;
    const baselineY = this.y + size;
    this.textAt(label, CONTENT_LEFT, baselineY, options);
    this.textAt(value, CONTENT_RIGHT, baselineY, { ...options, align: "right" });
    this.y += Math.ceil(size * 1.28);
  }

  image(image: HTMLImageElement, width: number, height: number): void {
    this.operations.push({ kind: "image", image, x: (PAPER_DOTS - width) / 2, y: this.y, width, height });
    this.y += height + 8;
  }
}

async function loadReceiptLogo(url: string | null | undefined): Promise<HTMLImageElement | null> {
  if (!url) return null;
  return await new Promise((resolve) => {
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = url;
  });
}

function addSaleItem(composer: ReceiptComposer, item: SaleOrder["items"][number]): void {
  const itemStartY = composer.y;
  const nameLines = wrapText(
    composer.measureContext,
    item.product_name,
    230,
    20,
    400,
  );
  const firstBaseline = itemStartY + 20;
  nameLines.forEach((line, index) => {
    composer.textAt(line, CONTENT_LEFT, firstBaseline + index * 25, { size: 20 });
  });
  composer.textAt(formatReceiptQuantity(Number(item.qty), item.unit_code), 356, firstBaseline, { align: "right", size: 20 });
  composer.textAt(formatThaiCurrency(Number(item.unit_price)), 448, firstBaseline, { align: "right", size: 20 });
  composer.textAt(formatThaiCurrency(Number(item.subtotal)), CONTENT_RIGHT, firstBaseline, { align: "right", size: 20 });
  composer.y = itemStartY + Math.max(25, nameLines.length * 25);

  if (item.variant_name) {
    composer.wrapped(item.variant_name, 230, { size: 18, color: "#333333", lineHeight: 23 });
  }
  if (Number(item.refunded_qty ?? 0) > 0) {
    composer.wrapped(
      `คืนแล้ว ${formatReceiptQuantity(Number(item.refunded_qty), item.unit_code)}${item.unit_code ? ` ${item.unit_code}` : ""}${Number(item.refunded_amount ?? 0) > 0 ? ` • ${formatThaiCurrency(Number(item.refunded_amount))}` : ""}`,
      CONTENT_WIDTH,
      { size: 18, weight: 600, lineHeight: 23 },
    );
  }
  composer.spacer(5);
}

function drawOperations(composer: ReceiptComposer): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = PAPER_DOTS;
  canvas.height = Math.max(1, Math.ceil(composer.y + 72));
  if (canvas.height > 30000) throw new Error("ใบเสร็จยาวเกินขีดจำกัด กรุณาแบ่งพิมพ์เป็นหลายใบ");
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("อุปกรณ์นี้ไม่สามารถสร้างภาพใบเสร็จได้");
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.textBaseline = "alphabetic";

  for (const operation of composer.operations) {
    if (operation.kind === "rule") {
      context.save();
      context.strokeStyle = "#000000";
      context.setLineDash([5, 5]);
      context.beginPath();
      context.moveTo(CONTENT_LEFT, operation.y + 0.5);
      context.lineTo(CONTENT_RIGHT, operation.y + 0.5);
      context.stroke();
      context.restore();
    } else if (operation.kind === "image") {
      context.save();
      context.filter = "grayscale(1) contrast(1.5)";
      context.drawImage(operation.image, operation.x, operation.y, operation.width, operation.height);
      context.restore();
    } else {
      context.fillStyle = operation.color;
      context.textAlign = operation.align;
      setFont(context, operation.size, operation.weight);
      context.fillText(operation.text, operation.x, operation.y);
    }
  }
  return canvas;
}

function createMeasureContext(): CanvasRenderingContext2D {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  if (!context) throw new Error("อุปกรณ์นี้ไม่สามารถจัดหน้าใบเสร็จได้");
  return context;
}

async function renderSaleReceipt(
  order: SaleOrder,
  company: EscPosReceiptCompany,
  branch: EscPosReceiptBranch,
  cashier: string,
): Promise<HTMLCanvasElement> {
  const composer = new ReceiptComposer(createMeasureContext());
  const logo = await loadReceiptLogo(company.logo_url);
  if (logo) {
    const scale = Math.min(280 / logo.naturalWidth, 100 / logo.naturalHeight, 1);
    composer.image(logo, Math.round(logo.naturalWidth * scale), Math.round(logo.naturalHeight * scale));
  }
  composer.centered(company.name, 28, 700, 34);
  composer.centered(`${branch.name}${branch.phone ? ` • ${branch.phone}` : ""}`, 21, 400, 27);
  composer.centered("ใบเสร็จรับเงิน", 23, 700, 29);
  composer.centered(`เลขที่: ${order.order_number}`, 20, 400, 26);
  composer.centered(`วันที่: ${formatThaiDate(order.created_at)} น.`, 20, 400, 26);
  composer.centered(`พนักงาน: ${cashier}`, 20, 400, 26);
  composer.centered(`สถานะ: ${receiptOrderStatusLabels[order.status] ?? order.status}`, 20, 600, 26);

  composer.rule();
  const tableHeaderY = composer.y + 20;
  composer.textAt("สินค้า", CONTENT_LEFT, tableHeaderY, { size: 20, weight: 700 });
  composer.textAt("จำนวน", 356, tableHeaderY, { align: "right", size: 19, weight: 700 });
  composer.textAt("ราคา", 448, tableHeaderY, { align: "right", size: 19, weight: 700 });
  composer.textAt("รวม", CONTENT_RIGHT, tableHeaderY, { align: "right", size: 19, weight: 700 });
  composer.y += 31;
  order.items.forEach((item) => addSaleItem(composer, item));

  composer.rule();
  composer.pair("ยอดรวม", formatThaiCurrency(Number(order.subtotal)));
  composer.pair("ส่วนลด", formatThaiCurrency(Number(order.discount_amount)));
  composer.pair(getReceiptVatSummaryLabel(order), formatThaiCurrency(Number(order.vat_amount)));
  composer.rule();
  composer.pair("สุทธิ", formatThaiCurrency(Number(order.total_amount)), { size: 24, weight: 700 });
  const refundedAmount = Number(order.refund_amount ?? 0);
  if (refundedAmount > 0) {
    composer.pair("คืนเงินสะสม", formatThaiCurrency(refundedAmount), { weight: 600 });
    composer.pair("สุทธิหลังหักคืน", formatThaiCurrency(Number(order.total_amount) - refundedAmount));
  }
  composer.pair("รับเงิน", formatThaiCurrency(Number(order.paid_amount)));
  composer.pair("เงินทอน", formatThaiCurrency(Number(order.change_amount)));
  if (order.customer_tax_id) composer.pair("เลขผู้เสียภาษี", order.customer_tax_id, { size: 19 });

  composer.rule();
  composer.text("การชำระเงิน", { weight: 700 });
  const paymentHistory = order.payments ?? [];
  for (const payment of paymentHistory.filter((item) => Number(item.amount) >= 0)) {
    composer.pair(receiptPaymentLabels[payment.payment_method] ?? "อื่นๆ", formatThaiCurrency(Number(payment.amount)));
    if (payment.reference_no) composer.wrapped(`อ้างอิง: ${payment.reference_no}`, CONTENT_WIDTH, { size: 18, color: "#333333", lineHeight: 23 });
  }
  const refundPayments = paymentHistory.filter((item) => Number(item.amount) < 0);
  if (refundPayments.length > 0) {
    composer.spacer(4);
    composer.text("ประวัติคืนเงิน", { weight: 700 });
    for (const payment of refundPayments) {
      composer.pair(receiptPaymentLabels[payment.payment_method] ?? "อื่นๆ", formatThaiCurrency(Number(payment.amount)));
      if (payment.reference_no) composer.wrapped(`อ้างอิง: ${payment.reference_no}`, CONTENT_WIDTH, { size: 18, lineHeight: 23 });
    }
  }

  if (order.note) {
    composer.rule();
    composer.text("หมายเหตุ", { weight: 700 });
    composer.wrapped(order.note, CONTENT_WIDTH, { size: 18, lineHeight: 23 });
  }

  composer.rule();
  composer.text("ข้อมูลลูกค้า", { weight: 700 });
  composer.wrapped(`ชื่อลูกค้า: ${order.customer_name || "ลูกค้าทั่วไป"}`, CONTENT_WIDTH, { size: 19, lineHeight: 25 });
  if (order.customer_phone) composer.wrapped(`เบอร์โทร: ${order.customer_phone}`, CONTENT_WIDTH, { size: 19, lineHeight: 25 });
  if (order.customer_tax_id) composer.wrapped(`เลขผู้เสียภาษี: ${order.customer_tax_id}`, CONTENT_WIDTH, { size: 19, lineHeight: 25 });

  composer.rule();
  composer.centered("ขอบคุณที่ใช้บริการ", 21, 400, 28);
  if (company.website) composer.centered(company.website, 18, 400, 23);
  if (company.phone) composer.centered(company.phone, 18, 400, 23);
  return drawOperations(composer);
}

async function renderTakeawayReceipt(
  receipt: TakeawayReceipt,
  copyType: "customer" | "merchant",
): Promise<HTMLCanvasElement> {
  const payload = receipt.payload;
  const composer = new ReceiptComposer(createMeasureContext());
  composer.centered("Foodchainservice Takeaway", 27, 700, 34);
  composer.centered(copyType === "customer" ? "ใบเสร็จลูกค้า" : "สำเนาร้าน", 22, 700, 29);
  composer.centered(String(payload.queue_number ?? "OFF"), 50, 800, 58);
  composer.centered(receipt.receipt_number, 20, 500, 26);
  composer.centered(new Date(receipt.issued_at).toLocaleString("th-TH"), 19, 400, 25);
  composer.rule();

  payload.items.forEach((item) => {
    const startY = composer.y;
    const lines = wrapText(composer.measureContext, `${Number(item.quantity)} × ${item.name}`, 365, 20, 400);
    lines.forEach((line, index) => composer.textAt(line, CONTENT_LEFT, startY + 20 + index * 25, { size: 20 }));
    composer.textAt(formatThaiCurrency(Number(item.line_total)), CONTENT_RIGHT, startY + 20, { align: "right", size: 20 });
    composer.y = startY + Math.max(25, lines.length * 25);
    composer.text(item.sku, { size: 17, color: "#333333", lineHeight: 22 });
    composer.spacer(3);
  });

  composer.rule();
  composer.pair("ก่อนภาษี", formatThaiCurrency(Number(payload.subtotal)));
  composer.pair("ส่วนลด", formatThaiCurrency(Number(payload.discount_amount)));
  composer.pair("ภาษี", formatThaiCurrency(Number(payload.tax_amount)));
  composer.rule();
  composer.pair("สุทธิ", formatThaiCurrency(Number(payload.total_amount)), { size: 24, weight: 700 });
  composer.pair("ชำระโดย", receiptPaymentLabels[payload.payment_method] ?? payload.payment_method);
  composer.rule();
  composer.centered("นำเลขคิวไปรับสินค้าที่เคาน์เตอร์", 20, 500, 27);
  if (receipt.print_count > 0) composer.centered(`พิมพ์ซ้ำครั้งที่ ${receipt.print_count + 1}`, 17, 400, 22);
  return drawOperations(composer);
}

async function renderWapOrderSlip(
  order: WapOrder,
  type: "customer" | "kitchen",
  employeeName: string,
  menu: WapMenu | null,
  promptpayQrDataUrl?: string | null,
): Promise<HTMLCanvasElement> {
  const isKitchen = type === "kitchen";
  const shopName = menu?.brand_name?.trim() || "Restaurant POS";
  const branchName = menu?.branch_name?.trim() || "ไม่ระบุสาขา";
  const branchLabel = branchName.startsWith("สาขา") ? branchName : `สาขา ${branchName}`;
  const composer = new ReceiptComposer(createMeasureContext());

  composer.centered(isKitchen ? "สลิปครัว" : "สลิปลูกค้า", 28, 800, 35);
  composer.centered(order.queue_display ?? "-", 52, 800, 61);
  composer.centered(shopName, 24, 700, 31);
  composer.centered(branchLabel, 20, 400, 26);
  composer.centered(`เลขขาย ${order.sale_order_number}`, 19, 400, 25);
  composer.centered(`พนักงาน ${employeeName}`, 19, 400, 25);
  if (order.created_at) composer.centered(new Date(order.created_at).toLocaleString("th-TH"), 18, 400, 24);
  composer.rule();

  if (order.customer_name) composer.wrapped(`ลูกค้า: ${order.customer_name}`, CONTENT_WIDTH, { size: 19, lineHeight: 25 });
  if (order.customer_phone) composer.text(`โทร: ${order.customer_phone}`, { size: 19, lineHeight: 25 });
  if (order.customer_name || order.customer_phone) composer.spacer(4);

  order.items.forEach((item) => {
    const startY = composer.y;
    const maxNameWidth = isKitchen ? CONTENT_WIDTH : 375;
    const lines = wrapText(composer.measureContext, `${formatReceiptQuantity(Number(item.qty), null)} × ${item.product_name}`, maxNameWidth, 21, isKitchen ? 700 : 400);
    lines.forEach((line, index) => composer.textAt(line, CONTENT_LEFT, startY + 21 + index * 27, { size: 21, weight: isKitchen ? 700 : 400 }));
    if (!isKitchen) composer.textAt(formatThaiCurrency(Number(item.unit_price) * Number(item.qty)), CONTENT_RIGHT, startY + 21, { align: "right", size: 20 });
    composer.y = startY + Math.max(27, lines.length * 27);
    if (item.special_request) {
      composer.wrapped(`* ${item.special_request}`, CONTENT_WIDTH - 20, { x: CONTENT_LEFT + 20, size: 20, weight: 700, lineHeight: 26 });
    }
    composer.spacer(5);
  });

  composer.rule();
  if (!isKitchen) {
    composer.pair("รวม", formatThaiCurrency(Number(order.total_amount)));
    composer.pair("รับเงิน", formatThaiCurrency(Number(order.paid_amount)));
    composer.pair("ทอน", formatThaiCurrency(Number(order.change_amount)));
    composer.pair("ชำระโดย", receiptPaymentLabels[order.payment_method] ?? order.payment_method);
    if (promptpayQrDataUrl) {
      const qrImage = await loadReceiptLogo(promptpayQrDataUrl);
      if (qrImage) {
        composer.rule();
        composer.centered(`PromptPay ${branchLabel}`, 20, 700, 28);
        composer.image(qrImage, 240, 240);
        composer.centered(`ยอดชำระ ${formatThaiCurrency(Number(order.total_amount))}`, 20, 700, 27);
        if (menu?.promptpay_name) composer.centered(`ชื่อบัญชี ${menu.promptpay_name}`, 18, 400, 24);
      }
    }
    composer.rule();
    composer.centered("นำสลิปนี้ไปรับสินค้าที่เคาน์เตอร์", 20, 500, 27);
  } else {
    composer.centered("ทำสินค้าแล้วส่งกลับเคาน์เตอร์", 21, 700, 28);
  }
  return drawOperations(composer);
}

function renderLongTestReceipt(): HTMLCanvasElement {
  const composer = new ReceiptComposer(createMeasureContext());
  composer.centered("ทดสอบ ESC/POS แบบยาว", 28, 700, 35);
  composer.centered("60 รายการ • ความสูงตามข้อมูลจริง", 21, 400, 28);
  composer.centered(new Date().toLocaleString("th-TH"), 19, 400, 25);
  composer.rule();
  const headerY = composer.y + 20;
  composer.textAt("สินค้า", CONTENT_LEFT, headerY, { size: 20, weight: 700 });
  composer.textAt("จำนวน", 356, headerY, { align: "right", size: 19, weight: 700 });
  composer.textAt("ราคา", 448, headerY, { align: "right", size: 19, weight: 700 });
  composer.textAt("รวม", CONTENT_RIGHT, headerY, { align: "right", size: 19, weight: 700 });
  composer.y += 31;
  for (let index = 1; index <= 60; index += 1) {
    const baselineY = composer.y + 20;
    composer.textAt(`สินค้าทดสอบ ${String(index).padStart(2, "0")}`, CONTENT_LEFT, baselineY, { size: 20 });
    composer.textAt("1", 356, baselineY, { align: "right", size: 20 });
    composer.textAt("฿10.00", 448, baselineY, { align: "right", size: 20 });
    composer.textAt("฿10.00", CONTENT_RIGHT, baselineY, { align: "right", size: 20 });
    composer.y += 27;
  }
  composer.rule();
  composer.pair("รวม 60 รายการ", "฿600.00", { size: 23, weight: 700 });
  composer.centered("จบใบเสร็จ — ต้องตัดตรงนี้", 21, 700, 28);
  return drawOperations(composer);
}

export function canvasToEscPosRaster(canvas: HTMLCanvasElement): Uint8Array {
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("อ่านภาพใบเสร็จไม่สำเร็จ");
  const image = context.getImageData(0, 0, canvas.width, canvas.height).data;
  const bytesPerRow = Math.ceil(canvas.width / 8);
  const raster = new Uint8Array(bytesPerRow * canvas.height);
  for (let y = 0; y < canvas.height; y += 1) {
    for (let x = 0; x < canvas.width; x += 1) {
      const pixelIndex = (y * canvas.width + x) * 4;
      const alpha = image[pixelIndex + 3] / 255;
      const luminance = (image[pixelIndex] * 0.299 + image[pixelIndex + 1] * 0.587 + image[pixelIndex + 2] * 0.114) * alpha + 255 * (1 - alpha);
      if (luminance < 205) raster[y * bytesPerRow + Math.floor(x / 8)] |= 0x80 >> (x % 8);
    }
  }

  const header = new Uint8Array([
    0x1d, 0x76, 0x30, 0x00,
    bytesPerRow & 0xff, (bytesPerRow >> 8) & 0xff,
    canvas.height & 0xff, (canvas.height >> 8) & 0xff,
  ]);
  const output = new Uint8Array(2 + header.length + raster.length + 7);
  let offset = 0;
  output.set([0x1b, 0x40], offset); offset += 2;
  output.set(header, offset); offset += header.length;
  output.set(raster, offset); offset += raster.length;
  output.set([0x1b, 0x64, 0x04, 0x1d, 0x56, 0x41, 0x10], offset);
  return output;
}

export async function printEscPosBytes(bytes: Uint8Array): Promise<void> {
  const device = await pairedDevice();
  if (!device) throw new Error("ยังไม่ได้เชื่อมเครื่องพิมพ์ ESC/POS กับเว็บนี้");
  await withPrinter(device, async (activeDevice, endpointNumber) => {
    const chunkSize = 16 * 1024;
    for (let offset = 0; offset < bytes.length; offset += chunkSize) {
      const chunk = bytes.slice(offset, Math.min(bytes.length, offset + chunkSize));
      const result = await activeDevice.transferOut(endpointNumber, chunk);
      if (result.status !== "ok") throw new Error(`เครื่องพิมพ์ไม่รับข้อมูล (${result.status})`);
    }
  });
}

export async function printEscPosReceipt(
  order: SaleOrder,
  company: EscPosReceiptCompany,
  branch: EscPosReceiptBranch,
  cashier: string,
): Promise<void> {
  await printEscPosBytes(await buildEscPosReceiptBytes(order, company, branch, cashier));
}

export async function buildEscPosReceiptBytes(
  order: SaleOrder,
  company: EscPosReceiptCompany,
  branch: EscPosReceiptBranch,
  cashier: string,
): Promise<Uint8Array> {
  return canvasToEscPosRaster(await renderSaleReceipt(order, company, branch, cashier));
}

export async function buildEscPosTakeawayReceiptBytes(
  receipt: TakeawayReceipt,
  copyType: "customer" | "merchant",
): Promise<Uint8Array> {
  return canvasToEscPosRaster(await renderTakeawayReceipt(receipt, copyType));
}

export async function printEscPosTakeawayReceipt(
  receipt: TakeawayReceipt,
  copyType: "customer" | "merchant",
): Promise<void> {
  await printEscPosBytes(await buildEscPosTakeawayReceiptBytes(receipt, copyType));
}

export async function buildEscPosWapOrderSlipBytes(
  order: WapOrder,
  type: "customer" | "kitchen",
  employeeName: string,
  menu: WapMenu | null,
  promptpayQrDataUrl?: string | null,
): Promise<Uint8Array> {
  return canvasToEscPosRaster(await renderWapOrderSlip(order, type, employeeName, menu, promptpayQrDataUrl));
}

export async function printEscPosWapOrderSlip(
  order: WapOrder,
  type: "customer" | "kitchen",
  employeeName: string,
  menu: WapMenu | null,
  promptpayQrDataUrl?: string | null,
): Promise<void> {
  await printEscPosBytes(await buildEscPosWapOrderSlipBytes(order, type, employeeName, menu, promptpayQrDataUrl));
}

export function buildEscPosLongTestBytes(): Uint8Array {
  return canvasToEscPosRaster(renderLongTestReceipt());
}

export async function printEscPosLongTest(): Promise<void> {
  await printEscPosBytes(buildEscPosLongTestBytes());
}

export function describeEscPosError(error: unknown): string {
  if (error instanceof DOMException && error.name === "NotFoundError") return "ไม่ได้เลือกเครื่องพิมพ์";
  if (error instanceof DOMException && error.name === "SecurityError") return "Chrome ไม่อนุญาตให้เว็บเข้าถึงเครื่องพิมพ์นี้";
  if (error instanceof DOMException && error.name === "NetworkError") return "เปิดเครื่องพิมพ์ไม่ได้ อาจมีโปรแกรมอื่นกำลังใช้งานอยู่";
  return error instanceof Error ? error.message : "เชื่อมต่อเครื่องพิมพ์ไม่สำเร็จ";
}
