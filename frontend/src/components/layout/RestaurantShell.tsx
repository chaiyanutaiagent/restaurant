import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { authApi } from "@/lib/api";
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

  return (
    <div className="flex h-screen flex-col bg-slate-50">
      {centralBrandSlug ? (
        <nav className="border-b border-slate-200 bg-white px-3 py-2">
          <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-2">
            <span className="mr-2 text-sm font-black uppercase tracking-wide text-slate-500">{centralBrandSlug}</span>
            {CENTRAL_NAV.filter((item) => item.permissions.some((code) => hasPermission(code))).map((item) => (
              <Link
                key={item.path}
                to={`/central/${centralBrandSlug}/${item.path}`}
                className={`rounded-md px-3 py-1.5 text-sm font-semibold transition ${centralSection === item.path ? "bg-slate-950 text-white" : "text-slate-600 hover:bg-slate-100"}`}
              >
                {item.label}
              </Link>
            ))}
          </div>
        </nav>
      ) : null}
      {storeBrandSlug ? (
        <nav className="border-b border-slate-200 bg-white px-3 py-2">
          <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-2">
            <span className="mr-2 text-sm font-black uppercase tracking-wide text-slate-500">{storeBrandSlug}</span>
            {STORE_NAV.filter((item) => item.permissions.some((code) => hasPermission(code))).map((item) => (
              <Link
                key={item.path}
                to={`/store/${storeBrandSlug}/${item.path}`}
                className={`rounded-md px-3 py-1.5 text-sm font-semibold transition ${storeSection === item.path ? "bg-slate-950 text-white" : "text-slate-600 hover:bg-slate-100"}`}
              >
                {item.label}
              </Link>
            ))}
          </div>
        </nav>
      ) : null}
      <main className="min-h-0 flex-1 overflow-auto p-3">
        <Outlet />
      </main>
    </div>
  );
}
