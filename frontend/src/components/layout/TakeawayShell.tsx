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

function NavigationLink({ item, vertical = false }: { item: TakeawayNavigationItem; vertical?: boolean }): JSX.Element {
  const Icon = icons[item.key] ?? LayoutDashboard;
  return (
    <NavLink
      to={item.to}
      end={item.to === "/takeaway"}
      title={item.description}
      className={({ isActive }) => cn(
        "flex min-h-11 items-center gap-3 rounded-xl px-3 py-2 text-sm font-semibold transition",
        vertical ? "w-full" : "min-w-fit",
        isActive ? "bg-emerald-500 text-slate-950 shadow-sm" : "text-slate-300 hover:bg-slate-800 hover:text-white",
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="min-w-0">
        <span className="block truncate">{item.label}</span>
        {vertical ? <span className="mt-0.5 block truncate text-[11px] font-normal opacity-70">{item.description}</span> : null}
      </span>
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
    <div className="flex min-h-screen bg-[linear-gradient(180deg,#ecfdf5_0%,#f8fafc_30%,#eef2f7_100%)] text-slate-950">
      <aside className="sticky top-0 hidden h-screen w-[18rem] shrink-0 flex-col border-r border-slate-800 bg-slate-950 text-white xl:flex">
        <div className="border-b border-slate-800 px-5 py-5">
          <p className="text-xl font-black tracking-tight">Foodchainservice</p>
          <p className="mt-1 text-[10px] font-bold uppercase tracking-[0.24em] text-emerald-400">Takeaway POS</p>
          <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-400">
            <p className="font-semibold text-slate-200">{businessType === "takeaway" ? "Takeaway workspace" : "Signed workspace"}</p>
            <p className="mt-1 truncate">{branchId ? `สาขา ${branchId.slice(0, 8)}` : "ระดับบริษัท/แบรนด์"}</p>
          </div>
        </div>
        <nav aria-label="พื้นที่ทำงาน Takeaway" className="app-horizontal-scroll flex-1 space-y-5 overflow-y-auto px-3 py-4">
          {visibleGroups.map((group) => (
            <div key={group.area} className="space-y-1">
              <p className="px-3 pb-1 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500">{group.shortLabel}</p>
              {group.items.map((item) => <NavigationLink key={item.key} item={item} vertical />)}
            </div>
          ))}
        </nav>
        <div className="border-t border-slate-800 p-3">
          <NavLink className="flex min-h-11 items-center justify-center gap-2 rounded-xl border border-slate-700 px-3 text-sm font-semibold text-slate-200 hover:bg-slate-800" to="/admin">
            <LayoutDashboard className="h-4 w-4" /> ERP กลาง
          </NavLink>
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-30 border-b border-slate-800 bg-slate-950 text-white shadow-lg xl:hidden">
          <div className="flex min-h-16 items-center gap-4 border-b border-slate-800 px-3 md:px-5">
            <div className="min-w-fit">
              <p className="text-lg font-black tracking-tight">Foodchainservice</p>
              <p className="text-[10px] font-bold uppercase tracking-[0.24em] text-emerald-400">Takeaway POS</p>
            </div>
            <div className="flex min-w-0 flex-1 items-center gap-2 overflow-hidden text-xs text-slate-400">
              <span className="truncate rounded-full border border-slate-700 px-2.5 py-1">{branchId ? `สาขา ${branchId.slice(0, 8)}` : "ระดับบริษัท/แบรนด์"}</span>
            </div>
            <NavLink className="min-w-fit rounded-xl border border-slate-700 px-3 py-2 text-sm font-semibold text-slate-200 hover:bg-slate-800" to="/admin">
              ERP กลาง
            </NavLink>
          </div>
          <nav aria-label="พื้นที่ทำงาน Takeaway" className="app-horizontal-scroll flex gap-3 overflow-x-auto px-3 py-2 md:px-5">
            {visibleGroups.map((group) => (
              <div key={group.area} className="flex min-w-fit items-center gap-1 border-r border-slate-800 pr-3 last:border-r-0">
                <span className="mr-1 rounded-lg bg-slate-800 px-2 py-1 text-[10px] font-black tracking-wider text-slate-400">{group.shortLabel}</span>
                {group.items.map((item) => <NavigationLink key={item.key} item={item} />)}
              </div>
            ))}
          </nav>
        </header>
        <main className="p-3 md:p-5 xl:p-7">
          <div className="app-page max-w-[1800px]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
