import { useQuery } from "@tanstack/react-query";
import { Building2, Grid2X2, LayoutDashboard, Store, UtensilsCrossed } from "lucide-react";
import { useCallback, useEffect, useMemo } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { authApi } from "@/lib/api";
import { wapApi } from "@/lib/wapApi";
import { useAuthStore } from "@/stores/auth.store";

const CENTRAL_NAV = [
  { label: "Orders", path: "orders", permissions: ["fb.kitchen.manage"] },
  {
    label: "Production",
    path: "production",
    permissions: [
      "brand.central.production.view",
      "brand.central.production.manage",
      "fb.kitchen.manage"
    ]
  },
  {
    label: "Stock",
    path: "stock",
    permissions: [
      "brand.central.raw_stock.view",
      "brand.central.raw_stock.manage",
      "brand.central.ready_stock.view",
      "brand.central.ready_stock.manage",
      "brand.central.production.view",
      "brand.central.production.manage",
      "fb.kitchen.manage"
    ]
  },
  { label: "Credits", path: "credits", permissions: ["fb.kitchen.manage"] },
  { label: "Recipes", path: "recipes", permissions: ["fb.recipe.manage"] },
  { label: "Reports", path: "reports", permissions: ["fb.report.view"] },
  {
    label: "Cutover",
    path: "cutover",
    permissions: [
      "brand.central.raw_stock.view",
      "brand.central.raw_stock.manage",
      "brand.central.ready_stock.view",
      "brand.central.ready_stock.manage",
      "fb.kitchen.manage"
    ]
  },
  { label: "พนักงาน", path: "staff", permissions: ["system.user.approve"] }
];

const STORE_NAV = [
  { label: "ขาย", path: "orders", permissions: ["brand.store.order.create", "fb.order.create"] },
  { label: "Stock", path: "stock", permissions: ["brand.store.stock.view", "brand.store.stock.adjust"] },
  { label: "ปิดกะ", path: "close-shift", permissions: ["brand.store.shift.close", "fb.order.create"] },
  { label: "รับสินค้า", path: "replenishment-orders", permissions: ["brand.store.replenishment.submit", "brand.store.delivery.receive", "fb.order.create"] },
  { label: "เครดิต", path: "credits", permissions: ["brand.store.replenishment.submit", "brand.store.delivery.receive", "fb.order.create"] },
  { label: "พนักงาน", path: "staff", permissions: ["system.user.request"] }
];

export default function RestaurantShell(): JSX.Element {
  const branchId = useAuthStore((state) => state.branchId);
  const companyId = useAuthStore((state) => state.companyId);
  const setSession = useAuthStore((state) => state.setSession);
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const location = useLocation();

  const branchesQuery = useQuery({
    queryKey: ["system", "my-branches"],
    queryFn: async () => (await authApi.myBranches()).data.data,
  });

  const defaultBranch = useMemo(
    () => branchesQuery.data?.find((branch) => branch.is_default) ?? branchesQuery.data?.[0] ?? null,
    [branchesQuery.data]
  );

  const handleSwitchBranch = useCallback(async (
    nextBranchId: string,
    nextStationKey: string | null = null
  ): Promise<void> => {
    if (!companyId) return;
    const response = await authApi.switchBranch(nextBranchId, nextStationKey);
    setSession(response.data.data, companyId);
  }, [companyId, setSession]);

  useEffect(() => {
    if (!branchId && defaultBranch) {
      void handleSwitchBranch(defaultBranch.branch_id, defaultBranch.station_key);
    }
  }, [branchId, defaultBranch, handleSwitchBranch]);

  const centralMatch = location.pathname.match(/^\/central\/([^/]+)(?:\/([^/]+))?/);
  const centralBrandSlug = centralMatch?.[1] ?? null;
  const centralSection = centralMatch?.[2] ?? "orders";
  const storeMatch = location.pathname.match(/^\/store\/([^/]+)(?:\/branches\/[^/]+)?(?:\/([^/]+))?/);
  const storeBrandSlug = storeMatch?.[1] ?? null;
  const storeSection = storeMatch?.[2] ?? "orders";
  const brandFeaturesQuery = useQuery({
    queryKey: ["restaurant-brand-features", centralBrandSlug],
    queryFn: async () => {
      if (!centralBrandSlug) throw new Error("Brand is required");
      return (await wapApi.brandFeatures(centralBrandSlug)).data.data;
    },
    enabled: Boolean(centralBrandSlug),
  });
  const centralProductionEnabled = brandFeaturesQuery.data?.central_production ?? false;
  const currentBranch = branchesQuery.data?.find((branch) => branch.branch_id === branchId) ?? defaultBranch;
  const activeBrandSlug = centralBrandSlug ?? storeBrandSlug;
  const workspaceLabel = centralBrandSlug ? "ครัวกลาง" : storeBrandSlug ? "หน้าร้าน" : "Restaurant";

  const contextNavigation = centralBrandSlug
    ? CENTRAL_NAV.filter((item) => (
      item.permissions.some((code) => hasPermission(code))
      && (item.path !== "production" || centralProductionEnabled)
    ))
    : STORE_NAV.filter((item) => item.permissions.some((code) => hasPermission(code)));
  const activeSection = centralBrandSlug ? centralSection : storeSection;

  return (
    <div className="flex h-screen flex-col bg-[linear-gradient(180deg,#fff7ed_0%,#f8fafc_34%,#eef2f7_100%)] text-slate-950">
      <header className="sticky top-0 z-30 shrink-0 border-b border-slate-200 bg-white/95 shadow-sm backdrop-blur">
        <div className="flex min-h-16 items-center gap-3 px-3 md:px-5 xl:px-7">
          <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-orange-600 text-white shadow-sm">
            <UtensilsCrossed className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <p className="truncate text-base font-black md:text-lg">Restaurant POS</p>
            <p className="truncate text-xs text-slate-500">
              {workspaceLabel}{activeBrandSlug ? ` · ${activeBrandSlug}` : ""}
            </p>
          </div>

          <div className="ml-auto flex min-w-0 items-center gap-2">
            {storeBrandSlug && branchesQuery.data?.length ? (
              <label className="relative hidden items-center md:flex">
                <Building2 className="pointer-events-none absolute left-3 h-4 w-4 text-orange-600" />
                <select
                  aria-label="เลือกสาขา"
                  value={currentBranch?.branch_id ?? ""}
                  onChange={(event) => {
                    const branch = branchesQuery.data?.find((row) => row.branch_id === event.target.value);
                    if (branch) void handleSwitchBranch(branch.branch_id, branch.station_key);
                  }}
                  className="h-11 max-w-[15rem] appearance-none rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-8 text-sm font-semibold text-slate-700 shadow-sm"
                >
                  {branchesQuery.data.map((branch) => (
                    <option key={`${branch.branch_id}:${branch.station_key ?? "branch"}`} value={branch.branch_id}>
                      {branch.branch_name}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <Link className="grid h-11 w-11 place-items-center rounded-xl border border-slate-200 bg-white text-slate-600 shadow-sm hover:bg-slate-50" to="/" title="เลือกพื้นที่ทำงาน">
              <Grid2X2 className="h-5 w-5" />
            </Link>
            <Link className="flex h-11 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50" to="/admin">
              <LayoutDashboard className="h-4 w-4" />
              <span className="hidden lg:inline">ERP กลาง</span>
            </Link>
          </div>
        </div>
      </header>

      {activeBrandSlug ? (
        <nav aria-label={`เมนู${workspaceLabel}`} className="app-horizontal-scroll shrink-0 overflow-x-auto border-b border-slate-800 bg-slate-950 px-3 py-2 text-white md:px-5 xl:px-7">
          <div className="app-page flex min-w-max items-center gap-1.5">
            <span className="mr-1 flex min-h-10 items-center gap-2 rounded-xl bg-slate-800 px-3 text-xs font-black uppercase tracking-wider text-slate-300">
              {storeBrandSlug ? <Store className="h-4 w-4" /> : <UtensilsCrossed className="h-4 w-4" />}
              {workspaceLabel}
            </span>
            {contextNavigation.map((item) => (
              <Link
                key={item.path}
                to={`/${centralBrandSlug ? "central" : "store"}/${activeBrandSlug}/${item.path}`}
                className={`flex min-h-10 items-center rounded-xl px-3 text-sm font-semibold transition ${activeSection === item.path ? "bg-orange-500 text-white shadow-sm" : "text-slate-300 hover:bg-slate-800 hover:text-white"}`}
              >
                {item.label}
              </Link>
            ))}
          </div>
        </nav>
      ) : null}

      <main className="min-h-0 flex-1 overflow-auto p-3 md:p-5 xl:p-7">
        <div className="app-page">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
