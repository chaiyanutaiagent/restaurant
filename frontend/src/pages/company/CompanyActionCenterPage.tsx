import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  Check,
  ExternalLink,
  Filter,
  Search,
  UserRoundCheck,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import CompanyStatePanel from "@/components/company/CompanyStatePanel";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/use-toast";
import { companyFoundationApi } from "@/lib/api";
import { companyRequestState, formatCompanyDateTime } from "@/lib/companyPresentation";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth.store";
import type { CompanyWorkItem } from "@/types/companyFoundation";

const severityClass: Record<CompanyWorkItem["severity"], string> = {
  info: "border-blue-200 bg-blue-50 text-blue-800",
  warning: "border-amber-200 bg-amber-50 text-amber-800",
  error: "border-red-200 bg-red-50 text-red-800",
  blocker: "border-red-700 bg-red-700 text-white",
};

const severityLabel: Record<CompanyWorkItem["severity"], string> = {
  info: "ข้อมูล",
  warning: "ควรตรวจ",
  error: "ผิดพลาด",
  blocker: "เร่งด่วน",
};

const statusLabel: Record<CompanyWorkItem["status"], string> = {
  open: "เปิดอยู่",
  acknowledged: "รับทราบแล้ว",
  completed: "เสร็จแล้ว",
  dismissed: "ซ่อนแล้ว",
};

type ActionName = "assign" | "acknowledge" | "dismiss";
type ListFilter = "all" | "unread" | "mine" | "open";

function safeDeepLink(value: string): string | null {
  return value.startsWith("/") && !value.startsWith("//") ? value : null;
}

export default function CompanyActionCenterPage(): JSX.Element {
  const [filter, setFilter] = useState<ListFilter>("all");
  const [severity, setSeverity] = useState<"all" | CompanyWorkItem["severity"]>("all");
  const [source, setSource] = useState("all");
  const [search, setSearch] = useState("");
  const [online, setOnline] = useState(() => navigator.onLine);
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const branchId = useAuthStore((state) => state.branchId);
  const stationKey = useAuthStore((state) => state.stationKey);

  useEffect(() => {
    const update = (): void => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  const listing = useQuery({
    queryKey: ["company-foundation", "action-center", branchId, stationKey],
    queryFn: async () => (await companyFoundationApi.actionCenter()).data.data,
    retry: false,
  });
  const access = useQuery({
    queryKey: ["company-foundation", "access", branchId, stationKey],
    queryFn: async () => (await companyFoundationApi.access()).data.data,
    retry: false,
  });
  const action = useMutation({
    mutationFn: async ({ item, next }: { item: CompanyWorkItem; next: ActionName }) => (
      await companyFoundationApi.actionWorkItem(
        item.id,
        next,
        next === "assign"
          ? "รับผิดชอบรายการจาก Company Action Center"
          : next === "acknowledge"
            ? "รับทราบจาก Company Action Center"
            : "ซ่อนจากรายการส่วนตัว",
        next === "assign" ? access.data?.user_id : null,
      )
    ).data.data,
    onSuccess: async (_, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["company-foundation", "action-center"] }),
        queryClient.invalidateQueries({ queryKey: ["company-foundation", "overview"] }),
      ]);
      toast({
        title: variables.next === "assign" ? "รับผิดชอบรายการแล้ว" : variables.next === "acknowledge" ? "รับทราบแล้ว" : "ซ่อนรายการแล้ว",
        description: "สถานะล่าสุดบันทึกที่ Server และจะปรากฏใน Audit trail",
      });
    },
    onError: () => {
      toast({
        title: "ดำเนินการไม่สำเร็จ",
        description: "Server ไม่ได้เปลี่ยนสถานะรายการ กรุณาตรวจเครือข่ายหรือสิทธิ์แล้วลองใหม่",
        variant: "destructive",
      });
    },
  });

  const sources = useMemo(
    () => Array.from(new Set(listing.data?.items.map((item) => item.source_app) ?? [])).sort(),
    [listing.data?.items],
  );
  const items = useMemo(() => {
    const query = search.trim().toLocaleLowerCase("th");
    return (listing.data?.items ?? []).filter((item) => {
      if (filter === "unread" && !item.unread) return false;
      if (filter === "mine" && item.owner_id !== access.data?.user_id) return false;
      if (filter === "open" && item.status !== "open") return false;
      if (severity !== "all" && item.severity !== severity) return false;
      if (source !== "all" && item.source_app !== source) return false;
      if (query && !`${item.title} ${item.source_app} ${item.type}`.toLocaleLowerCase("th").includes(query)) return false;
      return true;
    });
  }, [access.data?.user_id, filter, listing.data?.items, search, severity, source]);

  if (listing.isLoading) {
    return (
      <div data-testid="company-actions-loading">
        <div className="mb-5 space-y-2"><Skeleton className="h-9 w-72" /><Skeleton className="h-5 w-96 max-w-full" /></div>
        <Skeleton className="mb-4 h-20 rounded-2xl" />
        <div className="space-y-3">{[0, 1, 2].map((item) => <Skeleton key={item} className="h-44 rounded-2xl" />)}</div>
      </div>
    );
  }

  if (listing.error || !listing.data) {
    return <CompanyStatePanel kind={companyRequestState(listing.error)} onRetry={() => void listing.refetch()} />;
  }

  const summary = {
    blocker: listing.data.items.filter((item) => item.severity === "blocker").length,
    unread: listing.data.unread,
    owned: listing.data.items.filter((item) => item.owner_id === access.data?.user_id).length,
  };

  return (
    <div data-testid="company-action-center">
      <PageHeader
        title="งานและการแจ้งเตือน"
        subtitle={`รวมงานจากทุกระบบตามลำดับที่ Server กำหนด · อัปเดต ${formatCompanyDateTime(listing.data.generated_at)}`}
      />

      <section className="mb-4 grid gap-3 sm:grid-cols-3" aria-label="สรุปรายการ">
        <button type="button" onClick={() => setFilter("all")} className="min-h-24 rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm"><span className="text-xs font-bold text-slate-500">ทั้งหมด</span><strong className="mt-2 block text-2xl text-slate-950">{listing.data.total}</strong></button>
        <button type="button" onClick={() => setFilter("unread")} className="min-h-24 rounded-2xl border border-blue-100 bg-white p-4 text-left shadow-sm"><span className="text-xs font-bold text-slate-500">ยังไม่อ่าน</span><strong className="mt-2 block text-2xl text-blue-700">{summary.unread}</strong></button>
        <button type="button" onClick={() => setSeverity("blocker")} className="min-h-24 rounded-2xl border border-red-100 bg-white p-4 text-left shadow-sm"><span className="text-xs font-bold text-slate-500">เร่งด่วน</span><strong className="mt-2 block text-2xl text-red-700">{summary.blocker}</strong></button>
      </section>

      <section className="mb-4 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm" aria-label="ตัวกรองรายการ">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">ค้นหางาน</span>
            <Search className="pointer-events-none absolute left-3.5 top-3.5 h-4 w-4 text-slate-400" />
            <Input className="pl-10" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="ค้นหางาน ระบบต้นทาง หรือประเภท" />
          </label>
          <div className="flex min-w-0 gap-2 overflow-x-auto pb-1 xl:pb-0" role="group" aria-label="สถานะรายการ">
            {([[
              "all", "ทั้งหมด",
            ], ["unread", "ยังไม่อ่าน"], ["mine", `ของฉัน ${summary.owned}`], ["open", "เปิดอยู่"]] as const).map(([value, label]) => (
              <Button key={value} variant={filter === value ? "default" : "outline"} onClick={() => setFilter(value)} aria-pressed={filter === value}>{label}</Button>
            ))}
          </div>
          <label className="flex min-h-11 items-center gap-2 rounded-xl border border-slate-200 px-3 text-sm font-semibold text-slate-600">
            <Filter className="h-4 w-4" /><span className="sr-only">ระดับความสำคัญ</span>
            <select className="bg-transparent outline-none" value={severity} onChange={(event) => setSeverity(event.target.value as typeof severity)}>
              <option value="all">ทุกระดับ</option><option value="blocker">เร่งด่วน</option><option value="error">ผิดพลาด</option><option value="warning">ควรตรวจ</option><option value="info">ข้อมูล</option>
            </select>
          </label>
          <label className="flex min-h-11 items-center rounded-xl border border-slate-200 px-3 text-sm font-semibold text-slate-600">
            <span className="sr-only">ระบบต้นทาง</span>
            <select className="max-w-44 bg-transparent outline-none" value={source} onChange={(event) => setSource(event.target.value)}>
              <option value="all">ทุกระบบ</option>{sources.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
        </div>
      </section>

      {!online ? <CompanyStatePanel compact kind="offline" title="Action Center อยู่ในโหมดออฟไลน์" description="ดูข้อมูลที่โหลดไว้ได้ แต่ปิดการเปลี่ยนสถานะทั้งหมดจนกว่าจะเชื่อมต่ออีกครั้ง" /> : null}

      <div className={cn("mt-3 space-y-3", !online && "opacity-80")}>
        {items.length === 0 ? (
          <CompanyStatePanel kind="empty" title="ไม่พบงานตามตัวกรอง" description="เปลี่ยนคำค้นหรือตัวกรองเพื่อดูรายการอื่น โดยระบบจะไม่สร้างงานจำลองขึ้นมาเอง" />
        ) : null}
        {items.map((item) => {
          const deepLink = safeDeepLink(item.deep_link);
          const canAssign = Boolean(access.data?.user_id) && item.available_actions.includes("assign") && item.status === "open";
          const canAcknowledge = item.available_actions.includes("acknowledge") && item.status === "open";
          const canDismiss = item.available_actions.includes("dismiss") && !["completed", "dismissed"].includes(item.status);
          return (
            <article key={item.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm md:p-5">
              <div className="flex flex-col justify-between gap-4 xl:flex-row xl:items-start">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge className={severityClass[item.severity]}>{severityLabel[item.severity]}</Badge>
                    <Badge variant="outline">{statusLabel[item.status]}</Badge>
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{item.source_app}</span>
                    {item.unread ? <span className="inline-flex items-center gap-1 text-xs font-bold text-blue-700"><span className="h-2 w-2 rounded-full bg-blue-600" />ยังไม่อ่าน</span> : null}
                  </div>
                  <h2 className="mt-3 text-base font-black text-slate-950 md:text-lg">{item.title}</h2>
                  <div className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-2 lg:grid-cols-4">
                    <p><span className="block font-semibold text-slate-400">ผู้รับผิดชอบ</span>{item.owner_id === access.data?.user_id ? "ฉัน" : item.owner_id ?? "ยังไม่มอบหมาย"}</p>
                    <p><span className="block font-semibold text-slate-400">ครบกำหนด</span>{formatCompanyDateTime(item.due_at)}</p>
                    <p><span className="block font-semibold text-slate-400">ขอบเขต</span>{item.branch_id ? "ระดับสาขา" : item.brand_id ? "ระดับแบรนด์" : "ระดับบริษัท"}</p>
                    <p><span className="block font-semibold text-slate-400">ผลกระทบ</span>{item.business_impact}</p>
                  </div>
                  <p className="mt-3 text-xs text-slate-400">สิทธิ์ที่ต้องใช้: {item.permission_required}</p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2 xl:max-w-xs xl:justify-end">
                  {canAssign ? <Button variant="outline" disabled={!online || action.isPending} onClick={() => action.mutate({ item, next: "assign" })}><UserRoundCheck className="h-4 w-4" />รับผิดชอบ</Button> : null}
                  {canAcknowledge ? <Button variant="outline" disabled={!online || action.isPending} onClick={() => action.mutate({ item, next: "acknowledge" })}><Check className="h-4 w-4" />รับทราบ</Button> : null}
                  {canDismiss ? <Button variant="outline" disabled={!online || action.isPending} onClick={() => action.mutate({ item, next: "dismiss" })}><X className="h-4 w-4" />ซ่อน</Button> : null}
                  {deepLink ? <Button asChild><Link to={deepLink}><ExternalLink className="h-4 w-4" />เปิดต้นทาง</Link></Button> : null}
                </div>
              </div>
            </article>
          );
        })}
      </div>

      <div className="mt-5 flex items-start gap-3 rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
        <Bell className="mt-0.5 h-5 w-5 shrink-0" />
        <p>รายการนี้แสดงเฉพาะ action ที่ backend อนุญาตจริง ส่วน Approve, Return และ Complete จะยังไม่สร้างปุ่มจนกว่า workflow และ approval gate จะพร้อม</p>
      </div>
    </div>
  );
}
