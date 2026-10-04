import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import CompanyStatePanel from "@/components/company/CompanyStatePanel";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { companyFoundationApi } from "@/lib/api";
import { companyRequestState, formatCompanyDateTime } from "@/lib/companyPresentation";
import type { CompanyGovernance } from "@/types/companyFoundation";

const stateStyle: Record<string, string> = {
  ready: "border-emerald-200 bg-emerald-50 text-emerald-800",
  pass: "border-emerald-200 bg-emerald-50 text-emerald-800",
  available: "border-emerald-200 bg-emerald-50 text-emerald-800",
  attention: "border-amber-200 bg-amber-50 text-amber-900",
  blocked: "border-red-200 bg-red-50 text-red-800",
  hold: "border-orange-200 bg-orange-50 text-orange-900",
  disabled: "border-slate-200 bg-slate-100 text-slate-700",
  planned: "border-violet-200 bg-violet-50 text-violet-800",
  permission_denied: "border-slate-300 bg-slate-100 text-slate-800",
  read_only: "border-blue-200 bg-blue-50 text-blue-800",
};

function StateBadge({ value }: { value: string }): JSX.Element {
  return <Badge variant="outline" className={stateStyle[value] ?? stateStyle.disabled}>{value.replaceAll("_", " ")}</Badge>;
}

export default function CompanyGovernancePage(): JSX.Element {
  const governance = useQuery({
    queryKey: ["company-foundation", "governance"],
    queryFn: async () => (await companyFoundationApi.governance()).data.data as CompanyGovernance,
    retry: false,
    staleTime: 60_000,
  });
  if (governance.isLoading) return <CompanyStatePanel kind="loading" />;
  if (governance.error || !governance.data) return <CompanyStatePanel kind={companyRequestState(governance.error)} onRetry={() => void governance.refetch()} />;
  const data = governance.data;
  return <div data-testid="company-governance-page" className="space-y-6">
    <PageHeader title="สถานะระบบและการออกเวอร์ชัน" subtitle="หลักฐานจาก Server สำหรับ Integration, Reporting, Reconciliation และ Release Gate — หน้านี้ไม่เปิด Production" />
    {governance.isStale ? <CompanyStatePanel kind="stale" compact onRetry={() => void governance.refetch()} /> : null}
    <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" aria-label="สรุปสถานะ">
      {Object.entries(data.summary).map(([key, value]) => <Card key={key}><CardContent className="p-4"><p className="text-xs font-bold uppercase text-slate-500">{key}</p><p className="mt-1 text-3xl font-black">{value}</p></CardContent></Card>)}
    </section>
    <section>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h2 className="text-xl font-black">สถานะการปฏิบัติงาน</h2><p className="text-sm text-slate-500">อัปเดต {formatCompanyDateTime(data.generated_at)} · {data.scope === "company" ? "ทั้งบริษัท" : "เฉพาะสาขา"}</p></div>
      <div className="grid gap-4 lg:grid-cols-2">
        {data.areas.map((area) => <Card key={area.key} className={area.stale ? "border-amber-300" : ""}><CardHeader className="pb-3"><div className="flex items-start justify-between gap-3"><div><CardTitle className="text-base">{area.title}</CardTitle><p className="mt-1 text-xs text-slate-500">{area.source_system} · {area.mode.replaceAll("_", " ")}</p></div><StateBadge value={area.stale ? "attention" : area.state} /></div></CardHeader><CardContent className="space-y-3"><p className="text-sm text-slate-700">{area.reason}</p>{area.metrics.length ? <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">{area.metrics.map((metric) => <div key={metric.key} className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">{metric.label}</p><p className="mt-1 text-lg font-black">{metric.value}</p></div>)}</div> : null}{area.deep_link ? <Button asChild size="sm" variant="outline"><Link to={area.deep_link}>เปิดรายละเอียด<ArrowRight className="ml-2 h-4 w-4" /></Link></Button> : null}</CardContent></Card>)}
      </div>
    </section>
    <section><h2 className="mb-3 text-xl font-black">Release Gates</h2><div className="space-y-3">{data.release_gates.map((gate) => <Card key={gate.key}><CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start"><ShieldCheck className="h-5 w-5 shrink-0 text-blue-700" /><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><strong>{gate.title}</strong><StateBadge value={gate.state} />{gate.server_enforced ? <Badge variant="outline">Server enforced</Badge> : null}</div><p className="mt-1 text-sm text-slate-600">{gate.reason}</p></div></CardContent></Card>)}</div></section>
    <section><h2 className="mb-3 text-xl font-black">ขอบเขตระบบ</h2><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{data.coverage.map((area) => <Card key={area.key}><CardContent className="p-4"><div className="flex items-start justify-between gap-2"><strong>{area.title}</strong><StateBadge value={area.state} /></div><p className="mt-2 text-sm text-slate-600">{area.release_boundary}</p><Button asChild className="mt-3" size="sm" variant="ghost"><Link to={area.entry_route}>เปิดพื้นที่งาน<ArrowRight className="ml-2 h-4 w-4" /></Link></Button></CardContent></Card>)}</div></section>
    <p className="text-xs text-slate-500">Release commit: {data.release_commit || "ยังไม่ได้ระบุ"} · Production authorized: ไม่</p>
  </div>;
}
