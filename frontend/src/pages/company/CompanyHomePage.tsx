import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  AppWindow,
  ArrowRight,
  Bell,
  CheckCircle2,
  Clock3,
  Cpu,
  Database,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { Link } from "react-router-dom";
import CompanyStatePanel from "@/components/company/CompanyStatePanel";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { companyFoundationApi } from "@/lib/api";
import {
  companyRequestState,
  dataSourceLabel,
  formatCompanyDateTime,
  operationalStateClass,
  operationalStateLabel,
  readinessClass,
  readinessLabel,
} from "@/lib/companyPresentation";
import { getDisplayName } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth.store";
import type { CompanyOverviewSection, OperationalState } from "@/types/companyFoundation";

const moduleRoute: Record<CompanyOverviewSection["module_key"], string> = {
  erp: "/dashboard",
  central_kitchen: "/company-kitchen",
  restaurant_pos: "/restaurant",
  takeaway_pos: "/takeaway",
  retail_pos: "/pos",
  hotel_pms: "",
};

const moduleName: Record<CompanyOverviewSection["module_key"], string> = {
  erp: "ERP",
  central_kitchen: "ครัวกลาง",
  restaurant_pos: "Restaurant POS",
  takeaway_pos: "Takeaway POS",
  retail_pos: "Retail POS",
  hotel_pms: "Hotel PMS",
};

function statusAttention(summary: Partial<Record<OperationalState, number>>): number {
  return ["offline", "degraded", "pending_sync", "stale", "error"]
    .reduce((total, state) => total + (summary[state as OperationalState] ?? 0), 0);
}

export default function CompanyHomePage(): JSX.Element {
  const branchId = useAuthStore((state) => state.branchId);
  const stationKey = useAuthStore((state) => state.stationKey);
  const user = useAuthStore((state) => state.user);
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const canViewOperational = ["system.device.view", "pos.sale.view", "fb.kitchen.ticket.manage"]
    .some(hasPermission);

  const overview = useQuery({
    queryKey: ["company-foundation", "overview", branchId, stationKey],
    queryFn: async () => (await companyFoundationApi.overview()).data.data,
    retry: false,
  });
  const operational = useQuery({
    queryKey: ["company-foundation", "operational-status", branchId, stationKey],
    queryFn: async () => (await companyFoundationApi.operationalStatus()).data.data,
    enabled: canViewOperational,
    retry: false,
  });

  const refreshAll = async (): Promise<void> => {
    await Promise.all([
      overview.refetch(),
      ...(canViewOperational ? [operational.refetch()] : []),
    ]);
  };

  if (overview.isLoading) {
    return (
      <div data-testid="company-dashboard-loading">
        <div className="mb-5 space-y-2"><Skeleton className="h-9 w-72" /><Skeleton className="h-5 w-[28rem] max-w-full" /></div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((item) => <Skeleton key={item} className="h-32 rounded-2xl" />)}
        </div>
        <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.65fr)_minmax(20rem,0.75fr)]">
          <Skeleton className="h-[28rem] rounded-2xl" /><Skeleton className="h-[28rem] rounded-2xl" />
        </div>
      </div>
    );
  }

  if (overview.error || !overview.data) {
    const kind = companyRequestState(overview.error);
    return (
      <CompanyStatePanel
        kind={kind}
        title={kind === "permission_denied" ? "ไม่มีสิทธิ์เปิด Dashboard บริษัท" : undefined}
        onRetry={() => void overview.refetch()}
      />
    );
  }

  const data = overview.data;
  const taskTotal = data.task_summary.total ?? 0;
  const deviceAttention = operational.data ? statusAttention(operational.data.summary) : 0;
  const displayName = getDisplayName(user?.display_name ?? null, user?.username ?? "ผู้ใช้งาน");
  const attentionComponents = operational.data?.components
    .filter((component) => component.state !== "online" && component.state !== "disabled")
    .sort((left, right) => right.queue_size - left.queue_size)
    .slice(0, 5) ?? [];

  return (
    <div data-testid="company-dashboard">
      <PageHeader
        title={`สวัสดี ${displayName}`}
        subtitle={`ภาพรวม ${data.context.company.name} · ${data.context.branch?.name ?? "ทุกสาขาที่มีสิทธิ์"} · อัปเดต ${formatCompanyDateTime(data.generated_at)}`}
        actions={(
          <Button variant="outline" onClick={() => void refreshAll()} disabled={overview.isFetching || operational.isFetching}>
            <RefreshCw className={(overview.isFetching || operational.isFetching) ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            อัปเดตข้อมูล
          </Button>
        )}
      />

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="สรุปงานและสถานะ">
        <Link to="/company/actions" className="rounded-2xl border border-red-100 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2">
          <div className="flex items-center justify-between"><span className="rounded-xl bg-red-50 p-2.5 text-red-600"><ShieldAlert className="h-5 w-5" /></span><ArrowRight className="h-4 w-4 text-slate-300" /></div>
          <p className="mt-4 text-sm font-semibold text-slate-500">งานเร่งด่วน</p>
          <p className="mt-1 text-3xl font-black text-slate-950">{(data.task_summary.blocker ?? 0) + (data.task_summary.error ?? 0)}</p>
          <p className="mt-1 text-xs text-slate-500">Blocker และข้อผิดพลาดที่ต้องตรวจ</p>
        </Link>
        <Link to="/company/actions" className="rounded-2xl border border-amber-100 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2">
          <div className="flex items-center justify-between"><span className="rounded-xl bg-amber-50 p-2.5 text-amber-700"><Bell className="h-5 w-5" /></span><ArrowRight className="h-4 w-4 text-slate-300" /></div>
          <p className="mt-4 text-sm font-semibold text-slate-500">งานทั้งหมด</p>
          <p className="mt-1 text-3xl font-black text-slate-950">{taskTotal}</p>
          <p className="mt-1 text-xs text-slate-500">ยังไม่อ่าน {data.task_summary.unread ?? 0} รายการ</p>
        </Link>
        <Link to="/company/apps" className="rounded-2xl border border-blue-100 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2">
          <div className="flex items-center justify-between"><span className="rounded-xl bg-blue-50 p-2.5 text-blue-700"><AppWindow className="h-5 w-5" /></span><ArrowRight className="h-4 w-4 text-slate-300" /></div>
          <p className="mt-4 text-sm font-semibold text-slate-500">ระบบของบริษัท</p>
          <p className="mt-1 text-3xl font-black text-slate-950">{data.sections.filter((section) => section.readiness !== "planned").length}</p>
          <p className="mt-1 text-xs text-slate-500">แสดงตามสิทธิ์และ Release Gate</p>
        </Link>
        <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between"><span className="rounded-xl bg-slate-100 p-2.5 text-slate-700"><Cpu className="h-5 w-5" /></span>{canViewOperational ? <Badge className={deviceAttention ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}>{deviceAttention ? "ต้องตรวจ" : "ปกติ"}</Badge> : null}</div>
          <p className="mt-4 text-sm font-semibold text-slate-500">Device / Sync</p>
          <p className="mt-1 text-3xl font-black text-slate-950">{canViewOperational ? deviceAttention : "—"}</p>
          <p className="mt-1 text-xs text-slate-500">{canViewOperational ? "รายการที่ไม่อยู่ในสถานะออนไลน์" : "ข้อมูลจำกัดตามสิทธิ์"}</p>
        </article>
      </section>

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(21rem,0.75fr)]">
        <section className="rounded-2xl border border-slate-200 bg-white shadow-sm" aria-labelledby="company-products-title">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
            <div><p className="text-xs font-black uppercase tracking-[0.18em] text-blue-700">Product readiness</p><h2 id="company-products-title" className="mt-1 text-lg font-black">ระบบของบริษัท</h2></div>
            <Link to="/company/apps" className="inline-flex min-h-11 items-center gap-1 px-2 text-sm font-bold text-blue-700">ดูแอปทั้งหมด <ArrowRight className="h-4 w-4" /></Link>
          </div>
          <div className="grid gap-3 p-4 md:grid-cols-2 2xl:grid-cols-3">
            {data.sections.map((section) => {
              const route = moduleRoute[section.module_key];
              const disabled = !route || ["planned", "dark_launch"].includes(section.readiness);
              const card = (
                <article className={disabled ? "h-full rounded-2xl border border-slate-200 bg-slate-50 p-4 opacity-80" : "h-full rounded-2xl border border-slate-200 bg-white p-4 transition hover:border-blue-300 hover:shadow-md"}>
                  <div className="flex items-start justify-between gap-2">
                    <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 font-black text-blue-700">{moduleName[section.module_key].slice(0, 2)}</span>
                    <Badge className={readinessClass[section.readiness]}>{readinessLabel[section.readiness]}</Badge>
                  </div>
                  <h3 className="mt-4 font-black text-slate-950">{moduleName[section.module_key]}</h3>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500"><Database className="h-3.5 w-3.5" />{dataSourceLabel(section.data_source)}{section.stale ? <Badge className="border-orange-200 bg-orange-50 text-orange-800">ข้อมูลเก่า</Badge> : null}</div>
                  <div className="mt-3 flex items-center justify-between text-xs"><span className={`rounded-full border px-2 py-1 font-bold ${operationalStateClass[section.status]}`}>{operationalStateLabel[section.status]}</span>{!disabled ? <ArrowRight className="h-4 w-4 text-blue-600" /> : null}</div>
                </article>
              );
              return disabled ? <div key={section.module_key}>{card}</div> : (
                <Link key={section.module_key} to={route} className="rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2">
                  {card}
                </Link>
              );
            })}
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white shadow-sm" aria-labelledby="operational-title">
          <div className="border-b border-slate-200 px-5 py-4">
            <p className="text-xs font-black uppercase tracking-[0.18em] text-blue-700">Operations</p>
            <h2 id="operational-title" className="mt-1 text-lg font-black">สถานะอุปกรณ์และการซิงก์</h2>
          </div>
          <div className="p-4">
            {!canViewOperational ? <CompanyStatePanel compact kind="permission_denied" /> : null}
            {canViewOperational && operational.isLoading ? <CompanyStatePanel compact kind="loading" /> : null}
            {canViewOperational && operational.error ? (
              <CompanyStatePanel compact kind={companyRequestState(operational.error)} onRetry={() => void operational.refetch()} />
            ) : null}
            {canViewOperational && operational.data && attentionComponents.length === 0 ? (
              <CompanyStatePanel compact kind="empty" title="ทุกองค์ประกอบอยู่ในสถานะปกติ" description="ไม่พบ Device หรือ Sync ที่ต้องดำเนินการในขณะนี้" />
            ) : null}
            {attentionComponents.length > 0 ? (
              <div className="space-y-2">
                {attentionComponents.map((component) => (
                  <article key={component.id} className="rounded-xl border border-slate-200 p-3">
                    <div className="flex items-start justify-between gap-2"><div className="min-w-0"><p className="truncate text-sm font-bold text-slate-950">{component.name}</p><p className="mt-1 truncate text-xs text-slate-500">{component.source_system}</p></div><Badge className={operationalStateClass[component.state]}>{operationalStateLabel[component.state]}</Badge></div>
                    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500"><span>คิว {component.queue_size}</span><span>ล่าสุด {formatCompanyDateTime(component.last_sync_at ?? component.last_seen_at)}</span></div>
                  </article>
                ))}
              </div>
            ) : null}
          </div>
        </section>
      </div>

      <section className="mt-5 rounded-2xl border border-slate-200 bg-white shadow-sm" aria-labelledby="module-overview-title">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4"><div><p className="text-xs font-black uppercase tracking-[0.18em] text-blue-700">Overview</p><h2 id="module-overview-title" className="mt-1 text-lg font-black">ภาพรวมจากแต่ละระบบ</h2></div><span className="text-xs text-slate-500">ข้อมูล ณ {formatCompanyDateTime(data.generated_at)}</span></div>
        <div className="grid gap-4 p-4 lg:grid-cols-2 2xl:grid-cols-3">
          {data.sections.filter((section) => section.readiness !== "planned").map((section) => (
            <article key={section.module_key} className="rounded-2xl border border-slate-200 p-4">
              <div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="font-black">{section.title}</h3><p className="mt-1 text-xs text-slate-500">{dataSourceLabel(section.data_source)}</p></div><Badge className={operationalStateClass[section.status]}>{operationalStateLabel[section.status]}</Badge></div>
              {section.error_code ? <p className="mt-3 flex items-center gap-2 rounded-lg bg-red-50 p-2 text-xs text-red-800"><AlertTriangle className="h-4 w-4" />{section.error_code}</p> : null}
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {section.metrics.map((metric) => {
                  const content = <div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">{metric.label}</p><p className="mt-1 text-lg font-black text-slate-950">{String(metric.value)}</p></div>;
                  return metric.deep_link ? <Link key={metric.key} to={metric.deep_link}>{content}</Link> : <div key={metric.key}>{content}</div>;
                })}
              </div>
              <p className="mt-3 flex items-center gap-1 text-[11px] text-slate-400"><Clock3 className="h-3.5 w-3.5" />อัปเดต {formatCompanyDateTime(section.updated_at)}{section.stale ? " · ข้อมูลเก่า" : ""}</p>
            </article>
          ))}
        </div>
      </section>

      {taskTotal === 0 ? (
        <div className="mt-5 flex items-center gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-900">
          <CheckCircle2 className="h-6 w-6 shrink-0" /><div><p className="font-black">ไม่มีงานค้างในบริบทปัจจุบัน</p><p className="text-sm text-emerald-800">Action Center พร้อมรับรายการใหม่จากทุกระบบตามสิทธิ์ของคุณ</p></div>
        </div>
      ) : null}
    </div>
  );
}
