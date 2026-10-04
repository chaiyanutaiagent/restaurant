import { Activity, Building2, ClipboardList, CreditCard, Headphones, KeyRound, LayoutDashboard, LogOut, ShieldCheck, Users, type LucideIcon } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { usePlatformAuthStore } from "@/stores/platform-auth.store";
import { platformApi } from "@/lib/platformApi";
import { PLATFORM_BRAND } from "@/config/platformBrand";

export default function PlatformShell(): JSX.Element {
  const operator = usePlatformAuthStore((state) => state.operator);
  const clearSession = usePlatformAuthStore((state) => state.clearSession);
  const navigate = useNavigate();
  const permissions = operator?.permissions ?? [];
  const can = (permission: string) => permission === "self" || permissions.includes("*") || permissions.includes(permission);
  const roleName = operator?.role_codes?.[0]?.replaceAll("_", " ") ?? "No active role";
  const navigation: Array<{ to: string; label: string; icon: LucideIcon; permission: string }> = [
    { to: "/platform/dashboard", label: "ภาพรวมระบบ", icon: LayoutDashboard, permission: "platform.company.view" },
    { to: "/platform/companies", label: "บริษัทลูกค้า", icon: Building2, permission: "platform.company.view" },
    { to: "/platform/billing", label: "Billing", icon: CreditCard, permission: "platform.billing.view" },
    { to: "/platform/support", label: "Privacy & Support", icon: Headphones, permission: "platform.support.view" },
    { to: "/platform/audit", label: "Audit Log", icon: ClipboardList, permission: "platform.audit.view" },
    { to: "/platform/operations", label: "Operations", icon: Activity, permission: "platform.operations.view" },
    { to: "/platform/team", label: "Team & Roles", icon: Users, permission: "platform.team.view" },
    { to: "/platform/security", label: "บัญชีและความปลอดภัย", icon: KeyRound, permission: "self" },
  ];

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
              <p className="text-xs capitalize text-slate-400">{roleName} · {operator?.environment?.toUpperCase()}</p>
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
          {navigation.filter((item) => can(item.permission)).map((item) => {
            const Icon = item.icon;
            return <NavLink key={item.to} to={item.to} className={({ isActive }) => `flex min-h-12 min-w-fit items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold ${isActive ? "bg-emerald-400 text-slate-950" : "text-slate-300 hover:bg-slate-900"}`}><Icon className="h-5 w-5" />{item.label}</NavLink>;
          })}
        </nav>
        <main className="min-w-0">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
