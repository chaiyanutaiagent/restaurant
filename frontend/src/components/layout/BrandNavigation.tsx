import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  ChevronDown,
  ChevronRight,
  Factory,
  Loader2,
  Settings,
  Store
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useToast } from "@/components/ui/use-toast";
import { authApi } from "@/lib/api";
import {
  brandNavigationApi,
  type BrandNavigationItem
} from "@/lib/brandNavigationApi";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth.store";

type BrandNavigationProps = {
  onNavigate: () => void;
};

function routeBrandSlug(pathname: string): string | null {
  return (
    pathname.match(/^\/(?:central|store)\/([^/]+)/)?.[1] ??
    pathname.match(/^\/brands\/([^/]+)/)?.[1] ??
    null
  );
}

export default function BrandNavigation({
  onNavigate
}: BrandNavigationProps): JSX.Element | null {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const companyId = useAuthStore((state) => state.companyId);
  const currentBranchId = useAuthStore((state) => state.branchId);
  const setSession = useAuthStore((state) => state.setSession);
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const [expandedSlugs, setExpandedSlugs] = useState<Set<string>>(new Set());
  const [switchingTarget, setSwitchingTarget] = useState<string | null>(null);

  const navigationQuery = useQuery({
    queryKey: ["brand-navigation"],
    queryFn: async () => (await brandNavigationApi.mine()).data.data,
    staleTime: 60_000
  });
  const brands = navigationQuery.data ?? [];
  const activeBrandSlug = routeBrandSlug(location.pathname);

  useEffect(() => {
    if (brands.length === 0) return;
    const defaultSlug =
      brands.find((brand) => brand.slug === activeBrandSlug)?.slug ??
      brands[0]?.slug;
    if (!defaultSlug) return;
    setExpandedSlugs((current) => {
      if (current.size > 0 || current.has(defaultSlug)) return current;
      return new Set([defaultSlug]);
    });
  }, [activeBrandSlug, brands]);

  if (navigationQuery.isLoading) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 text-xs text-gray-500">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        กำลังโหลดแบรนด์
      </div>
    );
  }
  if (brands.length === 0) return null;

  function toggleBrand(slug: string): void {
    setExpandedSlugs((current) => {
      const next = new Set(current);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  }

  async function openWorkspace(
    brand: BrandNavigationItem,
    targetBranchId: string | null,
    section: string,
    workspace: "central" | "store"
  ): Promise<void> {
    const targetKey = `${workspace}:${brand.slug}:${targetBranchId ?? "current"}`;
    setSwitchingTarget(targetKey);
    try {
      if (targetBranchId && targetBranchId !== currentBranchId) {
        if (!companyId) throw new Error("ไม่พบบริษัทของผู้ใช้");
        const response = await authApi.switchBranch(targetBranchId);
        setSession(response.data.data, companyId);
        await queryClient.invalidateQueries({ refetchType: "none" });
      }
      navigate(`/${workspace}/${brand.slug}/${section}`);
      onNavigate();
    } catch (error) {
      toast({
        title: "เปิดพื้นที่แบรนด์ไม่สำเร็จ",
        description:
          error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    } finally {
      setSwitchingTarget(null);
    }
  }

  return (
    <div className="space-y-1">
      {brands.map((brand) => {
        const isExpanded = expandedSlugs.has(brand.slug);
        const isBrandActive = activeBrandSlug === brand.slug;
        return (
          <div key={brand.id}>
            <button
              type="button"
              className={cn(
                "flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm font-semibold transition-colors",
                isBrandActive
                  ? "bg-blue-950 text-blue-100"
                  : "text-gray-200 hover:bg-gray-800 hover:text-white"
              )}
              aria-expanded={isExpanded}
              onClick={() => toggleBrand(brand.slug)}
            >
              <Store className="h-4 w-4 text-orange-400" />
              <span className="min-w-0 flex-1 truncate">{brand.name}</span>
              {isExpanded ? (
                <ChevronDown className="h-4 w-4 text-gray-400" />
              ) : (
                <ChevronRight className="h-4 w-4 text-gray-400" />
              )}
            </button>

            {isExpanded ? (
              <div className="ml-5 space-y-1 border-l border-gray-700 pl-2">
                {brand.central_landing_path ? (
                  <button
                    type="button"
                    className={cn(
                      "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors",
                      location.pathname.startsWith(`/central/${brand.slug}/`)
                        ? "bg-blue-600 text-white"
                        : "text-gray-300 hover:bg-gray-800 hover:text-white"
                    )}
                    disabled={switchingTarget !== null}
                    onClick={() =>
                      void openWorkspace(
                        brand,
                        brand.central_branch_id,
                        brand.central_landing_path!,
                        "central"
                      )
                    }
                  >
                    {switchingTarget ===
                    `central:${brand.slug}:${brand.central_branch_id ?? "current"}` ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Factory className="h-3.5 w-3.5" />
                    )}
                    <span>ส่วนกลาง</span>
                  </button>
                ) : null}

                {brand.branches.length > 0 ? (
                  <>
                    <p className="px-3 pt-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-gray-500">
                      สาขา ({brand.branches.length})
                    </p>
                    {brand.branches.map((branch) => {
                      const targetKey = `store:${brand.slug}:${branch.branch_id}`;
                      const isActive =
                        branch.is_current &&
                        location.pathname.startsWith(`/store/${brand.slug}/`);
                      return (
                        <button
                          key={branch.branch_id}
                          type="button"
                          className={cn(
                            "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors",
                            isActive
                              ? "bg-blue-600 text-white"
                              : "text-gray-300 hover:bg-gray-800 hover:text-white"
                          )}
                          disabled={switchingTarget !== null}
                          title={
                            branch.store_location_configured
                              ? branch.branch_name
                              : `${branch.branch_name} — ยังไม่ได้ตั้งค่าคลังหน้าร้าน`
                          }
                          onClick={() =>
                            void openWorkspace(
                              brand,
                              branch.branch_id,
                              branch.landing_path,
                              "store"
                            )
                          }
                        >
                          {switchingTarget === targetKey ? (
                            <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                          ) : (
                            <Building2 className="h-3.5 w-3.5 shrink-0" />
                          )}
                          <span className="min-w-0 flex-1 truncate">
                            {branch.branch_name}
                          </span>
                          {branch.is_current ? (
                            <span
                              className={cn(
                                "h-1.5 w-1.5 shrink-0 rounded-full",
                                isActive ? "bg-white" : "bg-emerald-400"
                              )}
                              aria-label="สาขาปัจจุบัน"
                            />
                          ) : null}
                        </button>
                      );
                    })}
                  </>
                ) : null}

                {hasPermission("fb.settings.manage") ? (
                  <Link
                    to="/restaurant/brands"
                    onClick={onNavigate}
                    className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-gray-400 transition-colors hover:bg-gray-800 hover:text-white"
                  >
                    <Settings className="h-3.5 w-3.5" />
                    <span>ตั้งค่าแบรนด์</span>
                  </Link>
                ) : null}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
