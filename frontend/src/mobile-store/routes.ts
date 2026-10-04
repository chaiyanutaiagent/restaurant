export const STORE_ROUTES = [
  { path: "/takeaway/store/orders", label: "ขายและเตรียมสินค้า", permission: "takeaway.sale.create" },
  { path: "/takeaway/store/catalog", label: "สินค้า", permission: "takeaway.catalog.view" },
  { path: "/takeaway/store/shifts", label: "กะขาย", permission: "takeaway.shift.manage" },
  { path: "/takeaway/store/stock", label: "สต๊อกร้าน", permission: "takeaway.stock.view" },
  { path: "/takeaway/store/central-orders", label: "สั่ง/รับส่วนกลาง", permission: "takeaway.central_order.create" },
  { path: "/takeaway/store/transfers", label: "รับโอนสินค้า", permission: "takeaway.transfer.manage" },
  { path: "/takeaway/store/credits", label: "เครดิตสาขา", permission: "takeaway.credit.manage" },
  { path: "/takeaway/store/device", label: "เครื่องพิมพ์/แอป", permission: "takeaway.store.access" },
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
