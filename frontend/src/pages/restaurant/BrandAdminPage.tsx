import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, Building2, CheckCircle2, ClipboardList, Coins, ExternalLink, Factory, Loader2, PackageCheck, Plus, Store, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth.store";
import type { Branch } from "@/types/user";

type BrandBranch = {
  id: string;
  branch_id: string;
  branch_name: string;
  business_type: "restaurant";
  target_database: "restaurant";
  branch_type: "company_owned" | "franchise" | string;
  store_location_id: string | null;
  is_active: boolean;
};

type Brand = {
  id: string;
  slug: string;
  name: string;
  business_type: "restaurant";
  target_database: "restaurant";
  storefront_mode: "food_stall" | "drink_shop" | string;
  theme_config: Record<string, unknown>;
  is_active: boolean;
  branches: BrandBranch[];
};

const TEMPLATE_CONFIG: Record<string, Record<string, unknown>> = {
  food_stall: {
    primary: "#f97316",
    accent: "#0f172a",
    order_mode: "quick_food",
  },
  drink_shop: {
    primary: "#16a34a",
    accent: "#0f766e",
    order_mode: "beverage",
  },
};

async function fetchBrands(): Promise<Brand[]> {
  const res = await authApi.get("/restaurant/brands");
  return res.data.data as Brand[];
}

async function fetchBranches(): Promise<Branch[]> {
  const res = await authApi.get("/system/branches");
  return res.data.data as Branch[];
}

function branchTypeLabel(type: string): string {
  return type === "franchise" ? "แฟรนไชส์" : "สาขาบริษัท";
}

function getApiErrorMessage(error: unknown): string {
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response;
    return response?.data?.detail ?? "";
  }
  return error instanceof Error ? error.message : "";
}

export default function BrandAdminPage(): JSX.Element {
  const { toast } = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((state) => state.companyId);
  const currentBranchId = useAuthStore((state) => state.branchId);
  const setSession = useAuthStore((state) => state.setSession);
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const [selectedBrandId, setSelectedBrandId] = useState<string | null>(null);
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [storefrontMode, setStorefrontMode] = useState<"food_stall" | "drink_shop">("food_stall");
  const [isActive, setIsActive] = useState(true);
  const [branchId, setBranchId] = useState("");
  const [branchType, setBranchType] = useState<"company_owned" | "franchise">("company_owned");
  const [openingBranchId, setOpeningBranchId] = useState<string | null>(null);

  const brandsQuery = useQuery({ queryKey: ["restaurant-brands"], queryFn: fetchBrands });
  const branchesQuery = useQuery({ queryKey: ["system-branches"], queryFn: fetchBranches });
  const brands = brandsQuery.data ?? [];
  const selectedBrand = brands.find((brand) => brand.id === selectedBrandId) ?? null;
  const canManageCompany = hasPermission("system.company.edit");
  const productionEntitlementQuery = useQuery({
    queryKey: ["central-production-entitlement", selectedBrandId],
    queryFn: async () => (
      await authApi.get(`/system/brands/${selectedBrandId}/modules/central-production`)
    ).data.data as { is_enabled: boolean },
    enabled: Boolean(selectedBrandId && canManageCompany),
  });
  const activeBranches = selectedBrand?.branches.filter((item) => item.is_active) ?? [];
  const franchiseBranches = activeBranches.filter((item) => item.branch_type === "franchise");
  const companyBranches = activeBranches.filter((item) => item.branch_type !== "franchise");
  const primaryBranch = activeBranches.find((item) => item.branch_id === currentBranchId) ?? activeBranches[0] ?? null;

  const availableBranches = useMemo(() => {
    const attached = new Set((selectedBrand?.branches ?? []).filter((item) => item.is_active).map((item) => item.branch_id));
    return (branchesQuery.data ?? []).filter((branch) => !attached.has(branch.id));
  }, [branchesQuery.data, selectedBrand]);

  useEffect(() => {
    if (selectedBrandId || brands.length === 0) return;
    const firstBrand = brands[0];
    setSelectedBrandId(firstBrand.id);
    setSlug(firstBrand.slug);
    setName(firstBrand.name);
    setStorefrontMode(firstBrand.storefront_mode === "drink_shop" ? "drink_shop" : "food_stall");
    setIsActive(firstBrand.is_active);
  }, [brands, selectedBrandId]);

  function resetForm(): void {
    setSelectedBrandId(null);
    setSlug("");
    setName("");
    setStorefrontMode("food_stall");
    setIsActive(true);
    setBranchId("");
    setBranchType("company_owned");
  }

  function startEdit(brand: Brand): void {
    setSelectedBrandId(brand.id);
    setSlug(brand.slug);
    setName(brand.name);
    setStorefrontMode(brand.storefront_mode === "drink_shop" ? "drink_shop" : "food_stall");
    setIsActive(brand.is_active);
    setBranchId("");
    setBranchType("company_owned");
  }

  async function openRestaurantBranch(target: BrandBranch): Promise<void> {
    if (!target.is_active) return;
    setOpeningBranchId(target.branch_id);
    try {
      if (target.branch_id !== currentBranchId) {
        if (!companyId) throw new Error("ไม่พบบริษัทของผู้ใช้");
        const response = await authApi.switchBranch(target.branch_id);
        setSession(response.data.data, companyId);
        await queryClient.invalidateQueries({ refetchType: "none" });
      }
      navigate("/restaurant");
    } catch (error) {
      toast({
        title: "เปิดระบบร้านอาหารไม่สำเร็จ",
        description: getApiErrorMessage(error) || "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive",
      });
    } finally {
      setOpeningBranchId(null);
    }
  }

  const saveBrandMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        slug: slug.trim().toLowerCase(),
        name: name.trim(),
        storefront_mode: storefrontMode,
        theme_config: TEMPLATE_CONFIG[storefrontMode],
        is_active: isActive,
      };
      if (selectedBrandId) {
        return (await authApi.patch(`/restaurant/brands/${selectedBrandId}`, payload)).data.data as Brand;
      }
      return (await authApi.post("/restaurant/brands", payload)).data.data as Brand;
    },
    onSuccess: async (brand) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["restaurant-brands"] }),
        queryClient.invalidateQueries({ queryKey: ["brand-navigation"] }),
      ]);
      toast({ title: selectedBrandId ? "อัปเดตแบรนด์แล้ว" : "สร้างแบรนด์แล้ว" });
      startEdit(brand);
    },
    onError: (error) => toast({ title: "บันทึกแบรนด์ไม่สำเร็จ", description: getApiErrorMessage(error), variant: "destructive" }),
  });

  const attachBranchMutation = useMutation({
    mutationFn: async () => {
      if (!selectedBrandId || !branchId) throw new Error("ยังไม่ได้เลือกแบรนด์หรือสาขา");
      return (await authApi.post(`/restaurant/brands/${selectedBrandId}/branches`, {
        branch_id: branchId,
        branch_type: branchType,
        is_active: true,
      })).data.data as Brand;
    },
    onSuccess: async (brand) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["restaurant-brands"] }),
        queryClient.invalidateQueries({ queryKey: ["brand-navigation"] }),
      ]);
      toast({ title: "ผูกสาขากับแบรนด์แล้ว" });
      setSelectedBrandId(brand.id);
      setBranchId("");
      setBranchType("company_owned");
    },
    onError: (error) => toast({ title: "ผูกสาขาไม่สำเร็จ", description: getApiErrorMessage(error), variant: "destructive" }),
  });

  const deactivateBranchMutation = useMutation({
    mutationFn: async (target: BrandBranch) => {
      if (!selectedBrandId) throw new Error("ยังไม่ได้เลือกแบรนด์");
      return (await authApi.delete(`/restaurant/brands/${selectedBrandId}/branches/${target.branch_id}`)).data.data as Brand;
    },
    onSuccess: async (brand) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["restaurant-brands"] }),
        queryClient.invalidateQueries({ queryKey: ["brand-navigation"] }),
      ]);
      toast({ title: "ปิดการใช้งานสาขาในแบรนด์แล้ว" });
      setSelectedBrandId(brand.id);
    },
    onError: (error) => toast({ title: "ปิดสาขาไม่สำเร็จ", description: getApiErrorMessage(error), variant: "destructive" }),
  });

  const productionEntitlementMutation = useMutation({
    mutationFn: async (isEnabled: boolean) => {
      if (!selectedBrandId) throw new Error("ยังไม่ได้เลือกแบรนด์");
      return (
        await authApi.put(`/system/brands/${selectedBrandId}/modules/central-production`, {
          is_enabled: isEnabled,
          config: {},
        })
      ).data.data as { is_enabled: boolean };
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["central-production-entitlement", selectedBrandId] }),
        queryClient.invalidateQueries({ queryKey: ["restaurant-brand-features"] }),
      ]);
      toast({ title: "อัปเดตสิทธิ์ Production แล้ว" });
    },
    onError: (error) => toast({ title: "อัปเดต Production ไม่สำเร็จ", description: getApiErrorMessage(error), variant: "destructive" }),
  });

  const isSaving = saveBrandMutation.isPending || attachBranchMutation.isPending || deactivateBranchMutation.isPending;

  return (
    <div>
      <PageHeader
        title="แบรนด์ร้านอาหาร"
        subtitle="Restaurant เป็นฟังก์ชันหลัก และแต่ละแบรนด์เป็นพื้นที่จัดการสาขา ร้าน ครัว เมนู และออเดอร์"
        actions={
          <Button variant="outline" onClick={resetForm}>
            <Plus className="mr-2 h-4 w-4" />
            สร้างแบรนด์
          </Button>
        }
      />

      <div className="grid gap-6 p-6 xl:grid-cols-[320px_1fr]">
        <aside className="space-y-2">
          {brandsQuery.isLoading ? (
            <div className="flex h-32 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              โหลดแบรนด์
            </div>
          ) : brands.length > 0 ? brands.map((brand) => (
            <button
              key={brand.id}
              type="button"
              className={`w-full rounded-lg border p-4 text-left transition ${selectedBrandId === brand.id ? "border-orange-400 bg-orange-50" : "border-slate-200 bg-white hover:border-slate-300"}`}
              onClick={() => startEdit(brand)}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-bold text-slate-950">{brand.name}</p>
                  <p className="text-sm text-slate-500">/{brand.slug}</p>
                </div>
                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${brand.is_active ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                  {brand.is_active ? "active" : "inactive"}
                </span>
              </div>
              <p className="mt-2 text-xs font-semibold text-slate-500">{brand.storefront_mode} · {brand.branches.filter((item) => item.is_active).length} สาขา</p>
            </button>
          )) : (
            <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
              ยังไม่มีแบรนด์
            </div>
          )}
        </aside>

        <main className="space-y-6">
          {selectedBrand ? (
            <section className="rounded-lg border border-slate-200 bg-white p-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-sm font-semibold uppercase text-orange-600">Restaurant Brand</p>
                  <h2 className="mt-1 text-xl font-black text-slate-950">{selectedBrand.name}</h2>
                  <p className="mt-1 text-sm text-slate-500">/{selectedBrand.slug} · {selectedBrand.storefront_mode}</p>
                </div>
                <div className="grid gap-2 sm:grid-cols-3">
                  <div className="rounded-md border border-slate-200 px-3 py-2">
                    <p className="text-xs font-semibold text-slate-500">สาขาใช้งาน</p>
                    <p className="text-lg font-black text-slate-950">{activeBranches.length}</p>
                  </div>
                  <div className="rounded-md border border-slate-200 px-3 py-2">
                    <p className="text-xs font-semibold text-slate-500">แฟรนไชส์</p>
                    <p className="text-lg font-black text-emerald-700">{franchiseBranches.length}</p>
                  </div>
                  <div className="rounded-md border border-slate-200 px-3 py-2">
                    <p className="text-xs font-semibold text-slate-500">สาขาบริษัท</p>
                    <p className="text-lg font-black text-blue-700">{companyBranches.length}</p>
                  </div>
                </div>
              </div>

              <div className="mt-5 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                <Button
                  variant="outline"
                  className="justify-start border-orange-300 bg-orange-50 text-orange-800 hover:bg-orange-100"
                  disabled={!primaryBranch || openingBranchId !== null}
                  onClick={() => primaryBranch && void openRestaurantBranch(primaryBranch)}
                >
                  {openingBranchId === primaryBranch?.branch_id
                    ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    : <Store className="mr-2 h-4 w-4" />}
                  เปิดระบบร้านอาหาร
                </Button>
                <Button asChild variant="outline" className="justify-start">
                  <Link to={`/store/${selectedBrand.slug}/close-shift`}>
                    <ClipboardList className="mr-2 h-4 w-4" />
                    ปิดกะ / สั่งสินค้า
                  </Link>
                </Button>
                <Button asChild variant="outline" className="justify-start">
                  <Link to={`/store/${selectedBrand.slug}/replenishment-orders`}>
                    <PackageCheck className="mr-2 h-4 w-4" />
                    ใบสั่งของสาขา
                  </Link>
                </Button>
                <Button asChild variant="outline" className="justify-start">
                  <Link to={`/central/${selectedBrand.slug}/orders`}>
                    <Building2 className="mr-2 h-4 w-4" />
                    ส่วนกลางแบรนด์
                  </Link>
                </Button>
                <Button asChild variant="outline" className="justify-start">
                  <Link to={`/central/${selectedBrand.slug}/credits`}>
                    <Coins className="mr-2 h-4 w-4" />
                    เครดิตแฟรนไชส์
                  </Link>
                </Button>
                <Button asChild variant="outline" className="justify-start">
                  <Link to={`/central/${selectedBrand.slug}/reports`}>
                    <BarChart3 className="mr-2 h-4 w-4" />
                    รายงานแบรนด์
                  </Link>
                </Button>
              </div>
              {canManageCompany ? (
                <div className="mt-4 flex flex-col gap-3 rounded-md border border-slate-200 bg-slate-50 p-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-start gap-3">
                    <Factory className="mt-0.5 h-5 w-5 text-slate-600" />
                    <div>
                      <p className="font-bold text-slate-950">Central kitchen / Production</p>
                      <p className="text-sm text-slate-500">เปิดเฉพาะแบรนด์ที่ใช้งานครัวกลาง</p>
                    </div>
                  </div>
                  <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                    <input
                      type="checkbox"
                      checked={productionEntitlementQuery.data?.is_enabled ?? false}
                      disabled={productionEntitlementQuery.isLoading || productionEntitlementMutation.isPending}
                      onChange={(event) => productionEntitlementMutation.mutate(event.target.checked)}
                    />
                    เปิดใช้งาน
                  </label>
                </div>
              ) : null}
            </section>
          ) : null}

          <section className="rounded-lg border border-slate-200 bg-white p-5">
            <div className="mb-4 flex items-center gap-2">
              <Store className="h-5 w-5 text-orange-600" />
              <h2 className="font-bold text-slate-950">{selectedBrandId ? "แก้ไขแบรนด์" : "สร้างแบรนด์ใหม่"}</h2>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Label>Slug</Label>
                <Input className="mt-1" value={slug} onChange={(event) => setSlug(event.target.value)} placeholder="brand-slug" />
              </div>
              <div>
                <Label>ชื่อแบรนด์</Label>
                <Input className="mt-1" value={name} onChange={(event) => setName(event.target.value)} placeholder="ชื่อแบรนด์" />
              </div>
              <div>
                <Label>Template</Label>
                <select
                  className="mt-1 h-10 w-full rounded-md border border-gray-300 px-3 text-sm"
                  value={storefrontMode}
                  onChange={(event) => setStorefrontMode(event.target.value === "drink_shop" ? "drink_shop" : "food_stall")}
                >
                  <option value="food_stall">ร้านอาหาร / food stall</option>
                  <option value="drink_shop">ร้านเครื่องดื่ม / drink shop</option>
                </select>
              </div>
              <label className="mt-6 flex items-center gap-2 text-sm font-semibold text-slate-700">
                <input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} />
                เปิดใช้งานแบรนด์
              </label>
            </div>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              {selectedBrand ? (
                <>
                  <Button asChild variant="outline">
                    <Link to={`/store/${selectedBrand.slug}/orders`}>
                      <ExternalLink className="mr-2 h-4 w-4" />
                      หน้าร้าน
                    </Link>
                  </Button>
                  <Button asChild variant="outline">
                    <Link to={`/central/${selectedBrand.slug}/orders`}>
                      <ExternalLink className="mr-2 h-4 w-4" />
                      ส่วนกลาง
                    </Link>
                  </Button>
                </>
              ) : null}
              <Button
                className="bg-orange-600 hover:bg-orange-700"
                disabled={!slug.trim() || !name.trim() || saveBrandMutation.isPending}
                onClick={() => saveBrandMutation.mutate()}
              >
                {saveBrandMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-2 h-4 w-4" />}
                {selectedBrandId ? "บันทึก" : "สร้างแบรนด์"}
              </Button>
            </div>
          </section>

          <section className="rounded-lg border border-slate-200 bg-white">
            <div className="flex items-center gap-2 border-b border-slate-200 p-4">
              <Building2 className="h-5 w-5 text-slate-700" />
              <h2 className="font-bold text-slate-950">สาขาของแบรนด์</h2>
            </div>
            {selectedBrand ? (
              <>
                <div className="grid gap-3 border-b border-slate-100 p-4 md:grid-cols-[1fr_180px_auto] md:items-end">
                  <div>
                    <Label>เพิ่มสาขา</Label>
                    <select
                      className="mt-1 h-10 w-full rounded-md border border-gray-300 px-3 text-sm"
                      value={branchId}
                      onChange={(event) => setBranchId(event.target.value)}
                    >
                      <option value="">เลือกสาขา</option>
                      {availableBranches.map((branch) => (
                        <option key={branch.id} value={branch.id}>{branch.name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <Label>ประเภทสาขา</Label>
                    <select
                      className="mt-1 h-10 w-full rounded-md border border-gray-300 px-3 text-sm"
                      value={branchType}
                      onChange={(event) => setBranchType(event.target.value === "franchise" ? "franchise" : "company_owned")}
                    >
                      <option value="company_owned">สาขาบริษัท</option>
                      <option value="franchise">แฟรนไชส์</option>
                    </select>
                  </div>
                  <Button disabled={!branchId || isSaving} onClick={() => attachBranchMutation.mutate()}>
                    {attachBranchMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
                    ผูกสาขา
                  </Button>
                </div>
                <div className="divide-y divide-slate-100">
                  {selectedBrand.branches.length > 0 ? selectedBrand.branches.map((item) => (
                    <div key={item.id} className={`grid gap-3 px-4 py-3 md:grid-cols-[1fr_auto] md:items-center ${item.is_active ? "" : "bg-slate-50 text-slate-400"}`}>
                      <div>
                        <p className="font-bold text-slate-950">{item.branch_name || item.branch_id}</p>
                        <p className="text-sm text-slate-500">{branchTypeLabel(item.branch_type)} · {item.is_active ? "ใช้งานอยู่" : "ปิดใช้งาน"}</p>
                      </div>
                      <div className="flex flex-wrap justify-end gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={!item.is_active || openingBranchId !== null}
                          onClick={() => void openRestaurantBranch(item)}
                        >
                          {openingBranchId === item.branch_id
                            ? <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                            : <ExternalLink className="mr-1 h-4 w-4" />}
                          เปิดร้าน
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-red-600 hover:bg-red-50"
                          disabled={!item.is_active || deactivateBranchMutation.isPending}
                          onClick={() => deactivateBranchMutation.mutate(item)}
                        >
                          <X className="mr-1 h-4 w-4" />
                          ปิดสาขานี้
                        </Button>
                      </div>
                    </div>
                  )) : (
                    <div className="p-8 text-center text-slate-500">ยังไม่ได้ผูกสาขา</div>
                  )}
                </div>
              </>
            ) : (
              <div className="p-8 text-center text-slate-500">เลือกหรือสร้างแบรนด์ก่อนผูกสาขา</div>
            )}
          </section>
        </main>
      </div>
    </div>
  );
}
