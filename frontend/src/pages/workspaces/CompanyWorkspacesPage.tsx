import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  BedDouble,
  Building2,
  Factory,
  LayoutDashboard,
  Loader2,
  PackageCheck,
  Plus,
  Power,
  RotateCcw,
  ShoppingCart,
  Store,
  UtensilsCrossed,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { platformModule } from "@/config/platformModules";
import { authApi, membershipApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth.store";
import type { CompanyModuleAccess } from "@/types/moduleAccess";
import type {
  CompanyWorkspace,
  CompanyWorkspaceProvisionRequest,
  WorkspaceModuleKey,
} from "@/types/companyWorkspace";

const moduleIcons: Record<string, LucideIcon> = {
  erp: LayoutDashboard,
  central_kitchen: Factory,
  restaurant_pos: UtensilsCrossed,
  takeaway_pos: PackageCheck,
  retail_pos: ShoppingCart,
  hotel_pms: BedDouble,
};

const accessReason: Record<CompanyModuleAccess["reason_code"], string> = {
  enabled: "พร้อมใช้งาน",
  company_inactive: "บริษัทถูกระงับ",
  lifecycle_planned: "อยู่ในแผนพัฒนา",
  not_in_plan: "ไม่รวมในแพ็กเกจ",
  company_disabled: "บริษัทปิดโมดูลไว้",
  runtime_unavailable: "ระบบยังไม่เปิด",
  permission_denied: "ไม่มีสิทธิ์ใช้งาน",
};

function errorMessage(error: unknown): string {
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response;
    return response?.data?.detail ?? "";
  }
  return error instanceof Error ? error.message : "";
}

function newIdempotencyKey(): string {
  if (typeof crypto.randomUUID === "function") return `workspace-${crypto.randomUUID()}`;
  return `workspace-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function CompanyWorkspacesPage(): JSX.Element {
  const { toast } = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((state) => state.companyId);
  const currentBranchId = useAuthStore((state) => state.branchId);
  const setSession = useAuthStore((state) => state.setSession);
  const [moduleKey, setModuleKey] = useState<WorkspaceModuleKey>("restaurant_pos");
  const [brandSlug, setBrandSlug] = useState("");
  const [brandName, setBrandName] = useState("");
  const [branchCode, setBranchCode] = useState("");
  const [branchName, setBranchName] = useState("");
  const [branchType, setBranchType] = useState<"company_owned" | "franchise">("company_owned");
  const [storefrontMode, setStorefrontMode] = useState<"food_stall" | "drink_shop">("food_stall");
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);
  const [openingWorkspaceId, setOpeningWorkspaceId] = useState<string | null>(null);

  const directoryQuery = useQuery({
    queryKey: ["membership", "workspaces", companyId],
    queryFn: async () => (await membershipApi.workspaces()).data.data,
    enabled: Boolean(companyId),
    retry: false,
  });
  const modules = directoryQuery.data?.modules ?? [];
  const sharedModules = modules.filter((module) => module.kind === "shared_service");
  const workspaceModules = modules.filter((module) => module.kind !== "shared_service");
  const provisionableModules = useMemo(
    () => workspaceModules.filter((module) => module.can_provision),
    [workspaceModules],
  );

  useEffect(() => {
    if (
      provisionableModules.length > 0
      && !provisionableModules.some((module) => module.module_key === moduleKey)
    ) {
      setModuleKey(provisionableModules[0].module_key as WorkspaceModuleKey);
      setIdempotencyKey(null);
    }
  }, [moduleKey, provisionableModules]);

  const provisionMutation = useMutation({
    mutationFn: async () => {
      const requestKey = idempotencyKey ?? newIdempotencyKey();
      setIdempotencyKey(requestKey);
      const payload: CompanyWorkspaceProvisionRequest = {
        idempotency_key: requestKey,
        module_key: moduleKey,
        brand_slug: brandSlug.trim().toLowerCase(),
        brand_name: brandName.trim(),
        branch_code: branchCode.trim().toUpperCase(),
        branch_name: branchName.trim(),
        branch_type: branchType,
        storefront_mode: storefrontMode,
      };
      return (await membershipApi.provisionWorkspace(payload)).data.data;
    },
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["membership", "workspaces", companyId] }),
        queryClient.invalidateQueries({ queryKey: ["brand-navigation"] }),
        queryClient.invalidateQueries({ queryKey: ["system-branches"] }),
      ]);
      toast({
        title: result.created ? "สร้าง Workspace แล้ว" : "Workspace นี้มีอยู่แล้ว",
        description: `${result.workspace.brand_name} · ${result.workspace.branch_name}`,
      });
      setIdempotencyKey(null);
      setBranchCode("");
      setBranchName("");
    },
    onError: (error) => toast({
      title: "สร้าง Workspace ไม่สำเร็จ",
      description: errorMessage(error) || "กรุณาตรวจสอบข้อมูลแล้วลองใหม่",
      variant: "destructive",
    }),
  });

  const statusMutation = useMutation({
    mutationFn: async ({ workspace, active }: { workspace: CompanyWorkspace; active: boolean }) => {
      const defaultReason = active ? "เปิด Workspace กลับมาใช้งาน" : "พัก Workspace โดย Company Admin";
      const reason = window.prompt("ระบุเหตุผลเพื่อบันทึก Audit Log", defaultReason);
      if (!reason?.trim()) throw new Error("ยกเลิกการเปลี่ยนสถานะ");
      return (await membershipApi.updateWorkspaceStatus(workspace.workspace_id, active, reason)).data.data;
    },
    onSuccess: async (workspace) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["membership", "workspaces", companyId] }),
        queryClient.invalidateQueries({ queryKey: ["brand-navigation"] }),
      ]);
      toast({ title: workspace.is_active ? "เปิด Workspace แล้ว" : "พัก Workspace แล้ว" });
    },
    onError: (error) => {
      const message = errorMessage(error);
      if (message === "ยกเลิกการเปลี่ยนสถานะ") return;
      toast({ title: "เปลี่ยนสถานะไม่สำเร็จ", description: message, variant: "destructive" });
    },
  });

  async function openWorkspace(workspace: CompanyWorkspace): Promise<void> {
    if (!workspace.can_open || !companyId) return;
    setOpeningWorkspaceId(workspace.workspace_id);
    try {
      if (workspace.branch_id !== currentBranchId) {
        const response = useAuthStore.getState().accessToken
          ? await authApi.switchBranch(workspace.branch_id)
          : null;
        if (!response) throw new Error("ไม่พบ Session สำหรับเปิด Workspace");
        setSession(response.data.data, companyId);
        await queryClient.invalidateQueries({ refetchType: "none" });
      }
      navigate(workspace.entry_route);
    } catch (error) {
      toast({
        title: "เปิด Workspace ไม่สำเร็จ",
        description: errorMessage(error) || "ข้อมูลอ้างอิงอาจกำลังซิงก์ กรุณาลองอีกครั้ง",
        variant: "destructive",
      });
    } finally {
      setOpeningWorkspaceId(null);
    }
  }

  const canSubmit = brandSlug.trim().length >= 2
    && brandName.trim().length > 0
    && branchCode.trim().length > 0
    && branchName.trim().length > 0
    && provisionableModules.some((module) => module.module_key === moduleKey);

  return (
    <div>
      <PageHeader
        title="พื้นที่ทำงานของบริษัท"
        subtitle="จัดการ ERP, ครัวกลาง และ POS ทุกประเภทจาก Company Admin โดยข้อมูลขอบเขตมาจากระบบกลาง"
      />

      <div className="space-y-6 p-6">
        {directoryQuery.isLoading ? (
          <div className="flex min-h-40 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" /> กำลังโหลดโครงสร้างบริษัท
          </div>
        ) : null}
        {directoryQuery.error ? (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            โหลดรายการ Workspace ไม่สำเร็จ ระบบจึงปิดการสร้างและเปิด Workspace ไว้ชั่วคราว
          </div>
        ) : null}

        {directoryQuery.data ? (
          <>
            <section aria-labelledby="shared-services-title">
              <div className="mb-3">
                <p className="text-xs font-bold uppercase tracking-[0.2em] text-blue-600">Company shared</p>
                <h2 id="shared-services-title" className="mt-1 text-xl font-black text-slate-950">ระบบส่วนกลางของบริษัท</h2>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                {sharedModules.map((module) => {
                  const definition = platformModule(module.module_key);
                  const Icon = moduleIcons[module.module_key] ?? Building2;
                  const content = (
                    <>
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-blue-600 text-white"><Icon className="h-5 w-5" /></div>
                        <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${module.access.effective_access ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                          {accessReason[module.access.reason_code]}
                        </span>
                      </div>
                      <h3 className="mt-4 text-lg font-black text-slate-950">{definition.title}</h3>
                      <p className="mt-1 text-sm leading-6 text-slate-600">{definition.description}</p>
                      <div className="mt-4 flex items-center justify-between text-sm font-bold text-blue-700">
                        <span>{module.access.effective_access ? "เข้าใช้งาน" : "ยังไม่พร้อม"}</span>
                        {module.access.effective_access ? <ArrowRight className="h-4 w-4" /> : null}
                      </div>
                    </>
                  );
                  return module.access.effective_access && module.entry_route ? (
                    <Link key={module.module_key} to={module.entry_route} className="rounded-xl border border-blue-200 bg-blue-50 p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">{content}</Link>
                  ) : (
                    <article key={module.module_key} aria-disabled="true" className="rounded-xl border border-slate-200 bg-slate-50 p-5 opacity-75">{content}</article>
                  );
                })}
              </div>
            </section>

            <section aria-labelledby="workspace-collections-title">
              <div className="mb-3">
                <p className="text-xs font-bold uppercase tracking-[0.2em] text-violet-600">Business workspaces</p>
                <h2 id="workspace-collections-title" className="mt-1 text-xl font-black text-slate-950">ระบบ POS แยกตามแบรนด์และสาขา</h2>
              </div>
              <div className="grid gap-4 xl:grid-cols-3">
                {workspaceModules.map((module) => {
                  const definition = platformModule(module.module_key);
                  const Icon = moduleIcons[module.module_key] ?? Store;
                  return (
                    <article key={module.module_key} data-testid={`company-workspace-module-${module.module_key}`} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-950 text-white"><Icon className="h-5 w-5" /></div>
                        <span className={`rounded-full px-2 py-1 text-[11px] font-bold ${module.access.effective_access ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                          {accessReason[module.access.reason_code]}
                        </span>
                      </div>
                      <h3 className="mt-3 text-lg font-black text-slate-950">{definition.title}</h3>
                      <p className="mt-1 min-h-12 text-sm leading-6 text-slate-500">{definition.description}</p>
                      <div className="mt-4 space-y-2">
                        {module.workspaces.length > 0 ? module.workspaces.map((workspace) => (
                          <div key={workspace.workspace_id} data-testid={`company-workspace-${workspace.workspace_id}`} className={`rounded-lg border p-3 ${workspace.is_active ? "border-slate-200 bg-slate-50" : "border-slate-200 bg-slate-100 opacity-70"}`}>
                            <div className="flex items-start justify-between gap-2">
                              <div className="min-w-0">
                                <p className="truncate font-bold text-slate-950">{workspace.brand_name}</p>
                                <p className="truncate text-sm text-slate-600">{workspace.branch_name} · {workspace.branch_code}</p>
                              </div>
                              <span className="shrink-0 rounded-full bg-white px-2 py-1 text-[10px] font-semibold text-slate-600">{workspace.branch_type === "franchise" ? "แฟรนไชส์" : "สาขาบริษัท"}</span>
                            </div>
                            <div className="mt-3 flex gap-2">
                              <Button size="sm" className="flex-1" disabled={!workspace.can_open || openingWorkspaceId !== null} onClick={() => void openWorkspace(workspace)}>
                                {openingWorkspaceId === workspace.workspace_id ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />} เปิด
                              </Button>
                              <Button size="sm" variant="outline" disabled={statusMutation.isPending} onClick={() => statusMutation.mutate({ workspace, active: !workspace.is_active })}>
                                {workspace.is_active ? <Power className="h-4 w-4" /> : <RotateCcw className="h-4 w-4" />}
                                {workspace.is_active ? "พัก" : "คืนค่า"}
                              </Button>
                            </div>
                          </div>
                        )) : (
                          <p className="rounded-lg border border-dashed border-slate-300 px-3 py-5 text-center text-sm text-slate-500">ยังไม่มี Workspace</p>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>

            <section className="rounded-xl border border-blue-200 bg-white p-5 shadow-sm" aria-labelledby="provision-title">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-600 text-white"><Plus className="h-5 w-5" /></div>
                <div><h2 id="provision-title" className="text-lg font-black text-slate-950">สร้าง Workspace ใหม่</h2><p className="text-sm text-slate-500">ระบบจะกำหนดขอบเขตข้อมูลจากประเภท POS ให้เอง</p></div>
              </div>
              {provisionableModules.length > 0 ? (
                <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  <div>
                    <Label htmlFor="workspace-module">ประเภทระบบ</Label>
                    <select id="workspace-module" className="mt-1 h-10 w-full rounded-md border border-gray-300 px-3 text-sm" value={moduleKey} onChange={(event) => { setModuleKey(event.target.value as WorkspaceModuleKey); setIdempotencyKey(null); }}>
                      {provisionableModules.map((module) => <option key={module.module_key} value={module.module_key}>{platformModule(module.module_key).title}</option>)}
                    </select>
                  </div>
                  <div><Label htmlFor="workspace-brand-name">ชื่อแบรนด์</Label><Input id="workspace-brand-name" className="mt-1" value={brandName} onChange={(event) => { setBrandName(event.target.value); setIdempotencyKey(null); }} placeholder="เช่น หมูแดดเดียว" /></div>
                  <div><Label htmlFor="workspace-brand-slug">รหัสแบรนด์ (slug)</Label><Input id="workspace-brand-slug" className="mt-1" value={brandSlug} onChange={(event) => { setBrandSlug(event.target.value); setIdempotencyKey(null); }} placeholder="moo-dad-deaw" /></div>
                  <div><Label htmlFor="workspace-branch-name">ชื่อสาขา</Label><Input id="workspace-branch-name" className="mt-1" value={branchName} onChange={(event) => { setBranchName(event.target.value); setIdempotencyKey(null); }} placeholder="สาขาหลัก" /></div>
                  <div><Label htmlFor="workspace-branch-code">รหัสสาขา</Label><Input id="workspace-branch-code" className="mt-1" value={branchCode} onChange={(event) => { setBranchCode(event.target.value); setIdempotencyKey(null); }} placeholder="BKK01" /></div>
                  <div>
                    <Label htmlFor="workspace-branch-type">ประเภทสาขา</Label>
                    <select id="workspace-branch-type" className="mt-1 h-10 w-full rounded-md border border-gray-300 px-3 text-sm" value={branchType} onChange={(event) => { setBranchType(event.target.value === "franchise" ? "franchise" : "company_owned"); setIdempotencyKey(null); }}>
                      <option value="company_owned">สาขาบริษัท</option><option value="franchise">แฟรนไชส์</option>
                    </select>
                  </div>
                  {moduleKey === "restaurant_pos" ? (
                    <div>
                      <Label htmlFor="workspace-template">รูปแบบร้าน</Label>
                      <select id="workspace-template" className="mt-1 h-10 w-full rounded-md border border-gray-300 px-3 text-sm" value={storefrontMode} onChange={(event) => { setStorefrontMode(event.target.value === "drink_shop" ? "drink_shop" : "food_stall"); setIdempotencyKey(null); }}>
                        <option value="food_stall">ร้านอาหาร</option><option value="drink_shop">ร้านเครื่องดื่ม</option>
                      </select>
                    </div>
                  ) : null}
                  <div className="flex items-end"><Button className="w-full" disabled={!canSubmit || provisionMutation.isPending} onClick={() => provisionMutation.mutate()}>{provisionMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} สร้าง Workspace</Button></div>
                </div>
              ) : (
                <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">ยังไม่มีโมดูล POS ที่ผ่านแพ็กเกจ สถานะบริษัท ระบบ และสิทธิ์พร้อมกัน</p>
              )}
            </section>
          </>
        ) : null}
      </div>
    </div>
  );
}
