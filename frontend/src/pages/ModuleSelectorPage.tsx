import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Building2,
  LayoutDashboard,
  Loader2,
  ShoppingCart,
  Store,
  UtensilsCrossed,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useToast } from "@/components/ui/use-toast";
import { authApi } from "@/lib/api";
import {
  brandNavigationApi,
  type BrandNavigationBranch,
  type BrandNavigationItem,
} from "@/lib/brandNavigationApi";
import { useAuthStore } from "@/stores/auth.store";

type StoreEntry = {
  brand: BrandNavigationItem;
  branch: BrandNavigationBranch;
};

const modules = [
  {
    title: "Restaurant POS",
    eyebrow: "ร้านอาหาร / คาเฟ่",
    description: "ออเดอร์ โต๊ะ (ถ้ามี) ครัว คิว และ QR รับออเดอร์",
    to: "/restaurant",
    icon: UtensilsCrossed,
    accent: "bg-orange-600",
    surface: "border-orange-200 bg-orange-50",
    text: "text-orange-700",
  },
  {
    title: "Retail POS",
    eyebrow: "ร้านค้าปลีก",
    description: "ขายหน้าร้าน สแกนสินค้า เปิดกะ รับเงิน และพิมพ์ใบเสร็จ",
    to: "/pos",
    icon: ShoppingCart,
    accent: "bg-emerald-600",
    surface: "border-emerald-200 bg-emerald-50",
    text: "text-emerald-700",
  },
  {
    title: "Brand / Franchise POS",
    eyebrow: "ร้านแบรนด์และแฟรนไชส์",
    description: "หน้าขายรายสาขา สต็อก เติมสินค้า ปิดกะ และเชื่อมส่วนกลาง",
    to: "/restaurant/brands",
    icon: Store,
    accent: "bg-violet-600",
    surface: "border-violet-200 bg-violet-50",
    text: "text-violet-700",
    isBrandModule: true,
  },
  {
    title: "ERP Admin",
    eyebrow: "ระบบจัดการหลังบ้าน",
    description: "แดชบอร์ด ผู้ใช้ สินค้า คลัง รายงาน และตั้งค่าระบบ",
    to: "/admin",
    icon: LayoutDashboard,
    accent: "bg-blue-600",
    surface: "border-blue-200 bg-blue-50",
    text: "text-blue-700",
  },
];

function branchTypeLabel(type: string): string {
  return type === "franchise" ? "แฟรนไชส์" : "สาขาบริษัท";
}

function storeKey(store: StoreEntry): string {
  return `${store.brand.slug}:${store.branch.branch_id}`;
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
      navigate(`/store/${store.brand.slug}/${store.branch.landing_path}`);
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

  function openBrandModule(): void {
    if (stores[0]) {
      void openStore(stores[0]);
      return;
    }
    navigate(hasPermission("fb.settings.manage") ? "/restaurant/brands" : "/login?next=%2F");
  }

  return (
    <main className="min-h-screen bg-slate-100 text-slate-950">
      <div className="mx-auto w-full max-w-7xl px-5 py-10 sm:px-8 lg:py-16">
        <header className="max-w-3xl">
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-500">Restaurant POS</p>
          <h1 className="mt-3 text-3xl font-black tracking-tight md:text-5xl">เลือกพื้นที่ที่ต้องการใช้งาน</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600 md:text-base">
            เข้าร้านที่ใช้งานอยู่ได้ทันที หรือเลือกประเภทระบบ POS และหลังบ้านด้านล่าง
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
                  to="/restaurant/brands"
                  className="text-sm font-semibold text-violet-700 hover:text-violet-900"
                >
                  จัดการแบรนด์และสาขา
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
                        <span>{store.branch.landing_path === "orders" ? "เปิดหน้าขาย" : "เปิดพื้นที่ร้าน"}</span>
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

          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {modules.map((module) => {
              const content = (
                <>
                  <div>
                    <div className={`flex h-12 w-12 items-center justify-center rounded-lg text-white ${module.accent}`}>
                      <module.icon className="h-6 w-6" />
                    </div>
                    <p className={`mt-5 text-xs font-bold uppercase tracking-[0.16em] ${module.text}`}>
                      {module.eyebrow}
                    </p>
                    <h3 className="mt-1 text-xl font-black">{module.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-slate-600">{module.description}</p>
                  </div>
                  <div className={`mt-8 flex items-center justify-between text-sm font-bold ${module.text}`}>
                    <span>เข้าใช้งาน</span>
                    {module.isBrandModule && openingStoreKey !== null ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" />
                    )}
                  </div>
                </>
              );
              const className = `group flex min-h-64 flex-col justify-between rounded-xl border p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg ${module.surface}`;

              if (module.isBrandModule) {
                return (
                  <button
                    key={module.title}
                    type="button"
                    className={className}
                    disabled={openingStoreKey !== null}
                    onClick={openBrandModule}
                  >
                    {content}
                  </button>
                );
              }

              return (
                <Link key={module.title} to={module.to} className={className}>
                  {content}
                </Link>
              );
            })}
          </div>
        </section>

        <footer className="mt-8 flex flex-wrap items-center gap-3 text-sm text-slate-600">
          <Link to="/store" className="rounded-md border border-slate-300 bg-white px-3 py-2 hover:bg-slate-50">
            หน้าร้านสาธารณะ
          </Link>
          {isAuthenticated ? (
            <span className="px-1 text-slate-500">เข้าสู่ระบบแล้วในชื่อ {user?.display_name || user?.username}</span>
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
