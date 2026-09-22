import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Search } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import CompanyStatePanel from "@/components/company/CompanyStatePanel";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { companyFoundationApi } from "@/lib/api";
import { companyRequestState, formatCompanyDateTime } from "@/lib/companyPresentation";

export default function CompanyAuditPage(): JSX.Element {
  const [action, setAction] = useState("");
  const [resource, setResource] = useState("");
  const [requestId, setRequestId] = useState("");
  const [filters, setFilters] = useState({ action: "", resource: "", request_id: "" });
  const audit = useQuery({
    queryKey: ["company-foundation", "audit", filters],
    queryFn: async () => (await companyFoundationApi.audit({ limit: 100, ...filters })).data.data,
    retry: false,
  });
  if (audit.isLoading) return <CompanyStatePanel kind="loading" />;
  if (audit.error || !audit.data) return <CompanyStatePanel kind={companyRequestState(audit.error)} onRetry={() => void audit.refetch()} />;
  return <div data-testid="company-audit-page"><PageHeader title="บันทึกการเปลี่ยนแปลงบริษัท" subtitle="หลักฐานจาก Server ตามขอบเขตบริษัทและสาขาที่คุณได้รับอนุญาต ข้อมูลลับถูกปิดบังอัตโนมัติ" /><form className="mb-4 grid gap-2 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm md:grid-cols-[1fr_1fr_1.3fr_auto]" onSubmit={(event) => { event.preventDefault(); setFilters({ action: action.trim(), resource: resource.trim(), request_id: requestId.trim() }); }}><Input value={action} onChange={(event) => setAction(event.target.value)} placeholder="Action เช่น system.user.update" /><Input value={resource} onChange={(event) => setResource(event.target.value)} placeholder="Resource เช่น User" /><Input value={requestId} onChange={(event) => setRequestId(event.target.value)} placeholder="Request ID" /><Button type="submit"><Search className="mr-2 h-4 w-4" />ค้นหา</Button></form>{audit.data.items.length === 0 ? <CompanyStatePanel kind="empty" /> : <div className="space-y-3">{audit.data.items.map((event) => <article key={event.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-start"><div><div className="flex flex-wrap items-center gap-2"><strong>{event.action}</strong><Badge variant="outline">{event.resource ?? "System"}</Badge></div><p className="mt-1 text-sm text-slate-500">{formatCompanyDateTime(event.created_at)} · ผู้ทำ {event.user_id ?? "ระบบ"}</p></div>{event.deep_link ? <Button asChild size="sm" variant="outline"><Link to={event.deep_link}>เปิดรายการ<ExternalLink className="ml-2 h-4 w-4" /></Link></Button> : null}</div><details className="mt-3 rounded-xl bg-slate-50 p-3 text-xs"><summary className="cursor-pointer font-bold">ดูหลักฐาน</summary><pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-all">{JSON.stringify(event.new_value, null, 2)}</pre></details></article>)}</div>}</div>;
}
