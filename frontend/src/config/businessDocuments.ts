/** Navigation metadata only. Source APIs remain authoritative for access and issuance. */
export const DOCUMENT_CENTER_PERMISSIONS = [
  "inventory.purchase.view",
  "accounting.payment.view",
  "accounting.invoice.view",
];

export const DOCUMENT_GROUPS = {
  purchase: "จัดซื้อและรับสินค้า",
  payable: "เจ้าหนี้และการจ่าย",
  tax: "เอกสารภาษีจากการขาย",
  credit: "ขายเชื่อและลูกหนี้ (UAT)",
} as const;

export type DocumentGroup = keyof typeof DOCUMENT_GROUPS;

export type BusinessDocumentEntry = {
  id: string;
  title: string;
  description: string;
  group: DocumentGroup;
  permission: string;
  route: string;
  instruction: string;
};

export const BUSINESS_DOCUMENTS: readonly BusinessDocumentEntry[] = [
  ...([ ["sales_quotation", "ใบเสนอราคา"], ["sales_delivery", "ใบส่งมอบ"], ["customer_invoice", "ใบแจ้งหนี้ลูกค้า"],
    ["billing_notice", "ใบวางบิล"], ["customer_receipt", "ใบรับเงินลูกค้า"] ] as const).map(([id, title]) => ({
      id, title, group: "credit" as const, permission: "accounting.invoice.view", route: "/company/credit-sales",
      description: "วงจรขายเชื่อ UAT แยกจากยอดขาย POS และเครดิตสาขา",
      instruction: "สร้างรายการ อนุมัติ ส่งมอบ แจ้งหนี้ วางบิล และรับเงินจากหน้าขายเชื่อ ไม่ใช่เอกสารภาษีจริง",
    })),
  {
    id: "purchase_order", title: "ใบสั่งซื้อ", group: "purchase",
    permission: "inventory.purchase.view", route: "/purchase/orders",
    description: "สั่งซื้อสินค้าจากผู้จำหน่ายและติดตามการอนุมัติ",
    instruction: "เลือกใบสั่งซื้อเพื่อดูรายละเอียดหรือดาวน์โหลดเอกสารจากระบบจัดซื้อ",
  },
  {
    id: "goods_receipt", title: "ใบรับสินค้า", group: "purchase",
    permission: "inventory.purchase.view", route: "/purchase/orders",
    description: "หลักฐานรับสินค้าจากผู้จำหน่าย อ้างอิงใบสั่งซื้อ",
    instruction: "เปิดใบสั่งซื้อที่เกี่ยวข้อง แล้วดูส่วนประวัติการรับสินค้า ไม่ใช่ใบส่งของให้ลูกค้า",
  },
  {
    id: "supplier_invoice", title: "ใบแจ้งหนี้จากผู้จำหน่าย", group: "payable",
    permission: "accounting.payment.view", route: "/payable?tab=invoices",
    description: "ทะเบียนเจ้าหนี้ ยอดค้างชำระ และวันครบกำหนด",
    instruction: "ใช้บันทึกเอกสารที่ได้รับจากผู้จำหน่าย ไม่ใช่ออกใบแจ้งหนี้ให้ลูกค้า",
  },
  {
    id: "payment_voucher", title: "ใบสำคัญจ่าย", group: "payable",
    permission: "accounting.payment.view", route: "/payable?tab=payments",
    description: "หลักฐานการจ่ายเงินและการตัดยอดใบแจ้งหนี้เจ้าหนี้",
    instruction: "เลือกการจ่ายที่บันทึกแล้วเพื่อดาวน์โหลดใบสำคัญจ่าย",
  },
  {
    id: "wht_certificate", title: "หนังสือรับรองหัก ณ ที่จ่าย", group: "payable",
    permission: "accounting.payment.view", route: "/payable?tab=wht",
    description: "เอกสารหัก ณ ที่จ่ายที่อ้างอิงการจ่ายเงินให้ผู้จำหน่าย",
    instruction: "เลือกใบรับรองจากทะเบียนเดิม การออกเอกสารยังใช้สิทธิ์และเงื่อนไขต้นทาง",
  },
  {
    id: "sales_tax_document", title: "ใบกำกับภาษีและใบลดหนี้", group: "tax",
    permission: "accounting.invoice.view", route: "/etax",
    description: "เอกสารภาษีที่เชื่อมกับรายการขายและเอกสารอ้างอิงเดิม",
    instruction: "เลือกเอกสารจากทะเบียนภาษี การมีเมนูนี้ไม่ใช่การยืนยันสิทธิ์ออกเอกสารจริงหรือส่ง e-Tax สำเร็จ",
  },
];

export function visibleBusinessDocuments(permissions: readonly string[]): readonly BusinessDocumentEntry[] {
  return BUSINESS_DOCUMENTS.filter((entry) => permissions.includes("*") || permissions.includes(entry.permission));
}

export function filterBusinessDocuments(
  entries: readonly BusinessDocumentEntry[], search: string, group: DocumentGroup | "all",
): readonly BusinessDocumentEntry[] {
  const term = search.trim().toLocaleLowerCase("th");
  return entries.filter((entry) => (
    (group === "all" || entry.group === group)
    && `${entry.title} ${entry.description} ${entry.instruction}`.toLocaleLowerCase("th").includes(term)
  ));
}

export function payableDocumentTab(value: string | null): string {
  return value && ["invoices", "payments", "wht", "vat"].includes(value) ? value : "invoices";
}
