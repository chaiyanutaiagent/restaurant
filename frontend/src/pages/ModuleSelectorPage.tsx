import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  BedDouble,
  Building2,
  Factory,
  LayoutDashboard,
  Loader2,
  PackageCheck,
  ShoppingCart,
  Store,
  UtensilsCrossed,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useToast } from "@/components/ui/use-toast";
import { PLATFORM_BRAND } from "@/config/platformBrand";
import {
  PLATFORM_MODULES,
  canAccessPlatformModule,
  shouldShowWorkspaceModule,
  type PlatformModuleAvailability,
  type PlatformModuleKey,
} from "@/config/platformModules";
import { authApi, membershipApi } from "@/lib/api";
import {
  brandNavigationApi,
  type BrandNavigationBranch,
  type BrandNavigationItem,
} from "@/lib/brandNavigationApi";
import { useAuthStore } from "@/stores/auth.store";
import type { CompanyModuleAccess } from "@/types/moduleAccess";

type StoreEntry = {
  brand: BrandNavigationItem;
  branch: BrandNavigationBranch;
};

type ModulePresentation = {
  icon: LucideIcon;
  accent: string;
  surface: string;
  text: string;
};

const modulePresentation: Record<PlatformModuleKey, ModulePresentation> = {
  company_admin: {
    icon: Building2,
    accent: "bg-blue-600",
    surface: "border-blue-200 bg-blue-50",
    text: "text-blue-700",
  },
  erp: {
    icon: LayoutDashboard,
    accent: "bg-blue-600",
    surface: "border-blue-200 bg-blue-50",
    text: "text-blue-700",
  },
  central_kitchen: {
    icon: Factory,
    accent: "bg-violet-600",
    surface: "border-violet-200 bg-violet-50",
    text: "text-violet-700",
  },
  restaurant_pos: {
    icon: UtensilsCrossed,
    accent: "bg-orange-600",
    surface: "border-orange-200 bg-orange-50",
    text: "text-orange-700",
  },
  takeaway_pos: {
    icon: PackageCheck,
    accent: "bg-slate-950",
    surface: "border-slate-300 bg-slate-100",
    text: "text-slate-800",
  },
  retail_pos: {
    icon: ShoppingCart,
    accent: "bg-emerald-600",
    surface: "border-emerald-200 bg-emerald-50",
    text: "text-emerald-700",
  },
  hotel_pms: {
    icon: BedDouble,
    accent: "bg-amber-600",
    surface: "border-amber-200 bg-amber-50",
    text: "text-amber-700",
  },
};

const availabilityLabel: Record<PlatformModuleAvailability, string> = {
  active: "พร้อมใช้งาน",
  dark_launch: "ทดสอบภายใน",
  planned: "อยู่ในแผนพัฒนา",
};

function branchTypeLabel(type: string): string {
  return type === "franchise" ? "แฟรนไชส์" : "สาขาบริษัท";
}

function storeKey(store: StoreEntry): string {
  return `${store.brand.slug}:${store.branch.branch_id}`;
}

function accessLabel(
  moduleAvailability: PlatformModuleAvailability,
  access: CompanyModuleAccess | undefined,
): string {
  if (!access) return availabilityLabel[moduleAvailability];
  const labels: Record<CompanyModuleAccess["reason_code"], string> = {
    enabled: "พร้อมใช้งาน",
    company_inactive: "บริษัทถูกระงับ",
    lifecycle_planned: "อยู่ในแผนพัฒนา",
    not_in_plan: "ไม่รวมในแพ็กเกจ",
    company_disabled: "บริษัทปิดไว้",
    runtime_unavailable: "ระบบยังไม่เปิด",
    permission_denied: "ไม่มีสิทธิ์ใช้งาน",
  };
  return labels[access.reason_code];
}

export default function ModuleSelectorPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const accessToken = useAuthStore((state) => state.accessToken);
  const user = useAuthStore((state) => state.user);
  const companyId = useAuthStore((state) => state.companyId);
  const currentBranchId = useAuthStore((state) => state.branchId);
  const setSession = useAuthStore((state) => state.setSession);
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const isAuthenticated = Boolean(accessToken && user);
  const [openingStoreKey, setOpeningStoreKey] = useState<string | null>(null);

  const navigationQuery = useQuery({
    queryKey: ["brand-navigation"],
    queryFn: async () => (await brandNavigationApi.mine()).data.data,
    enabled: isAuthenticated,
    staleTime: 60_000,
  });
  const moduleAccessQuery = useQuery({
    queryKey: ["membership", "modules", companyId],
    queryFn: async () => (await membershipApi.modules()).data.data,
    enabled: isAuthenticated,
    retry: false,
    staleTime: 60_000,
  });

  const stores = useMemo<StoreEntry[]>(() => {
    const entries = (navigationQuery.data ?? []).flatMap((brand) =>
      brand.branches.map((branch) => ({ brand, branch })),
    );
    return entries.sort((left, right) => {
      if (left.branch.is_current !== right.branch.is_current) {
        return left.branch.is_current ? -1 : 1;
      }
      return left.branch.branch_name.localeCompare(right.branch.branch_name, "th");
    });
  }, [navigationQuery.data]);
  const moduleAccessByKey = useMemo(
    () => new Map((moduleAccessQuery.data ?? []).map((module) => [module.module_key, module])),
    [moduleAccessQuery.data],
  );
  const workspaceModules = PLATFORM_MODULES.filter((module) => {
    if (!shouldShowWorkspaceModule(module, isAuthenticated, hasPermission)) return false;
    if (!isAuthenticated || module.key === "company_admin") return true;
    const access = moduleAccessByKey.get(module.key);
    return access ? access.user_permitted : module.availability !== "dark_launch";
  });

  async function openStore(store: StoreEntry): Promise<void> {
    const key = storeKey(store);
    setOpeningStoreKey(key);
    try {
      if (store.branch.branch_id !== currentBranchId) {
        if (!companyId) throw new Error("ไม่พบบริษัทของผู้ใช้");
        const response = await authApi.switchBranch(store.branch.branch_id);
        setSession(response.data.data, companyId);
        await queryClient.invalidateQueries({ refetchType: "none" });
      }
      navigate("/restaurant");
    } catch (error) {
      toast({
        title: "เปิดร้านไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive",
      });
    } finally {
      setOpeningStoreKey(null);
    }
  }

  return (
    <main className="min-h-screen bg-slate-100 text-slate-950">
      <div className="mx-auto w-full max-w-7xl px-5 py-10 sm:px-8 lg:py-16">
        <header className="max-w-3xl">
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-blue-600">
            {PLATFORM_BRAND.productName}
          </p>
          <h1 className="mt-3 text-3xl font-black tracking-tight md:text-5xl">เลือกพื้นที่ที่ต้องการใช้งาน</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600 md:text-base">
            เข้าร้านที่ใช้งานอยู่ได้ทันที หรือเลือก ERP, ครัวกลาง และระบบ POS ของบริษัทด้านล่าง
          </p>
        </header>

        {isAuthenticated && (navigationQuery.isLoading || stores.length > 0) ? (
          <section className="mt-10" aria-labelledby="your-stores-title">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.2em] text-violet-600">Quick access</p>
                <h2 id="your-stores-title" className="mt-1 text-2xl font-black text-slate-950">
                  ร้านของคุณ
                </h2>
              </div>
              {stores.length > 0 && hasPermission("fb.settings.manage") ? (
                <Link
                  to={hasPermission("system.company.edit") ? "/workspaces" : "/restaurant/brands"}
                  className="text-sm font-semibold text-violet-700 hover:text-violet-900"
                >
                  จัดการพื้นที่ทำงาน
                </Link>
              ) : null}
            </div>

            {navigationQuery.isLoading ? (
              <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {[0, 1, 2].map((item) => (
                  <div
                    key={item}
                    className="h-40 animate-pulse rounded-xl border border-slate-200 bg-white"
                  />
                ))}
              </div>
            ) : (
              <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {stores.map((store) => {
                  const key = storeKey(store);
                  const isOpening = openingStoreKey === key;
                  return (
                    <button
                      key={key}
                      type="button"
                      disabled={openingStoreKey !== null}
                      onClick={() => void openStore(store)}
                      className="group flex min-h-40 flex-col justify-between rounded-xl border border-violet-200 bg-white p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-violet-400 hover:shadow-md disabled:cursor-wait disabled:opacity-70"
                    >
                      <div className="flex w-full items-start gap-4">
                        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-violet-600 text-white">
                          <Store className="h-5 w-5" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="truncate text-xs font-bold uppercase tracking-[0.14em] text-violet-700">
                              {store.brand.name}
                            </span>
                            {store.branch.is_current ? (
                              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-700">
                                สาขาปัจจุบัน
                              </span>
                            ) : null}
                          </div>
                          <h3 className="mt-1 truncate text-lg font-black text-slate-950">
                            {store.branch.branch_name}
                          </h3>
                          <p className="mt-1 flex items-center gap-1.5 text-sm text-slate-500">
                            <Building2 className="h-3.5 w-3.5" />
                            {branchTypeLabel(store.branch.branch_type)}
                          </p>
                        </div>
                      </div>
                      <div className="mt-5 flex w-full items-center justify-between text-sm font-bold text-violet-700">
                        <span>เปิดระบบร้านอาหาร</span>
                        {isOpening ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" />
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </section>
        ) : null}

        <section className="mt-12" aria-labelledby="pos-types-title">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Modules</p>
            <h2 id="pos-types-title" className="mt-1 text-2xl font-black text-slate-950">
              ระบบ POS และหลังบ้าน
            </h2>
          </div>

          {isAuthenticated && moduleAccessQuery.error ? (
            <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              ตรวจสอบสิทธิ์โมดูลจากระบบกลางไม่ได้ชั่วคราว จึงปิดปุ่มเข้าใช้งานไว้เพื่อความปลอดภัย
            </div>
          ) : null}

          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {workspaceModules.map((module) => {
              const presentation = modulePresentation[module.key];
              const ModuleIcon = presentation.icon;
              const serverAccess = module.key === "company_admin"
                ? undefined
                : moduleAccessByKey.get(module.key);
              const canOpen = isAuthenticated
                ? Boolean(
                    serverAccess?.effective_access
                    && canAccessPlatformModule(module, true, hasPermission)
                  )
                : canAccessPlatformModule(module, false, hasPermission);
              const managedWorkspaceDestination = isAuthenticated
                && hasPermission("system.company.edit")
                && module.key === "restaurant_pos"
                ? "/workspaces"
                : module.entryRoute;
              const destination = managedWorkspaceDestination
                ? isAuthenticated
                  ? managedWorkspaceDestination
                  : `/login?next=${encodeURIComponent(managedWorkspaceDestination)}`
                : null;
              const content = (
                <>
                  <div>
                    <div className="flex items-start justify-between gap-3">
                      <div className={`flex h-12 w-12 items-center justify-center rounded-lg text-white ${presentation.accent}`}>
                        <ModuleIcon className="h-6 w-6" />
                      </div>
                      <span className="rounded-full bg-white/80 px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-600">
                        {accessLabel(module.availability, serverAccess)}
                      </span>
                    </div>
                    <p className={`mt-5 text-xs font-bold uppercase tracking-[0.16em] ${presentation.text}`}>
                      {module.eyebrow}
                    </p>
                    <h3 className="mt-1 text-xl font-black">{module.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-slate-600">{module.description}</p>
                    {serverAccess ? (
                      <div className="mt-4 flex flex-wrap gap-1.5 text-[10px] font-semibold text-slate-600">
                        <span className="rounded-full bg-white/70 px-2 py-1">
                          แพ็กเกจ {serverAccess.plan_included ? "รวม" : "ไม่รวม"}
                        </span>
                        <span className="rounded-full bg-white/70 px-2 py-1">
                          บริษัท {serverAccess.company_enabled ? "เปิด" : "ปิด"}
                        </span>
                        <span className="rounded-full bg-white/70 px-2 py-1">
                          ระบบ {serverAccess.runtime_ready ? "พร้อม" : "ยังไม่พร้อม"}
                        </span>
                      </div>
                    ) : null}
                  </div>
                  <div className={`mt-8 flex items-center justify-between text-sm font-bold ${presentation.text}`}>
                    <span>{canOpen ? "เข้าใช้งาน" : "ยังไม่เปิดใช้งาน"}</span>
                    {canOpen ? <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" /> : null}
                  </div>
                </>
              );
              const className = `group flex min-h-64 flex-col justify-between rounded-xl border p-5 text-left shadow-sm ${presentation.surface}`;

              return canOpen && destination ? (
                <Link
                  key={module.key}
                  data-testid={`workspace-module-${module.key}`}
                  to={destination}
                  className={`${className} transition hover:-translate-y-0.5 hover:shadow-lg`}
                >
                  {content}
                </Link>
              ) : (
                <article
                  key={module.key}
                  data-testid={`workspace-module-${module.key}`}
                  aria-disabled="true"
                  className={`${className} opacity-70`}
                >
                  {content}
                </article>
              );
            })}
          </div>
        </section>

        <footer className="mt-8 flex flex-wrap items-center gap-3 text-sm text-slate-600">
          <Link to="/store" className="rounded-md border border-slate-300 bg-white px-3 py-2 hover:bg-slate-50">
            หน้าร้านสาธารณะ
          </Link>
          {isAuthenticated ? (
            <span className="px-1 text-slate-500">
              {PLATFORM_BRAND.companyAdminName} · {user?.display_name || user?.username}
            </span>
          ) : (
            <Link to="/login" className="rounded-md border border-slate-300 bg-white px-3 py-2 hover:bg-slate-50">
              เข้าสู่ระบบ
            </Link>
          )}
        </footer>
      </div>
    </main>
  );
}
