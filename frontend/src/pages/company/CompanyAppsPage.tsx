import { useQuery } from "@tanstack/react-query";
import {
  AppWindow,
  ArrowRight,
  Boxes,
  ChefHat,
  Database,
  Package,
  Search,
  ShoppingBag,
  Store,
  UtensilsCrossed,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import CompanyStatePanel from "@/components/company/CompanyStatePanel";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { companyFoundationApi } from "@/lib/api";
import {
  companyRequestState,
  dataSourceLabel,
  readinessClass,
  readinessLabel,
} from "@/lib/companyPresentation";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth.store";
import type { CompanyModuleAccess } from "@/types/moduleAccess";

const appDefinition: Record<CompanyModuleAccess["module_key"], {
  name: string;
  description: string;
  route: string;
  icon: typeof Boxes;
  accent: string;
}> = {
  erp: { name: "ERP", description: "จัดซื้อ คลังสินค้า การเงิน ภาษี และบุคลากร", route: "/dashboard", icon: Database, accent: "bg-blue-600" },
  central_kitchen: { name: "ครัวกลาง", description: "Demand วัตถุดิบ การผลิต และการกระจายสินค้า", route: "/company-kitchen", icon: ChefHat, accent: "bg-violet-600" },
  restaurant_pos: { name: "Restaurant POS", description: "หน้าร้าน โต๊ะและ QR ครัว เมนู และรายงานร้านอาหาร", route: "/restaurant", icon: UtensilsCrossed, accent: "bg-emerald-600" },
  takeaway_pos: { name: "Takeaway POS", description: "เคาน์เตอร์ ครัว คิวรับสินค้า และคลังสาขา", route: "/takeaway", icon: ShoppingBag, accent: "bg-rose-600" },
  retail_pos: { name: "Retail POS", description: "ขายปลีก สินค้า Barcode สต็อก และหน้าร้าน", route: "/pos", icon: Store, accent: "bg-orange-600" },
  hotel_pms: { name: "Hotel PMS", description: "ระบบบริหารที่พักในแผนงานอนาคต", route: "", icon: Boxes, accent: "bg-slate-500" },
};

const reasonLabel: Record<CompanyModuleAccess["reason_code"], string> = {
  enabled: "เปิดตามสิทธิ์ปัจจุบัน",
  company_inactive: "บริษัทถูกระงับการใช้งาน",
  lifecycle_planned: "อยู่ในแผนงาน ยังไม่เปิดใช้",
  not_in_plan: "แพ็กเกจปัจจุบันยังไม่รวมระบบนี้",
  company_disabled: "บริษัทปิดระบบนี้ไว้",
  runtime_unavailable: "Runtime ยังไม่พร้อม",
  permission_denied: "บทบาทปัจจุบันไม่มีสิทธิ์",
};

type ReadinessFilter = "all" | "available" | "pilot" | "restricted";

export default function CompanyAppsPage(): JSX.Element {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<ReadinessFilter>("all");
  const [permittedOnly, setPermittedOnly] = useState(true);
  const branchId = useAuthStore((state) => state.branchId);
  const stationKey = useAuthStore((state) => state.stationKey);
  const access = useQuery({
    queryKey: ["company-foundation", "access", branchId, stationKey],
    queryFn: async () => (await companyFoundationApi.access()).data.data,
    retry: false,
  });

  const modules = useMemo(() => {
    const query = search.trim().toLocaleLowerCase("th");
    return (access.data?.modules ?? [])
      .filter((module) => module.module_key !== "hotel_pms")
      .filter((module) => !permittedOnly || module.user_permitted)
      .filter((module) => {
        if (filter === "available") return module.effective_access && module.readiness !== "dark_launch";
        if (filter === "pilot") return module.readiness === "pilot" || module.readiness === "legacy";
        if (filter === "restricted") return ["dark_launch", "read_only", "planned"].includes(module.readiness) || !module.effective_access;
        return true;
      })
      .filter((module) => {
        if (!query) return true;
        const definition = appDefinition[module.module_key];
        return `${definition.name} ${definition.description} ${module.data_source}`.toLocaleLowerCase("th").includes(query);
      });
  }, [access.data?.modules, filter, permittedOnly, search]);

  if (access.isLoading) {
    return (
      <div data-testid="company-apps-loading">
        <div className="mb-5 space-y-2"><Skeleton className="h-9 w-52" /><Skeleton className="h-5 w-96 max-w-full" /></div>
        <Skeleton className="mb-5 h-16 rounded-2xl" />
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{[0, 1, 2, 3, 4].map((item) => <Skeleton key={item} className="h-72 rounded-2xl" />)}</div>
      </div>
    );
  }

  if (access.error || !access.data) {
    return <CompanyStatePanel kind={companyRequestState(access.error)} onRetry={() => void access.refetch()} />;
  }

  return (
    <div data-testid="company-app-launcher">
      <PageHeader title="แอปทั้งหมด" subtitle="เลือกพื้นที่ทำงาน ระบบจะแสดงสถานะ แหล่งข้อมูล และ action ตามสิทธิ์จาก Server" />

      <section className="mb-5 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm" aria-label="ค้นหาและกรองแอป">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">ค้นหาแอป</span>
            <Search className="pointer-events-none absolute left-3.5 top-3.5 h-4 w-4 text-slate-400" />
            <Input value={search} onChange={(event) => setSearch(event.target.value)} className="pl-10" placeholder="ค้นหาแอปหรือการทำงาน" />
          </label>
          <div className="app-horizontal-scroll flex gap-2 overflow-x-auto pb-1 xl:pb-0" role="group" aria-label="กรองสถานะแอป">
            {([
              ["all", "ทั้งหมด"],
              ["available", "เปิดใช้งาน"],
              ["pilot", "นำร่อง / Legacy"],
              ["restricted", "จำกัดการใช้งาน"],
            ] as const).map(([value, label]) => (
              <Button key={value} variant={filter === value ? "default" : "outline"} onClick={() => setFilter(value)} aria-pressed={filter === value}>{label}</Button>
            ))}
          </div>
          <label className="flex min-h-11 shrink-0 cursor-pointer items-center gap-2 rounded-xl border border-slate-200 px-3 text-sm font-semibold text-slate-700">
            <input type="checkbox" checked={permittedOnly} onChange={(event) => setPermittedOnly(event.target.checked)} className="h-4 w-4 rounded border-slate-300" />
            เฉพาะแอปที่มีสิทธิ์
          </label>
        </div>
      </section>

      {modules.length === 0 ? (
        <CompanyStatePanel kind="empty" title="ไม่พบแอปที่ตรงกับตัวกรอง" description="ลองเปลี่ยนคำค้น สถานะ หรือปิดตัวกรองเฉพาะแอปที่มีสิทธิ์" />
      ) : (
        <section className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3" aria-label="รายการแอป">
          {modules.map((module) => {
            const definition = appDefinition[module.module_key];
            const Icon = definition.icon;
            const canEnter = module.effective_access
              && Boolean(definition.route)
              && module.readiness !== "dark_launch"
              && module.allowed_actions.includes("view");
            const card = (
              <article className={cn(
                "flex h-full min-h-72 flex-col rounded-2xl border bg-white p-5 shadow-sm transition",
                canEnter ? "border-slate-200 hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md" : "border-slate-200 bg-slate-50/80",
              )}>
                <div className="flex items-start justify-between gap-3">
                  <span className={cn("rounded-2xl p-3 text-white shadow-sm", definition.accent)}><Icon className="h-6 w-6" /></span>
                  <Badge className={readinessClass[module.readiness]}>{readinessLabel[module.readiness]}</Badge>
                </div>
                <h2 className="mt-5 text-lg font-black text-slate-950">{definition.name}</h2>
                <p className="mt-1 min-h-12 text-sm leading-6 text-slate-600">{definition.description}</p>
                <div className="mt-4 space-y-2 border-t border-slate-100 pt-4 text-xs text-slate-600">
                  <p className="flex items-center gap-2"><Database className="h-4 w-4 text-slate-400" />แหล่งข้อมูล: <strong>{dataSourceLabel(module.data_source)}</strong></p>
                  <p className="flex items-center gap-2"><Store className="h-4 w-4 text-slate-400" />ขอบเขตสาขา: <strong>{module.branch_scope === "all" ? "ทุกสาขาที่มีสิทธิ์" : `${module.enabled_branch_ids.length} สาขา`}</strong></p>
                  <p className="flex items-center gap-2"><AppWindow className="h-4 w-4 text-slate-400" />Action: <strong>{module.allowed_actions.length ? module.allowed_actions.join(", ") : "ไม่มี"}</strong></p>
                </div>
                <div className="mt-auto pt-5">
                  {canEnter ? (
                    <span className="flex min-h-11 items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-sm font-bold text-white">
                      {module.readiness === "read_only" ? "ดูข้อมูล" : "เปิดระบบ"} <ArrowRight className="h-4 w-4" />
                    </span>
                  ) : (
                    <div className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-center text-xs font-semibold text-slate-600">
                      {module.status_reason ?? reasonLabel[module.reason_code]}
                    </div>
                  )}
                </div>
              </article>
            );
            return canEnter ? <Link key={module.module_key} to={definition.route}>{card}</Link> : <div key={module.module_key} aria-disabled="true">{card}</div>;
          })}
        </section>
      )}

      <div className="mt-5 flex items-start gap-3 rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
        <Package className="mt-0.5 h-5 w-5 shrink-0" />
        <p><strong>Server เป็นผู้ตัดสินสิทธิ์:</strong> หากไม่พบแอปหรือ action ที่ต้องการ โปรดติดต่อ Company Owner การแสดงปุ่มในหน้านี้ไม่สามารถข้าม Release Gate ได้</p>
      </div>
    </div>
  );
}
