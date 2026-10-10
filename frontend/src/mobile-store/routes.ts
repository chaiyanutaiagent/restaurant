export const STORE_ROUTES = [
  {
    path: "/takeaway/store/sales",
    label: "ขายสินค้า",
    navLabel: "ขาย",
    menuLabel: "ขายสินค้า",
    sectionLabel: "เมนูขายหน้าร้าน",
    permission: "takeaway.sale.create",
    primary: true,
  },
  {
    path: "/takeaway/store/orders",
    label: "ขายและเตรียมสินค้า",
    navLabel: "รับออเดอร์",
    menuLabel: "รับออเดอร์",
    sectionLabel: "รับออเดอร์ · เตรียมและส่งมอบ",
    permission: "takeaway.sale.create",
    primary: false,
  },
  {
    path: "/takeaway/store/catalog",
    label: "สินค้า",
    navLabel: "สินค้า",
    menuLabel: "สินค้า",
    sectionLabel: "รายการสินค้า",
    permission: "takeaway.catalog.view",
    primary: false,
  },
  {
    path: "/takeaway/store/stock",
    label: "สต๊อกร้าน",
    navLabel: "Stock",
    menuLabel: "Stock หน้าร้าน",
    sectionLabel: "Stock หน้าร้าน",
    permission: "takeaway.stock.view",
    primary: true,
  },
  {
    path: "/takeaway/store/shifts",
    label: "กะขาย",
    navLabel: "ปิดกะ",
    menuLabel: "ปิดกะ",
    sectionLabel: "ปิดกะ",
    permission: "takeaway.shift.manage",
    primary: true,
  },
  {
    path: "/takeaway/store/central-orders",
    label: "สั่ง/รับส่วนกลาง",
    navLabel: "สั่ง/รับสินค้า",
    menuLabel: "รายการสั่งสินค้า",
    sectionLabel: "รายการสั่งสินค้า",
    permission: "takeaway.central_order.create",
    primary: true,
  },
  {
    path: "/takeaway/store/credits",
    label: "เครดิตสาขา",
    navLabel: "เครดิต",
    menuLabel: "แจ้งเติมเครดิต",
    sectionLabel: "แจ้งเติมเครดิต",
    permission: "takeaway.credit.manage",
    primary: true,
  },
  {
    path: "/takeaway/store/transfers",
    label: "รับโอนสินค้า",
    navLabel: "รับโอนสินค้า",
    menuLabel: "รับโอนสินค้า",
    sectionLabel: "รับโอนสินค้า",
    permission: "takeaway.transfer.manage",
    primary: false,
  },
  {
    path: "/takeaway/store/device",
    label: "เครื่องพิมพ์/แอป",
    navLabel: "เครื่องพิมพ์/แอป",
    menuLabel: "ตั้งค่าเครื่องพิมพ์",
    sectionLabel: "ตั้งค่าเครื่องพิมพ์",
    permission: "takeaway.store.access",
    primary: false,
  },
] as const;

export function allowedStoreRoute(path: string, permissions: string[]): boolean {
  return STORE_ROUTES.some((route) => route.path === path && permissions.includes(route.permission));
}

export function businessCodeFromQr(value: string): string {
  const trimmed = value.trim();
  if (/^foodchainservice:\/\/business\//i.test(trimmed)) {
    return businessCodeFromQr(trimmed.slice("foodchainservice://business/".length));
  }
  const code = trimmed.toLowerCase();
  if (!/^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$/.test(code)) throw new Error("QR ต้องเป็น Business Code หรือ foodchainservice://business/<code>");
  return code;
}
