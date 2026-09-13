import {
  ArrowLeftRight,
  BarChart2,
  BookOpen,
  Building2,
  ChefHat,
  ClipboardCheck,
  ClipboardList,
  Cpu,
  Clock,
  CreditCard,
  Globe2,
  LayoutDashboard,
  Link2,
  LogOut,
  Package,
  Ruler,
  FileText,
  UtensilsCrossed,
  Warehouse,
  Shield,
  ShoppingCart,
  Store,
  Settings,
  Table2,
  Truck,
  Users,
  X
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { NavLink } from "react-router-dom";
import { useLogout } from "@/hooks/useAuth";
import { getDisplayName } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth.store";
import type { BranchSettings } from "@/types/admin";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import BrandNavigation from "@/components/layout/BrandNavigation";
import { cn } from "@/lib/utils";
import { syncStockBalances, useLowStockCount } from "@/lib/syncService";
import { branchApi, userApi } from "@/lib/adminApi";
import { fbApi } from "@/lib/fbApi";
import { brandNavigationApi } from "@/lib/brandNavigationApi";
import { PLATFORM_BRAND } from "@/config/platformBrand";

type SidebarProps = {
  workspace?: "admin" | "restaurant";
  isSidebarOpen: boolean;
  onClose: () => void;
};

type NavItem = {
  label: string;
  to: string;
  icon: typeof LayoutDashboard;
  permission?: string;
  permissions?: string[];
  feature?: "tables";
};

const mainItems: NavItem[] = [
  { label: "Company Admin", to: "/admin", icon: LayoutDashboard },
  { label: "แพ็กเกจ SaaS", to: "/billing", icon: CreditCard },
  { label: "Privacy & Support", to: "/privacy-support", icon: Shield },
  { label: "ผู้ใช้งาน", to: "/users", icon: Users, permission: "system.user.view" },
  { label: "บทบาท", to: "/roles", icon: Shield, permission: "system.role.view" },
  { label: "สาขา", to: "/branches", icon: Building2, permission: "system.branch.view" },
  { label: "อุปกรณ์", to: "/devices", icon: Cpu, permission: "system.device.view" }
];

const comingSoonItems: NavItem[] = [
  { label: "ขายสินค้า", to: "/pos", icon: ShoppingCart, permission: "pos.sale.create" },
  { label: "POS Admin", to: "/pos/admin", icon: Settings, permissions: ["pos.sale.view", "pos.sale.create", "pos.report.view", "system.company.edit"] },
  { label: "ลูกค้า", to: "/crm", icon: Users, permission: "pos.sale.view" },
  { label: "สินค้า", to: "/products", icon: Package, permission: "inventory.product.view" },
  { label: "หน่วยสินค้า", to: "/units", icon: Ruler, permission: "inventory.product.view" },
  { label: "คลังสินค้า", to: "/stock", icon: Warehouse, permissions: ["inventory.stock.view", "inventory.stock.adjust.request"] }
];

const reportItems: NavItem[] = [
  { label: "รายงาน", to: "/reports", icon: BarChart2, permission: "pos.report.view" },
  { label: "ประวัติกะ", to: "/shift-history", icon: Clock, permission: "pos.report.view" }
];

const purchaseItems: NavItem[] = [
  { label: "ผู้จำหน่าย", to: "/purchase/suppliers", icon: Truck, permission: "inventory.purchase.view" },
  { label: "ใบสั่งซื้อ", to: "/purchase/orders", icon: ClipboardList, permission: "inventory.purchase.view" }
];

const accountingItems: NavItem[] = [
  { label: "บัญชี", to: "/accounting", icon: BookOpen, permission: "accounting.report.view" },
  { label: "เจ้าหนี้", to: "/payable", icon: CreditCard, permission: "accounting.payment.view" },
  { label: "ใบกำกับภาษี", to: "/etax", icon: FileText, permission: "accounting.invoice.view" }
];

const hrItems: NavItem[] = [
  { label: "พนักงาน", to: "/hr", icon: Users, permission: "hr.employee.view" }
];

const transferItems: NavItem[] = [
  { label: "โอนย้ายสินค้า", to: "/transfer/orders", icon: ArrowLeftRight, permission: "inventory.transfer.view" },
  { label: "สต็อกทุกสาขา", to: "/stock/multi-branch", icon: Globe2, permission: "inventory.stock.view" },
  { label: "นับสินค้า", to: "/stock-count", icon: ClipboardCheck, permission: "inventory.stock.view" }
];

const integrationItems: NavItem[] = [
  { label: "API & Webhooks", to: "/integrations", icon: Link2, permission: "system.company.edit" }
];

const logisticsItems: NavItem[] = [
  { label: "การจัดส่ง", to: "/logistics", icon: Truck, permission: "pos.sale.view" }
];

const settingsItems: NavItem[] = [
  { label: "ตั้งค่าระบบ", to: "/settings", icon: Settings, permission: "system.company.edit" }
]

const fbItems: NavItem[] = [
  { label: "ภาพรวม F&B", to: "/restaurant", icon: UtensilsCrossed, permissions: ["fb.menu.view", "fb.table.manage", "fb.order.create", "fb.kitchen.ticket.manage", "fb.kitchen.manage", "fb.recipe.manage", "fb.report.view", "fb.settings.manage"] },
]

const fbSubItems: NavItem[] = [
  { label: "แบรนด์ร้านอาหาร", to: "/restaurant/brands", icon: Store, permission: "fb.settings.manage" },
  { label: "ขาย / รับกลับ", to: "/restaurant/wap", icon: ShoppingCart, permission: "fb.order.create" },
  { label: "ออเดอร์", to: "/restaurant/orders", icon: ClipboardList, permission: "fb.order.create" },
  { label: "โต๊ะ", to: "/restaurant/tables", icon: Table2, permission: "fb.table.manage", feature: "tables" },
  { label: "ครัว", to: "/restaurant/kitchen", icon: ChefHat, permissions: ["fb.kitchen.ticket.manage", "fb.kitchen.manage"] },
  { label: "เมนูและสูตรอาหาร", to: "/restaurant/recipes", icon: BookOpen, permission: "fb.recipe.manage" },
  { label: "รายงาน", to: "/restaurant/reports/ingredients", icon: BarChart2, permission: "fb.report.view" },
  { label: "ตั้งค่า F&B", to: "/restaurant/settings", icon: Settings, permission: "fb.settings.manage" },
];

const fbPermissionCodes = ["fb.menu.view", "fb.table.manage", "fb.order.create", "fb.kitchen.ticket.manage", "fb.kitchen.manage", "fb.recipe.manage", "fb.report.view", "fb.settings.manage"];

function canShowItem(item: NavItem, hasPermission: (code: string) => boolean): boolean {
  if (item.permission && !hasPermission(item.permission)) return false;
  if (item.permissions?.length && !item.permissions.some((code) => hasPermission(code))) return false;
  return true;
}

export default function Sidebar({
  workspace = "admin",
  isSidebarOpen,
  onClose
}: SidebarProps): JSX.Element {
  const businessSlug = useAuthStore((state) => state.businessSlug);
  const logout = useLogout(businessSlug ? `/${businessSlug}` : "/login");
  const user = useAuthStore((state) => state.user);
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const hasFbAccess = fbPermissionCodes.some((code) => hasPermission(code));
  const lowStockCount = useLowStockCount();
  const usersCountQuery = useQuery({
    queryKey: ["sidebar", "users-count"],
    enabled: hasPermission("system.user.view"),
    queryFn: async () => (await userApi.list({ limit: 1 })).data.meta.total ?? 0
  });
  const branchesCountQuery = useQuery({
    queryKey: ["sidebar", "branches-count"],
    enabled: hasPermission("system.branch.view"),
    queryFn: async () => (await branchApi.list()).data.data.length
  });
  const branchId = useAuthStore((s) => s.branchId);
  const fbSettingsQuery = useQuery({
    queryKey: ["branch-settings", branchId],
    enabled: Boolean(branchId) && hasFbAccess,
    queryFn: async () => (await fbApi.settings()).data.data as BranchSettings,
  });
  const fbEnabled = fbSettingsQuery.data?.fb_enabled ?? false;
  const brandNavigationQuery = useQuery({
    queryKey: ["brand-navigation"],
    enabled: workspace === "restaurant" && hasFbAccess,
    queryFn: async () => (await brandNavigationApi.mine()).data.data,
    staleTime: 60_000,
  });
  const currentBrand = brandNavigationQuery.data?.find((brand) =>
    brand.branches.some((branch) => branch.branch_id === branchId),
  );
  const currentBrandBranch = currentBrand?.branches.find((branch) => branch.branch_id === branchId);
  const hasTables = fbSettingsQuery.data
    ? fbSettingsQuery.data.fb_service_mode !== "quick_service"
    : false;
  const activeColor = workspace === "restaurant" ? "bg-orange-600" : "bg-blue-600";
  const brandTitle = workspace === "restaurant" ? (currentBrand?.name ?? "Restaurant") : PLATFORM_BRAND.productName;
  const brandSubtitle = workspace === "restaurant"
    ? `Restaurant${currentBrandBranch ? ` · ${currentBrandBranch.branch_name}` : ""}`
    : "Company Admin";

  useEffect(() => {
    if (hasPermission("inventory.stock.view") || hasPermission("inventory.stock.adjust.request")) {
      void syncStockBalances();
    }
  }, [hasPermission]);

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 flex w-72 flex-col bg-gray-900 text-gray-100 transition-transform duration-200 lg:static lg:translate-x-0",
        isSidebarOpen ? "translate-x-0" : "-translate-x-full"
      )}
    >
      <div className="flex items-center justify-between border-b border-gray-800 px-5 py-4">
        <div>
          <p className="text-lg font-semibold text-white">{brandTitle}</p>
          <p className="text-xs text-gray-400">{brandSubtitle}</p>
        </div>
        <Button variant="ghost" size="icon" className="text-gray-300 lg:hidden" onClick={onClose}>
          <X className="h-5 w-5" />
        </Button>
      </div>

      <div className="border-b border-gray-800 px-4 py-4">
        <div className="flex items-center gap-3 rounded-lg bg-gray-800/60 px-3 py-3">
          <Avatar className="h-10 w-10">
            <AvatarFallback>
              {user?.username.slice(0, 2).toUpperCase() ?? "AD"}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-white">
              {getDisplayName(user?.display_name ?? null, user?.username ?? "guest")}
            </p>
            <p className="truncate text-xs text-gray-400">@{user?.username ?? "guest"}</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-6 overflow-y-auto px-4 py-5">
        {workspace === "restaurant" ? (
          <>
            <div className="space-y-3">
              <p className="px-3 text-xs uppercase tracking-[0.25em] text-gray-500">
                Restaurant
              </p>
              {fbItems
                .filter((item) => canShowItem(item, hasPermission))
                .map((item) => (
                  <NavLink
                    key={item.to}
                    to={fbEnabled || !hasPermission("fb.settings.manage") ? item.to : "/restaurant/setup"}
                    onClick={onClose}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                        isActive ? "bg-orange-600 text-white" : "text-gray-300 hover:bg-gray-800 hover:text-white"
                      )
                    }
                  >
                    <item.icon className="h-4 w-4" />
                    <span>{item.label}</span>
                    {!fbEnabled && <span className="ml-auto rounded-full bg-orange-500 px-2 py-0.5 text-[10px] text-white">ตั้งค่า</span>}
                  </NavLink>
                ))}
              {fbEnabled && fbSubItems
                .filter((item) => canShowItem(item, hasPermission))
                .filter((item) => item.feature !== "tables" || hasTables)
                .map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to === "/admin" && businessSlug ? `/${businessSlug}/admin` : item.to}
                    onClick={onClose}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                        isActive ? "bg-orange-600 text-white" : "text-gray-300 hover:bg-gray-800 hover:text-white"
                      )
                    }
                  >
                    <item.icon className="h-4 w-4" />
                    <span>{item.label}</span>
                  </NavLink>
                ))}
            </div>

            <div className="space-y-3">
              <p className="px-3 text-xs uppercase tracking-[0.25em] text-gray-500">Switch</p>
              {[
                { label: "ร้านอาหาร", to: "/restaurant/orders", icon: ShoppingCart, permissions: ["brand.store.order.create", "fb.order.create"] },
                { label: "เปิด POS", to: "/pos", icon: ShoppingCart, permission: "pos.sale.create" },
                { label: "POS Admin", to: "/pos/admin", icon: Settings, permission: "pos.sale.view" },
                { label: "ERP Admin", to: "/admin", icon: LayoutDashboard }
              ]
                .filter((item) => canShowItem(item, hasPermission))
                .map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to === "/admin" && businessSlug ? `/${businessSlug}/admin` : item.to}
                    onClick={onClose}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                        isActive ? activeColor + " text-white" : "text-gray-300 hover:bg-gray-800 hover:text-white"
                      )
                    }
                  >
                    <item.icon className="h-4 w-4" />
                    <span>{item.label}</span>
                  </NavLink>
                ))}
            </div>
          </>
        ) : (
          <>
        <div className="space-y-2">
          {mainItems
            .filter((item) => !item.permission || hasPermission(item.permission))
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to === "/admin" && businessSlug ? `/${businessSlug}/admin` : item.to}
                onClick={onClose}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? activeColor + " text-white"
                      : "text-gray-300 hover:bg-gray-800 hover:text-white"
                  )
                }
              >
                <item.icon className="h-4 w-4" />
                <span className="flex items-center gap-2">
                  {item.label}
                  {item.to === "/users" && usersCountQuery.data ? (
                    <Badge variant="secondary">{usersCountQuery.data}</Badge>
                  ) : null}
                  {item.to === "/branches" && branchesCountQuery.data ? (
                    <Badge variant="secondary">{branchesCountQuery.data}</Badge>
                  ) : null}
                </span>
              </NavLink>
            ))}
        </div>

        <div className="space-y-3">
          <p className="px-3 text-xs uppercase tracking-[0.25em] text-gray-400">System</p>
        </div>

        <div className="space-y-3">
          <p className="px-3 text-xs uppercase tracking-[0.25em] text-gray-500">แบรนด์</p>
          <BrandNavigation onNavigate={onClose} />
        </div>

        <div className="space-y-3">
          <p className="px-3 text-xs uppercase tracking-[0.25em] text-gray-500">POS</p>
          {comingSoonItems
            .slice(0, 3)
            .filter((item) => !item.permission || hasPermission(item.permission))
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={onClose}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-blue-600 text-white"
                      : "text-gray-300 hover:bg-gray-800 hover:text-white"
                  )
                }
              >
                <item.icon className="h-4 w-4" />
                <span>{item.label}</span>
              </NavLink>
            ))}
        </div>

        <div className="space-y-3">
          <p className="px-3 text-xs uppercase tracking-[0.25em] text-gray-500">คลังสินค้า</p>
          {comingSoonItems
            .slice(3)
            .filter((item) => !item.permission || hasPermission(item.permission))
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={onClose}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-blue-600 text-white"
                      : "text-gray-300 hover:bg-gray-800 hover:text-white"
                  )
                }
              >
                <item.icon className="h-4 w-4" />
                <span className="flex items-center gap-2">
                  {item.label}
                  {item.to === "/stock" && lowStockCount > 0 ? (
                    <Badge variant="destructive">{lowStockCount}</Badge>
                  ) : null}
                </span>
              </NavLink>
            ))}
          {transferItems
            .filter((item) => !item.permission || hasPermission(item.permission))
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={onClose}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-blue-600 text-white"
                      : "text-gray-300 hover:bg-gray-800 hover:text-white"
                  )
                }
              >
                <item.icon className="h-4 w-4" />
                <span>{item.label}</span>
              </NavLink>
            ))}
        </div>

        <div className="space-y-3">
          <p className="px-3 text-xs uppercase tracking-[0.25em] text-gray-500">รายงาน</p>
          {reportItems
            .filter((item) => !item.permission || hasPermission(item.permission))
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={onClose}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-blue-600 text-white"
                      : "text-gray-300 hover:bg-gray-800 hover:text-white"
                  )
                }
              >
                <item.icon className="h-4 w-4" />
                <span>{item.label}</span>
              </NavLink>
            ))}
        </div>

        <div className="space-y-3">
          <p className="px-3 text-xs uppercase tracking-[0.25em] text-gray-500">การเชื่อมต่อ</p>
          {integrationItems
            .filter((item) => !item.permission || hasPermission(item.permission))
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={onClose}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-blue-600 text-white"
                      : "text-gray-300 hover:bg-gray-800 hover:text-white"
                  )
                }
              >
                <item.icon className="h-4 w-4" />
                <span>{item.label}</span>
              </NavLink>
            ))}
        </div>

        <div className="space-y-3">
          <p className="px-3 text-xs uppercase tracking-[0.25em] text-gray-500">โลจิสติกส์</p>
          {logisticsItems
            .filter((item) => !item.permission || hasPermission(item.permission))
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={onClose}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-blue-600 text-white"
                      : "text-gray-300 hover:bg-gray-800 hover:text-white"
                  )
                }
              >
                <item.icon className="h-4 w-4" />
                <span>{item.label}</span>
              </NavLink>
            ))}
        </div>

        <div className="space-y-3">
          <p className="px-3 text-xs uppercase tracking-[0.25em] text-gray-500">จัดซื้อ</p>
          {purchaseItems
            .filter((item) => !item.permission || hasPermission(item.permission))
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={onClose}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-blue-600 text-white"
                      : "text-gray-300 hover:bg-gray-800 hover:text-white"
                  )
                }
              >
                <item.icon className="h-4 w-4" />
                <span>{item.label}</span>
              </NavLink>
            ))}
        </div>

        <div className="space-y-3">
          <p className="px-3 text-xs uppercase tracking-[0.25em] text-gray-500">บัญชี</p>
          {accountingItems
            .filter((item) => !item.permission || hasPermission(item.permission))
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={onClose}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-blue-600 text-white"
                      : "text-gray-300 hover:bg-gray-800 hover:text-white"
                  )
                }
              >
                <item.icon className="h-4 w-4" />
                <span>{item.label}</span>
              </NavLink>
            ))}
        </div>

        <div className="space-y-3">
          <p className="px-3 text-xs uppercase tracking-[0.25em] text-gray-500">HR</p>
          {hrItems
            .filter((item) => !item.permission || hasPermission(item.permission))
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={onClose}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-blue-600 text-white"
                      : "text-gray-300 hover:bg-gray-800 hover:text-white"
                  )
                }
              >
                <item.icon className="h-4 w-4" />
                <span>{item.label}</span>
                </NavLink>
            ))}
        </div>
          </>
        )}

        <div className="border-t border-gray-800 pt-4">
          <div className="space-y-2">
            {settingsItems
              .filter((item) => !item.permission || hasPermission(item.permission))
              .map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  onClick={onClose}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? activeColor + " text-white"
                        : "text-gray-300 hover:bg-gray-800 hover:text-white"
                    )
                  }
                >
                  <item.icon className="h-4 w-4" />
                  <span>{item.label}</span>
                </NavLink>
              ))}
            <Button variant="ghost" className="w-full justify-start text-gray-300" onClick={logout}>
              <LogOut className="mr-2 h-4 w-4" />
              ออกจากระบบ
            </Button>
          </div>
        </div>
      </nav>
    </aside>
  );
}
