import {
  BarChart3,
  ChefHat,
  ClipboardList,
  Clock3,
  Construction,
  CreditCard,
  DatabaseZap,
  Factory,
  LayoutDashboard,
  PackageCheck,
  PlugZap,
  ScrollText,
  ShoppingBag,
  Truck,
  UserRoundCog,
  Users,
  Warehouse,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import {
  canAccessTakeawayArea,
  TAKEAWAY_NAVIGATION,
  type TakeawayNavigationItem,
} from "@/config/takeawayWorkspace";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth.store";

const icons: Record<string, typeof LayoutDashboard> = {
  overview: LayoutDashboard,
  "store-orders": ShoppingBag,
  "store-shifts": Clock3,
  "store-kitchen": ChefHat,
  "store-pickup": PackageCheck,
  "store-central-orders": ClipboardList,
  "store-stock": Warehouse,
  "store-transfers": Truck,
  "store-reports": BarChart3,
  "store-staff": Users,
  "central-orders": ClipboardList,
  "central-production": Factory,
  "central-stock": Warehouse,
  "central-transfers": Truck,
  "central-credits": CreditCard,
  "central-recipes": ScrollText,
  "central-reports": BarChart3,
  "central-staff": Users,
  "admin-import": DatabaseZap,
  "admin-cutover": Construction,
  "admin-erp": PlugZap,
  "admin-users": UserRoundCog,
};

function NavigationLink({ item }: { item: TakeawayNavigationItem }): JSX.Element {
  const Icon = icons[item.key] ?? LayoutDashboard;
  return (
    <NavLink
      to={item.to}
      end={item.to === "/takeaway"}
      title={item.description}
      className={({ isActive }) => cn(
        "flex min-w-fit items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold transition",
        isActive ? "bg-emerald-500 text-slate-950 shadow-sm" : "text-slate-300 hover:bg-slate-800 hover:text-white",
      )}
    >
      <Icon className="h-4 w-4" />
      {item.label}
    </NavLink>
  );
}

export default function TakeawayShell(): JSX.Element {
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const scopeTypes = useAuthStore((state) => state.scopeTypes ?? []);
  const businessType = useAuthStore((state) => state.businessType);
  const branchId = useAuthStore((state) => state.branchId);

  const visibleGroups = TAKEAWAY_NAVIGATION.map((group) => ({
    ...group,
    items: canAccessTakeawayArea(group.area, scopeTypes, hasPermission)
      ? group.items.filter((item) => item.permissions.some(hasPermission))
      : [],
  })).filter((group) => group.items.length > 0);

  return (
    <div className="min-h-screen bg-slate-100 text-slate-950">
      <header className="sticky top-0 z-30 border-b border-slate-800 bg-slate-950 text-white shadow-lg">
        <div className="flex min-h-16 items-center gap-4 border-b border-slate-800 px-4 lg:px-6">
          <div className="min-w-fit">
            <p className="text-lg font-black tracking-tight">Foodchainservice</p>
            <p className="text-[10px] font-bold uppercase tracking-[0.24em] text-emerald-400">Takeaway POS</p>
          </div>
          <div className="flex min-w-0 flex-1 items-center gap-2 overflow-hidden text-xs text-slate-400">
            <span className="rounded-full border border-slate-700 px-2.5 py-1">{businessType === "takeaway" ? "Takeaway workspace" : "Signed workspace"}</span>
            {branchId ? <span className="hidden truncate rounded-full border border-slate-700 px-2.5 py-1 md:inline">สาขา {branchId.slice(0, 8)}</span> : <span className="hidden rounded-full border border-slate-700 px-2.5 py-1 md:inline">ระดับบริษัท/แบรนด์</span>}
          </div>
          <NavLink className="min-w-fit rounded-xl border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800" to="/admin">
            ERP กลาง
          </NavLink>
        </div>
        <nav aria-label="พื้นที่ทำงาน Takeaway" className="flex gap-3 overflow-x-auto px-3 py-2 lg:px-6">
          {visibleGroups.map((group) => (
            <div key={group.area} className="flex min-w-fit items-center gap-1 border-r border-slate-800 pr-3 last:border-r-0">
              <span className="mr-1 rounded-lg bg-slate-800 px-2 py-1 text-[10px] font-black tracking-wider text-slate-400">{group.shortLabel}</span>
              {group.items.map((item) => <NavigationLink key={item.key} item={item} />)}
            </div>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-[1600px] p-3 md:p-5">
        <Outlet />
      </main>
    </div>
  );
}
