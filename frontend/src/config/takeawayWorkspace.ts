export type TakeawayWorkspaceArea = "overview" | "store" | "central" | "admin";

export type TakeawayNavigationItem = {
  key: string;
  label: string;
  to: string;
  permissions: string[];
  description: string;
};

export type TakeawayNavigationGroup = {
  area: TakeawayWorkspaceArea;
  label: string;
  shortLabel: string;
  allowedScopes: string[];
  items: TakeawayNavigationItem[];
};

export const TAKEAWAY_NAVIGATION: TakeawayNavigationGroup[] = [
  {
    area: "overview",
    label: "ภาพรวม",
    shortLabel: "ภาพรวม",
    allowedScopes: ["company", "brand", "branch", "station"],
    items: [
      {
        key: "overview",
        label: "ภาพรวมระบบ",
        to: "/takeaway",
        permissions: ["takeaway.catalog.view"],
        description: "สถานะระบบและทางลัดตามสิทธิ์",
      },
    ],
  },
  {
    area: "store",
    label: "หน้าร้าน",
    shortLabel: "STORE",
    allowedScopes: ["company", "branch", "station"],
    items: [
      { key: "store-orders", label: "ขายหน้าร้าน", to: "/takeaway/store/orders", permissions: ["takeaway.sale.create"], description: "รับเงิน ออกคิว และส่งครัว" },
      { key: "store-shifts", label: "กะขาย", to: "/takeaway/store/shifts", permissions: ["takeaway.shift.manage"], description: "เปิด ปิด และตรวจเงินในกะ" },
      { key: "store-kitchen", label: "ครัว", to: "/takeaway/store/kitchen", permissions: ["takeaway.kitchen.manage"], description: "คิวรอทำ กำลังทำ และพร้อมรับ" },
      { key: "store-pickup", label: "จุดรับสินค้า", to: "/takeaway/store/pickup", permissions: ["takeaway.pickup.manage"], description: "เรียกคิวและยืนยันส่งมอบ" },
      { key: "store-central-orders", label: "สั่งส่วนกลาง", to: "/takeaway/store/central-orders", permissions: ["takeaway.central_order.create"], description: "ใบสั่งประจำ รายการเพิ่ม และรับของ" },
      { key: "store-stock", label: "สต๊อกร้าน", to: "/takeaway/store/stock", permissions: ["takeaway.stock.view"], description: "ยอดคงเหลือและความเคลื่อนไหวสาขา" },
      { key: "store-transfers", label: "รับโอนสินค้า", to: "/takeaway/store/transfers", permissions: ["takeaway.transfer.manage"], description: "รายการส่งจากส่วนกลางและยอดรับจริง" },
      { key: "store-reports", label: "รายงานร้าน", to: "/takeaway/store/reports", permissions: ["takeaway.report.view"], description: "ยอดขายและการทำงานของสาขา" },
      { key: "store-staff", label: "พนักงาน", to: "/takeaway/store/staff", permissions: ["system.user.view"], description: "ผู้ใช้และบทบาทของสาขา" },
    ],
  },
  {
    area: "central",
    label: "ส่วนกลาง",
    shortLabel: "CENTRAL",
    allowedScopes: ["company", "brand"],
    items: [
      { key: "central-orders", label: "ใบสั่งสาขา", to: "/takeaway/central/orders", permissions: ["takeaway.central_order.manage"], description: "อนุมัติ แพ็ก ส่ง และติดตามแยกสาขา" },
      { key: "central-production", label: "การผลิต", to: "/takeaway/central/production", permissions: ["takeaway.production.manage"], description: "แผนผลิต วัตถุดิบ และผลผลิต" },
      { key: "central-stock", label: "สต๊อกกลาง", to: "/takeaway/central/stock", permissions: ["takeaway.stock.manage"], description: "RAW READY TRANSIT และ movement" },
      { key: "central-transfers", label: "กระจายสินค้า", to: "/takeaway/central/transfers", permissions: ["takeaway.transfer.manage"], description: "ส่งสินค้าไปสาขาและตรวจรับ" },
      { key: "central-credits", label: "เครดิตสาขา", to: "/takeaway/central/credits", permissions: ["takeaway.credit.manage"], description: "วงเงินและ ledger แฟรนไชส์" },
      { key: "central-recipes", label: "สูตร", to: "/takeaway/central/recipes", permissions: ["takeaway.production.manage"], description: "สูตรผลิต yield และต้นทุน" },
      { key: "central-reports", label: "รายงานกลาง", to: "/takeaway/central/reports", permissions: ["takeaway.report.view"], description: "ภาพรวมสาขา ผลิต สต๊อก และเครดิต" },
      { key: "central-staff", label: "พนักงาน", to: "/takeaway/central/staff", permissions: ["system.user.view"], description: "ผู้ใช้และบทบาทส่วนกลาง" },
    ],
  },
  {
    area: "admin",
    label: "ผู้ดูแล",
    shortLabel: "ADMIN",
    allowedScopes: ["company", "brand"],
    items: [
      { key: "admin-import", label: "นำเข้า Chambo", to: "/takeaway/admin/import", permissions: ["takeaway.import.dry_run"], description: "ตรวจแพ็กเกจก่อนย้ายข้อมูล" },
      { key: "admin-cutover", label: "Cutover", to: "/takeaway/admin/cutover", permissions: ["takeaway.import.apply"], description: "เตรียม activation และ rollback" },
      { key: "admin-erp", label: "เชื่อม ERP", to: "/takeaway/admin/erp", permissions: ["takeaway.erp.export"], description: "Outbox และ reconciliation" },
      { key: "admin-users", label: "ผู้ใช้และสิทธิ์", to: "/takeaway/admin/users", permissions: ["system.user.view"], description: "พนักงาน บทบาท และขอบเขตงาน" },
    ],
  },
];

export const TAKEAWAY_ENTRY_PERMISSIONS = Array.from(new Set(
  TAKEAWAY_NAVIGATION.flatMap((group) => group.items.flatMap((item) => item.permissions)),
)).filter((permission) => permission.startsWith("takeaway."));

export function canAccessTakeawayArea(
  area: TakeawayWorkspaceArea,
  scopeTypes: string[],
  hasPermission: (code: string) => boolean,
): boolean {
  if (hasPermission("*")) return true;
  const group = TAKEAWAY_NAVIGATION.find((candidate) => candidate.area === area);
  if (!group) return false;
  if (!scopeTypes.length) return true;
  return group.allowedScopes.some((scope) => scopeTypes.includes(scope));
}

export function firstAccessibleTakeawayRoute(
  scopeTypes: string[],
  hasPermission: (code: string) => boolean,
): string | null {
  for (const group of TAKEAWAY_NAVIGATION) {
    if (!canAccessTakeawayArea(group.area, scopeTypes, hasPermission)) continue;
    const item = group.items.find((candidate) => candidate.permissions.some(hasPermission));
    if (item) return item.to;
  }
  return null;
}
