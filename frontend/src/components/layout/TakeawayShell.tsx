import {
  BarChart3,
  ChefHat,
  ClipboardList,
  CreditCard,
  DatabaseZap,
  Factory,
  LayoutDashboard,
  PackageCheck,
  PlugZap,
  ShoppingBag,
  Truck,
  Warehouse,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth.store";

const navigation = [
  { to: "/takeaway", label: "ภาพรวม", icon: LayoutDashboard, permissions: ["takeaway.catalog.view"] },
  { to: "/takeaway/counter", label: "ขายหน้าร้าน", icon: ShoppingBag, permissions: ["takeaway.sale.create"] },
  { to: "/takeaway/kitchen", label: "ครัว", icon: ChefHat, permissions: ["takeaway.kitchen.manage"] },
  { to: "/takeaway/pickup", label: "รับสินค้า", icon: PackageCheck, permissions: ["takeaway.pickup.manage"] },
  { to: "/takeaway/central-orders", label: "สั่งส่วนกลาง", icon: ClipboardList, permissions: ["takeaway.central_order.create", "takeaway.central_order.manage"] },
  { to: "/takeaway/production", label: "ผลิต", icon: Factory, permissions: ["takeaway.production.manage"] },
  { to: "/takeaway/stock", label: "สต๊อกร่วม", icon: Warehouse, permissions: ["takeaway.stock.view"] },
  { to: "/takeaway/transfers", label: "โอนสินค้า", icon: Truck, permissions: ["takeaway.transfer.manage"] },
  { to: "/takeaway/credits", label: "วงเงิน", icon: CreditCard, permissions: ["takeaway.credit.manage"] },
  { to: "/takeaway/reports", label: "รายงาน", icon: BarChart3, permissions: ["takeaway.report.view"] },
  { to: "/takeaway/import", label: "นำเข้า Chambo", icon: DatabaseZap, permissions: ["takeaway.import.dry_run"] },
  { to: "/takeaway/erp", label: "เชื่อม ERP", icon: PlugZap, permissions: ["takeaway.erp.export"] },
];

export default function TakeawayShell(): JSX.Element {
  const hasPermission = useAuthStore((state) => state.hasPermission);
  return (
    <div className="min-h-screen bg-slate-100 text-slate-950">
      <header className="sticky top-0 z-30 border-b border-slate-800 bg-slate-950 text-white shadow-lg">
        <div className="flex min-h-16 items-center gap-4 px-4 lg:px-6">
          <div className="min-w-fit">
            <p className="text-lg font-black tracking-tight">Foodchainservice</p>
            <p className="text-[10px] font-bold uppercase tracking-[0.24em] text-emerald-400">Take away POS</p>
          </div>
          <nav className="flex min-w-0 flex-1 gap-1 overflow-x-auto py-2">
            {navigation.filter((item) => item.permissions.some(hasPermission)).map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/takeaway"}
                className={({ isActive }) => cn(
                  "flex min-w-fit items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold transition",
                  isActive ? "bg-emerald-500 text-slate-950" : "text-slate-300 hover:bg-slate-800 hover:text-white",
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            ))}
          </nav>
          <NavLink className="min-w-fit rounded-xl border border-slate-700 px-3 py-2 text-sm text-slate-200" to="/admin">
            ERP กลาง
          </NavLink>
        </div>
      </header>
      <main className="mx-auto max-w-[1600px] p-3 md:p-5">
        <Outlet />
      </main>
    </div>
  );
}
