import { Activity, Building2, ClipboardList, CreditCard, Headphones, KeyRound, LayoutDashboard, LogOut, ShieldCheck } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { usePlatformAuthStore } from "@/stores/platform-auth.store";
import { platformApi } from "@/lib/platformApi";
import { PLATFORM_BRAND } from "@/config/platformBrand";

export default function PlatformShell(): JSX.Element {
  const operator = usePlatformAuthStore((state) => state.operator);
  const clearSession = usePlatformAuthStore((state) => state.clearSession);
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-30 border-b border-slate-800 bg-slate-950/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] items-center justify-between px-4 py-3 md:px-6 xl:px-8">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-emerald-400 p-2.5 text-slate-950">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-emerald-300">
                Platform Control Plane
              </p>
              <h1 className="text-lg font-semibold">{PLATFORM_BRAND.platformName}</h1>
            </div>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <div className="hidden text-right sm:block">
              <p className="font-medium">{operator?.display_name}</p>
              <p className="text-xs text-slate-400">Platform Owner</p>
            </div>
            <button
              type="button"
              className="grid h-11 w-11 place-items-center rounded-xl border border-slate-700 text-slate-300 hover:bg-slate-800"
              aria-label="ออกจาก Platform"
              onClick={async () => {
                try {
                  await platformApi.logout();
                } finally {
                  clearSession();
                  navigate("/platform/login", { replace: true });
                }
              }}
            >
              <LogOut className="h-5 w-5" />
            </button>
          </div>
        </div>
      </header>
      <div className="mx-auto grid max-w-[1800px] gap-4 px-3 py-4 md:grid-cols-[240px_minmax(0,1fr)] md:gap-6 md:px-5 md:py-6 xl:px-8">
        <nav className="app-horizontal-scroll flex gap-2 overflow-x-auto md:sticky md:top-24 md:h-fit md:flex-col md:overflow-visible">
          <NavLink
            to="/platform/dashboard"
            className={({ isActive }) =>
              `flex min-h-12 min-w-fit items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold ${
                isActive ? "bg-emerald-400 text-slate-950" : "text-slate-300 hover:bg-slate-900"
              }`
            }
          >
            <LayoutDashboard className="h-5 w-5" /> ภาพรวมระบบ
          </NavLink>
          <NavLink
            to="/platform/companies"
            className={({ isActive }) =>
              `flex min-h-12 min-w-fit items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold ${
                isActive ? "bg-emerald-400 text-slate-950" : "text-slate-300 hover:bg-slate-900"
              }`
            }
          >
            <Building2 className="h-5 w-5" /> บริษัทลูกค้า
          </NavLink>
          <NavLink
            to="/platform/billing"
            className={({ isActive }) =>
              `flex min-h-12 min-w-fit items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold ${
                isActive ? "bg-emerald-400 text-slate-950" : "text-slate-300 hover:bg-slate-900"
              }`
            }
          >
            <CreditCard className="h-5 w-5" /> Billing
          </NavLink>
          <NavLink
            to="/platform/support"
            className={({ isActive }) =>
              `flex min-h-12 min-w-fit items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold ${
                isActive ? "bg-emerald-400 text-slate-950" : "text-slate-300 hover:bg-slate-900"
              }`
            }
          >
            <Headphones className="h-5 w-5" /> Privacy & Support
          </NavLink>
          <NavLink
            to="/platform/audit"
            className={({ isActive }) =>
              `flex min-h-12 min-w-fit items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold ${
                isActive ? "bg-emerald-400 text-slate-950" : "text-slate-300 hover:bg-slate-900"
              }`
            }
          >
            <ClipboardList className="h-5 w-5" /> Audit Log
          </NavLink>
          <NavLink
            to="/platform/operations"
            className={({ isActive }) =>
              `flex min-h-12 min-w-fit items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold ${
                isActive ? "bg-emerald-400 text-slate-950" : "text-slate-300 hover:bg-slate-900"
              }`
            }
          >
            <Activity className="h-5 w-5" /> Operations
          </NavLink>
          <NavLink
            to="/platform/security"
            className={({ isActive }) =>
              `flex min-h-12 min-w-fit items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold ${
                isActive ? "bg-emerald-400 text-slate-950" : "text-slate-300 hover:bg-slate-900"
              }`
            }
          >
            <KeyRound className="h-5 w-5" /> ความปลอดภัย
          </NavLink>
        </nav>
        <main className="min-w-0">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
