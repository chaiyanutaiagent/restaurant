import { useQuery } from "@tanstack/react-query";
import { ClipboardList } from "lucide-react";
import { platformApi, platformErrorMessage } from "@/lib/platformApi";

export default function PlatformAuditPage(): JSX.Element {
  const audit = useQuery({
    queryKey: ["platform", "audit"],
    queryFn: async () => (await platformApi.audit()).data.data
  });

  return (
    <div className="space-y-6">
      <div><p className="text-sm font-medium text-emerald-300">Traceability</p><h2 className="mt-1 text-3xl font-bold">Platform Audit Log</h2><p className="mt-2 text-sm text-slate-400">การสร้าง ระงับ เปิดใหม่ แก้ plan และ tenant export พร้อมเหตุผลและ operator</p></div>
      {audit.isLoading ? <p className="text-slate-400">กำลังโหลด...</p> : null}
      {audit.error ? <p className="text-red-300">{platformErrorMessage(audit.error)}</p> : null}
      <div className="space-y-3">
        {audit.data?.map((event) => (
          <article key={event.id} className="rounded-xl border border-slate-700 bg-slate-900 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3"><div className="flex items-center gap-3"><ClipboardList className="h-5 w-5 text-emerald-300" /><div><h3 className="font-semibold">{event.action}</h3><p className="mt-1 text-xs text-slate-400">Company {event.company_id || "Platform"} · Operator {event.operator_id || "system"}</p></div></div><time className="text-xs text-slate-400">{new Date(event.created_at).toLocaleString("th-TH")}</time></div>
            {typeof event.new_value?.reason === "string" ? <p className="mt-4 rounded-lg bg-slate-950 px-3 py-2 text-sm text-slate-300">เหตุผล: {event.new_value.reason}</p> : null}
          </article>
        ))}
      </div>
    </div>
  );
}
