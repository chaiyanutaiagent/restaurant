import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Bell, Building2, Loader2, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { companyFoundationApi } from "@/lib/api";
import type { OperationalState } from "@/types/companyFoundation";

const stateLabel: Record<OperationalState, string> = {
  online: "ปกติ",
  offline: "ออฟไลน์",
  degraded: "ต้องตรวจสอบ",
  pending_sync: "รอซิงก์",
  stale: "ข้อมูลเก่า",
  error: "ผิดพลาด",
  disabled: "ยังไม่เปิด",
};

const stateClass: Record<OperationalState, string> = {
  online: "bg-emerald-100 text-emerald-800",
  offline: "bg-slate-200 text-slate-700",
  degraded: "bg-amber-100 text-amber-800",
  pending_sync: "bg-blue-100 text-blue-800",
  stale: "bg-orange-100 text-orange-800",
  error: "bg-red-100 text-red-800",
  disabled: "bg-slate-100 text-slate-500",
};

export default function CompanyHomePage(): JSX.Element {
  const overview = useQuery({
    queryKey: ["company-foundation", "overview"],
    queryFn: async () => (await companyFoundationApi.overview()).data.data,
    retry: false,
  });

  return (
    <div>
      <PageHeader
        title={overview.data?.context.company.name ?? "หน้าหลักบริษัท"}
        subtitle="ภาพรวมงาน สิทธิ์ ความพร้อมของแอป และสถานะอุปกรณ์จากข้อมูลกลางชุดเดียว"
        actions={(
          <Button variant="outline" onClick={() => void overview.refetch()} disabled={overview.isFetching}>
            <RefreshCw className={`h-4 w-4 ${overview.isFetching ? "animate-spin" : ""}`} />รีเฟรช
          </Button>
        )}
      />
      <div className="space-y-6 p-6">
        {overview.isLoading ? (
          <div className="flex min-h-48 items-center justify-center rounded-xl border bg-white text-slate-500">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" /> กำลังโหลดภาพรวมบริษัท
          </div>
        ) : null}
        {overview.error ? (
          <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-red-800">
            <AlertTriangle className="mr-2 inline h-5 w-5" />โหลดภาพรวมไม่สำเร็จ ระบบจึงไม่เปิด action จากหน้านี้
          </div>
        ) : null}
        {overview.data ? (
          <>
            <section className="grid gap-4 md:grid-cols-3">
              <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <Building2 className="h-5 w-5 text-blue-600" />
                <p className="mt-3 text-sm text-slate-500">บริบทปัจจุบัน</p>
                <p className="mt-1 text-lg font-black text-slate-950">
                  {overview.data.context.branch?.name ?? "ทุกสาขาที่มีสิทธิ์"}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {overview.data.context.environment.toUpperCase()} · {overview.data.context.currency} · {overview.data.context.timezone}
                </p>
              </article>
              <Link to="/company/actions" className="rounded-xl border border-amber-200 bg-amber-50 p-5 shadow-sm transition hover:-translate-y-0.5">
                <Bell className="h-5 w-5 text-amber-700" />
                <p className="mt-3 text-sm text-amber-800">งานและการแจ้งเตือน</p>
                <p className="mt-1 text-3xl font-black text-slate-950">{overview.data.task_summary.total ?? 0}</p>
                <p className="mt-1 text-xs text-amber-800">ยังไม่อ่าน {overview.data.task_summary.unread ?? 0} รายการ</p>
              </Link>
              <Link to="/company/apps" className="rounded-xl border border-blue-200 bg-blue-50 p-5 shadow-sm transition hover:-translate-y-0.5">
                <ArrowRight className="h-5 w-5 text-blue-700" />
                <p className="mt-3 text-sm text-blue-800">แอปทั้งหมด</p>
                <p className="mt-1 text-lg font-black text-slate-950">เลือก ERP และระบบ POS</p>
                <p className="mt-1 text-xs text-blue-700">ระบบจะตรวจสิทธิ์และ Release Gate ก่อนเปิด</p>
              </Link>
            </section>

            <section>
              <div className="mb-3">
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-blue-600">Product readiness</p>
                <h2 className="mt-1 text-xl font-black text-slate-950">สถานะระบบที่เปิดให้บริษัทใช้งาน</h2>
              </div>
              <div className="grid gap-4 xl:grid-cols-2">
                {overview.data.sections.map((section) => (
                  <article key={section.module_key} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <h3 className="font-black text-slate-950">{section.title}</h3>
                        <p className="mt-1 text-xs text-slate-500">{section.readiness} · source: {section.data_source}</p>
                      </div>
                      <Badge className={stateClass[section.status]}>{stateLabel[section.status]}</Badge>
                    </div>
                    <div className="mt-4 grid gap-2 sm:grid-cols-2">
                      {section.metrics.map((metric) => {
                        const content = (
                          <div className="rounded-lg bg-slate-50 p-3">
                            <p className="text-xs text-slate-500">{metric.label}</p>
                            <p className="mt-1 text-lg font-black text-slate-900">{metric.value}</p>
                          </div>
                        );
                        return metric.deep_link ? <Link key={metric.key} to={metric.deep_link}>{content}</Link> : <div key={metric.key}>{content}</div>;
                      })}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </>
        ) : null}
      </div>
    </div>
  );
}
