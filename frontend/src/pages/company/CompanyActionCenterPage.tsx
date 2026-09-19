import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Check, ExternalLink, Loader2, X } from "lucide-react";
import { Link } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { companyFoundationApi } from "@/lib/api";
import type { CompanyWorkItem } from "@/types/companyFoundation";

const severityClass: Record<CompanyWorkItem["severity"], string> = {
  info: "bg-blue-100 text-blue-800",
  warning: "bg-amber-100 text-amber-800",
  error: "bg-red-100 text-red-800",
  blocker: "bg-red-700 text-white",
};

export default function CompanyActionCenterPage(): JSX.Element {
  const queryClient = useQueryClient();
  const listing = useQuery({
    queryKey: ["company-foundation", "action-center"],
    queryFn: async () => (await companyFoundationApi.actionCenter()).data.data,
    retry: false,
  });
  const action = useMutation({
    mutationFn: async ({ item, next }: { item: CompanyWorkItem; next: "acknowledge" | "dismiss" }) => (
      await companyFoundationApi.actionWorkItem(
        item.id,
        next,
        next === "acknowledge" ? "รับทราบจาก Company Action Center" : "ซ่อนจากรายการส่วนตัว",
      )
    ).data.data,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["company-foundation", "action-center"] }),
        queryClient.invalidateQueries({ queryKey: ["company-foundation", "overview"] }),
      ]);
    },
  });

  return (
    <div>
      <PageHeader title="งานและการแจ้งเตือน" subtitle="รายการจากทุกโมดูลเรียงตามความรุนแรงและผลกระทบทางธุรกิจ" />
      <div className="space-y-3 p-6">
        {listing.isLoading ? (
          <div className="flex min-h-40 items-center justify-center rounded-xl border bg-white text-slate-500"><Loader2 className="mr-2 h-5 w-5 animate-spin" />กำลังโหลดรายการ</div>
        ) : null}
        {listing.data?.items.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-slate-500"><Bell className="mx-auto mb-3 h-8 w-8" />ไม่มีงานค้างในบริบทปัจจุบัน</div>
        ) : null}
        {listing.data?.items.map((item) => (
          <article key={item.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge className={severityClass[item.severity]}>{item.severity}</Badge>
                  <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{item.source_app}</span>
                  {item.unread ? <span className="h-2 w-2 rounded-full bg-blue-600" aria-label="ยังไม่อ่าน" /> : null}
                </div>
                <h2 className="mt-2 font-black text-slate-950">{item.title}</h2>
                <p className="mt-1 text-xs text-slate-500">ต้องใช้สิทธิ์ {item.permission_required}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {item.available_actions.includes("acknowledge") && item.status === "open" ? (
                  <Button variant="outline" disabled={action.isPending} onClick={() => action.mutate({ item, next: "acknowledge" })}><Check className="h-4 w-4" />รับทราบ</Button>
                ) : null}
                <Button variant="outline" disabled={action.isPending} onClick={() => action.mutate({ item, next: "dismiss" })}><X className="h-4 w-4" />ซ่อน</Button>
                <Button asChild><Link to={item.deep_link}><ExternalLink className="h-4 w-4" />เปิดรายการต้นทาง</Link></Button>
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
