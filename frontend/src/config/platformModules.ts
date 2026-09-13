export type PlatformModuleKey =
  | "company_admin"
  | "erp"
  | "central_kitchen"
  | "restaurant_pos"
  | "takeaway_pos"
  | "retail_pos"
  | "hotel_pms";

export type PlatformModuleGroup = "control" | "shared_service" | "pos";
export type PlatformModuleAvailability = "active" | "dark_launch" | "planned";
export type PlatformModuleRegistration = "open" | "closed" | "not_applicable";
export type PlatformBusinessType = "restaurant" | "takeaway" | "retail_pos" | "hotel";

export type PlatformModuleDefinition = {
  key: PlatformModuleKey;
  title: string;
  eyebrow: string;
  description: string;
  group: PlatformModuleGroup;
  entryRoute: string | null;
  availability: PlatformModuleAvailability;
  registration: PlatformModuleRegistration;
  registrationRoute: string | null;
  permissionHints: readonly string[];
  businessType: PlatformBusinessType | null;
  workspaceVisible: boolean;
};

export const PLATFORM_MODULES = [
  {
    key: "company_admin",
    title: "Company Admin",
    eyebrow: "ศูนย์ควบคุมของบริษัท",
    description: "จัดการบริษัท ผู้ใช้ สิทธิ์ สาขา อุปกรณ์ และโมดูลที่เปิดใช้งาน",
    group: "control",
    entryRoute: "/admin",
    availability: "active",
    registration: "not_applicable",
    registrationRoute: null,
    permissionHints: [],
    businessType: null,
    workspaceVisible: false,
  },
  {
    key: "erp",
    title: "ERP และรายงาน",
    eyebrow: "ระบบบริหารส่วนกลาง",
    description: "สินค้า คลัง จัดซื้อ บัญชี บุคลากร รายงานรวม และการเชื่อมต่อระบบ",
    group: "shared_service",
    entryRoute: "/admin",
    availability: "active",
    registration: "not_applicable",
    registrationRoute: null,
    permissionHints: [],
    businessType: null,
    workspaceVisible: true,
  },
  {
    key: "central_kitchen",
    title: "Central Kitchen / Supply Chain",
    eyebrow: "ครัวกลางและซัพพลายเชน",
    description: "รับคำสั่งผลิตหลายแบรนด์ วางแผนการผลิต และบริหารวัตถุดิบกองกลาง",
    group: "shared_service",
    entryRoute: "/restaurant/brands",
    availability: "active",
    registration: "not_applicable",
    registrationRoute: null,
    permissionHints: [
      "brand.central.raw_stock.view",
      "brand.central.ready_stock.view",
      "brand.central.production.view",
      "brand.central.production.manage",
      "fb.kitchen.manage",
    ],
    businessType: null,
    workspaceVisible: true,
  },
  {
    key: "restaurant_pos",
    title: "Restaurant POS",
    eyebrow: "ร้านอาหารและคาเฟ่",
    description: "จัดการแบรนด์ สาขา ออเดอร์ โต๊ะ ครัว คิว เมนู สูตรอาหาร และ QR ที่โต๊ะ",
    group: "pos",
    entryRoute: "/restaurant/brands",
    availability: "active",
    registration: "open",
    registrationRoute: "/signup/restaurant",
    permissionHints: [
      "fb.menu.view",
      "fb.table.manage",
      "fb.order.create",
      "fb.kitchen.ticket.manage",
      "fb.kitchen.manage",
      "fb.recipe.manage",
      "fb.report.view",
      "fb.settings.manage",
      "brand.store.order.create",
    ],
    businessType: "restaurant",
    workspaceVisible: true,
  },
  {
    key: "takeaway_pos",
    title: "Takeaway POS",
    eyebrow: "รับสินค้าจากส่วนกลาง",
    description: "ขายแบบชำระก่อนผลิต ออกเลขคิว ส่งครัว และใช้สต๊อกร่วมหลายแบรนด์",
    group: "pos",
    entryRoute: "/takeaway",
    availability: "dark_launch",
    registration: "closed",
    registrationRoute: null,
    permissionHints: [
      "takeaway.catalog.view",
      "takeaway.sale.create",
      "takeaway.kitchen.manage",
      "takeaway.pickup.manage",
    ],
    businessType: "takeaway",
    workspaceVisible: true,
  },
  {
    key: "retail_pos",
    title: "Retail POS",
    eyebrow: "ร้านค้าปลีกและบริการ",
    description: "ขายหน้าร้าน สแกนสินค้า เปิดกะ รับชำระเงิน และจัดการสต๊อกหน้าร้าน",
    group: "pos",
    entryRoute: "/pos",
    availability: "active",
    registration: "closed",
    registrationRoute: null,
    permissionHints: ["pos.sale.create", "pos.sale.view", "pos.report.view"],
    businessType: "retail_pos",
    workspaceVisible: true,
  },
  {
    key: "hotel_pms",
    title: "Hotel PMS",
    eyebrow: "ที่พักและงานบริการ",
    description: "ระบบจอง ห้องพัก ผู้เข้าพัก และการบริหารโรงแรมแบบครบวงจร",
    group: "pos",
    entryRoute: null,
    availability: "planned",
    registration: "closed",
    registrationRoute: null,
    permissionHints: [],
    businessType: "hotel",
    workspaceVisible: true,
  },
] as const satisfies readonly PlatformModuleDefinition[];

export function platformModule(key: PlatformModuleKey): PlatformModuleDefinition {
  const module = PLATFORM_MODULES.find((item) => item.key === key);
  if (!module) throw new Error(`Unknown Foodchainservice module: ${key}`);
  return module;
}

export function registrationModules(): PlatformModuleDefinition[] {
  return PLATFORM_MODULES.filter((module) => module.registration !== "not_applicable");
}

export function canAccessPlatformModule(
  module: PlatformModuleDefinition,
  isAuthenticated: boolean,
  hasPermission: (permission: string) => boolean,
): boolean {
  if (!module.entryRoute || module.availability === "planned") return false;
  if (!isAuthenticated) return module.availability === "active";
  if (module.permissionHints.length === 0) return true;
  return module.permissionHints.some((permission) => hasPermission(permission));
}

export function shouldShowWorkspaceModule(
  module: PlatformModuleDefinition,
  isAuthenticated: boolean,
  hasPermission: (permission: string) => boolean,
): boolean {
  if (!module.workspaceVisible) return false;
  if (module.availability === "planned") return true;
  if (!isAuthenticated) return module.availability === "active";
  return canAccessPlatformModule(module, true, hasPermission);
}
