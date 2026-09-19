import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Boxes, ChefHat, Loader2, Package, ShoppingBag, UtensilsCrossed } from "lucide-react";
import { Link } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { companyFoundationApi } from "@/lib/api";
import type { CompanyModuleAccess } from "@/types/moduleAccess";

const appDefinition: Record<CompanyModuleAccess["module_key"], {
  name: string;
  description: string;
  route: string;
  icon: typeof Boxes;
}> = {
  erp: { name: "ERP", description: "งานหลังบ้าน บัญชี จัดซื้อ สต็อก และบุคลากร", route: "/dashboard", icon: Boxes },
  central_kitchen: { name: "ครัวกลาง", description: "วัตถุดิบ การผลิต และการกระจายสินค้า", route: "/company-kitchen", icon: ChefHat },
  restaurant_pos: { name: "Restaurant POS", description: "หน้าร้าน โต๊ะ QR ครัว และรายงานร้านอาหาร", route: "/restaurant", icon: UtensilsCrossed },
  takeaway_pos: { name: "Takeaway POS", description: "เคาน์เตอร์ ครัว จุดรับสินค้า และคลังสาขา", route: "/takeaway", icon: ShoppingBag },
  retail_pos: { name: "Retail POS", description: "ขายปลีก สินค้า ลูกค้า และงานหน้าร้าน", route: "/pos", icon: Package },
  hotel_pms: { name: "Hotel PMS", description: "ระบบบริหารที่พัก (แผนงานในอนาคต)", route: "", icon: Boxes },
};

const readinessLabel: Record<CompanyModuleAccess["readiness"], string> = {
  production: "ใช้งานจริง",
  pilot: "นำร่อง",
  dark_launch: "ทดสอบภายใน",
  read_only: "ดูข้อมูลเท่านั้น",
  legacy: "ระบบเดิม",
  planned: "แผนงาน",
};

export default function CompanyAppsPage(): JSX.Element {
  const access = useQuery({
    queryKey: ["company-foundation", "access"],
    queryFn: async () => (await companyFoundationApi.access()).data.data,
    retry: false,
  });
  const modules = access.data?.modules.filter((module) => (
    module.module_key !== "hotel_pms" && (module.company_enabled || module.plan_included)
  )) ?? [];

  return (
    <div>
      <PageHeader title="แอปทั้งหมด" subtitle="แสดงเฉพาะแอปของบริษัท พร้อมตรวจสิทธิ์และสถานะระบบจาก Backend ก่อนเปิด" />
      <div className="p-6">
        {access.isLoading ? (
          <div className="flex min-h-40 items-center justify-center rounded-xl border bg-white text-slate-500">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />กำลังตรวจสอบแอปที่ใช้งานได้
          </div>
        ) : null}
        {access.error ? (
          <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-red-800">
            ไม่สามารถตรวจสอบสิทธิ์แอปได้ ระบบจึงไม่เปิดทางลัดชั่วคราว
          </div>
        ) : null}
        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {modules.map((module) => {
            const definition = appDefinition[module.module_key];
            const Icon = definition.icon;
            const enabled = module.effective_access && Boolean(definition.route);
            const card = (
              <article className={`h-full rounded-xl border p-5 shadow-sm transition ${enabled ? "border-blue-200 bg-white hover:-translate-y-0.5 hover:shadow-md" : "border-slate-200 bg-slate-50 opacity-75"}`}>
                <div className="flex items-start justify-between gap-3">
                  <span className="rounded-xl bg-blue-100 p-3 text-blue-700"><Icon className="h-6 w-6" /></span>
                  <Badge variant="outline">{readinessLabel[module.readiness]}</Badge>
                </div>
                <h2 className="mt-5 text-lg font-black text-slate-950">{definition.name}</h2>
                <p className="mt-1 text-sm text-slate-600">{definition.description}</p>
                <p className="mt-4 text-xs text-slate-500">{enabled ? "เปิดตามสิทธิ์ปัจจุบัน" : `ยังเปิดไม่ได้: ${module.status_reason ?? module.reason_code}`}</p>
                {enabled ? <span className="mt-4 inline-flex items-center gap-1 text-sm font-bold text-blue-700">เปิดแอป <ArrowRight className="h-4 w-4" /></span> : null}
              </article>
            );
            return enabled ? <Link key={module.module_key} to={definition.route}>{card}</Link> : <div key={module.module_key}>{card}</div>;
          })}
        </section>
      </div>
    </div>
  );
}
