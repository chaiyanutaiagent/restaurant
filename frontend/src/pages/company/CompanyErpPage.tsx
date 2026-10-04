import { useQuery } from "@tanstack/react-query";
import {
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  Database,
  ExternalLink,
  FileCheck2,
  Filter,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
  WalletCards,
  Warehouse,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import CompanyStatePanel from "@/components/company/CompanyStatePanel";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { companyFoundationApi } from "@/lib/api";
import { companyRequestState, formatCompanyDateTime } from "@/lib/companyPresentation";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth.store";
import type {
  CompanyErpException,
  CompanyErpReadinessArea,
  CompanyErpReadinessState,
} from "@/types/companyFoundation";

const areaState: Record<CompanyErpReadinessState, { label: string; style: string }> = {
  ready: { label: "พร้อม", style: "border-emerald-200 bg-emerald-50 text-emerald-800" },
  attention: { label: "ต้องตรวจ", style: "border-amber-200 bg-amber-50 text-amber-900" },
  blocked: { label: "มีตัวกั้น", style: "border-red-200 bg-red-50 text-red-800" },
  hold: { label: "HOLD", style: "border-violet-200 bg-violet-50 text-violet-800" },
  permission_denied: { label: "ไม่มีสิทธิ์", style: "border-slate-200 bg-slate-100 text-slate-600" },
};

const severityStyle: Record<CompanyErpException["severity"], string> = {
  info: "border-blue-200 bg-blue-50 text-blue-800",
  warning: "border-amber-200 bg-amber-50 text-amber-900",
  error: "border-red-200 bg-red-50 text-red-800",
  blocker: "border-red-700 bg-red-700 text-white",
};

const severityLabel: Record<CompanyErpException["severity"], string> = {
  info: "ข้อมูล",
  warning: "ควรตรวจ",
  error: "ผิดพลาด",
  blocker: "ตัวกั้น",
};

const sourceLabel: Record<CompanyErpException["source"], string> = {
  purchase: "จัดซื้อ",
  transfer: "โอนสินค้า",
  stock_count: "ตรวจนับสต็อก",
  payable: "เจ้าหนี้",
  tax: "ภาษี",
};

const areaIcon: Record<CompanyErpReadinessArea["key"], typeof Database> = {
  purchasing: WalletCards,
  inventory: Warehouse,
  finance_tax: FileCheck2,
  reporting: Database,
};

function safePath(value: string | null): string | null {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : null;
}

function ageLabel(hours: number): string {
  if (hours < 1) return "ไม่ถึง 1 ชม.";
  if (hours < 24) return `${hours} ชม.`;
  return `${Math.floor(hours / 24)} วัน ${hours % 24} ชม.`;
}

export default function CompanyErpPage(): JSX.Element {
  const [severity, setSeverity] = useState<"all" | CompanyErpException["severity"]>("all");
  const [source, setSource] = useState<"all" | CompanyErpException["source"]>("all");
  const [branch, setBranch] = useState("all");
  const [online, setOnline] = useState(() => navigator.onLine);
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

  const readiness = useQuery({
    queryKey: ["company-foundation", "erp-readiness", branchId, stationKey],
    queryFn: async () => (await companyFoundationApi.erpReadiness()).data.data,
    retry: false,
  });

  const branches = useMemo(
    () => Array.from(new Map(
      (readiness.data?.exceptions ?? [])
        .filter((item) => item.branch_id)
        .map((item) => [item.branch_id as string, item.branch_name ?? item.branch_id as string]),
    ).entries()).sort((left, right) => left[1].localeCompare(right[1], "th")),
    [readiness.data?.exceptions],
  );
  const exceptions = useMemo(
    () => (readiness.data?.exceptions ?? []).filter((item) => (
      (severity === "all" || item.severity === severity)
      && (source === "all" || item.source === source)
      && (branch === "all" || item.branch_id === branch)
    )),
    [branch, readiness.data?.exceptions, severity, source],
  );

  if (readiness.isLoading) {
    return (
      <div data-testid="company-erp-loading">
        <div className="mb-5 space-y-2"><Skeleton className="h-9 w-64" /><Skeleton className="h-5 w-[32rem] max-w-full" /></div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((item) => <Skeleton key={item} className="h-44 rounded-2xl" />)}</div>
        <Skeleton className="mt-5 h-96 rounded-2xl" />
      </div>
    );
  }

  if (readiness.error || !readiness.data) {
    return <CompanyStatePanel kind={companyRequestState(readiness.error)} onRetry={() => void readiness.refetch()} />;
  }

  const data = readiness.data;
  const generatedAt = new Date(data.generated_at).getTime();
  const stale = Number.isFinite(generatedAt) && Date.now() - generatedAt > data.stale_after_seconds * 1000;
  const periodLabel = data.finance ? `${data.finance.period_month}/${data.finance.period_year + 543}` : "ไม่มีสิทธิ์";

  return (
    <div data-testid="company-erp-readiness">
      <PageHeader
        title="Shared ERP"
        subtitle={`${data.context.company.name} · ${data.context.branch?.name ?? "ทุกสาขาที่มีสิทธิ์"} · ข้อมูลจาก Server ${formatCompanyDateTime(data.generated_at)}`}
        actions={(
          <Button variant="outline" onClick={() => void readiness.refetch()} disabled={readiness.isFetching}>
            <RefreshCw className={cn("mr-2 h-4 w-4", readiness.isFetching && "animate-spin")} />รีเฟรช
          </Button>
        )}
      />

      {!online || stale ? (
        <div className={cn(
          "mb-4 flex items-start gap-3 rounded-2xl border p-4 text-sm font-semibold",
          !online ? "border-slate-300 bg-slate-100 text-slate-800" : "border-orange-200 bg-orange-50 text-orange-900",
        )} role="alert" data-testid={!online ? "erp-offline-state" : "erp-stale-state"}>
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <span>{!online ? "อุปกรณ์ออฟไลน์ กำลังแสดง snapshot ล่าสุด ห้ามอนุมัติหรือสรุปยอดจากข้อมูลนี้" : "ข้อมูลเกินช่วง freshness ที่กำหนด กรุณารีเฟรชก่อนตัดสินใจ"}</span>
        </div>
      ) : null}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="สถานะ ERP">
        {data.areas.map((area) => {
          const Icon = areaIcon[area.key];
          const link = safePath(area.deep_link);
          return (
            <article key={area.key} className="flex min-h-44 flex-col rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <span className="rounded-xl bg-blue-50 p-2.5 text-blue-700"><Icon className="h-5 w-5" /></span>
                <Badge className={areaState[area.state].style}>{areaState[area.state].label}</Badge>
              </div>
              <h2 className="mt-3 font-black text-slate-950">{area.title}</h2>
              <p className="mt-1 text-sm leading-6 text-slate-600">{area.message}</p>
              <div className="mt-auto flex items-end justify-between gap-3 pt-3">
                <div><span className="text-2xl font-black">{area.open_items}</span><span className="ml-1 text-xs text-slate-500">รายการเปิด</span></div>
                {link ? <Link to={link} className="flex min-h-10 items-center gap-1 text-sm font-bold text-blue-700">เปิดงาน<ArrowRight className="h-4 w-4" /></Link> : null}
              </div>
            </article>
          );
        })}
      </section>

      <section className="mt-5 grid gap-4 xl:grid-cols-[1.7fr_1fr]">
        <div className="min-w-0 rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 p-4">
            <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-center">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.16em] text-blue-700">Exception queue</p>
                <h2 className="mt-1 text-lg font-black">งานที่ต้องตรวจจากจัดซื้อ คลัง บัญชี และภาษี</h2>
              </div>
              <div className="flex flex-wrap items-center gap-2" aria-label="ตัวกรองคิวงาน">
                <Filter className="h-4 w-4 text-slate-400" />
                <select value={severity} onChange={(event) => setSeverity(event.target.value as typeof severity)} className="min-h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold">
                  <option value="all">ทุกระดับ</option><option value="blocker">ตัวกั้น</option><option value="error">ผิดพลาด</option><option value="warning">ควรตรวจ</option><option value="info">ข้อมูล</option>
                </select>
                <select value={source} onChange={(event) => setSource(event.target.value as typeof source)} className="min-h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold">
                  <option value="all">ทุกระบบ</option>{Object.entries(sourceLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
                <select value={branch} onChange={(event) => setBranch(event.target.value)} className="min-h-10 max-w-48 rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold">
                  <option value="all">ทุกสาขาที่มีสิทธิ์</option>{branches.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>
            </div>
          </div>
          {exceptions.length === 0 ? (
            <div className="p-4"><CompanyStatePanel kind="empty" compact title="ไม่พบรายการตามตัวกรอง" description="สถานะนี้ไม่ใช่การยืนยันว่าปิดงวดหรือพร้อม Production" /></div>
          ) : (
            <div className="divide-y divide-slate-100">
              {exceptions.map((item) => (
                <article key={item.id} className="p-4 hover:bg-slate-50/70">
                  <div className="flex flex-col justify-between gap-3 md:flex-row md:items-start">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2"><Badge className={severityStyle[item.severity]}>{severityLabel[item.severity]}</Badge><Badge variant="outline">{sourceLabel[item.source]}</Badge><strong className="break-words">{item.title}</strong></div>
                      <p className="mt-2 text-sm text-slate-600">เลขอ้างอิง <strong>{item.reference}</strong> · เจ้าของ {item.owner_id ?? "ยังไม่กำหนด"}</p>
                      <p className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500"><span><Clock3 className="mr-1 inline h-3.5 w-3.5" />อายุ {ageLabel(item.age_hours)}</span><span>ครบกำหนด {formatCompanyDateTime(item.due_at)}</span><span>หลักฐาน {item.evidence_reference}</span></p>
                    </div>
                    <Button asChild variant="outline" size="sm"><Link to={item.deep_link}>เปิดรายการ<ExternalLink className="ml-2 h-4 w-4" /></Link></Button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-4">
          <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" aria-labelledby="finance-readiness-title">
            <div className="flex items-start justify-between gap-3"><div><p className="text-xs font-black uppercase tracking-[0.16em] text-blue-700">Close readiness</p><h2 id="finance-readiness-title" className="mt-1 text-lg font-black">งวดบัญชีและภาษี {periodLabel}</h2></div>{data.finance?.ready_to_close ? <CheckCircle2 className="h-6 w-6 text-emerald-600" /> : <AlertOctagon className="h-6 w-6 text-amber-600" />}</div>
            {data.finance ? (
              <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
                <div className="rounded-xl bg-slate-50 p-3"><span className="block text-xs text-slate-500">สถานะงวด</span><strong>{data.finance.period_status}</strong></div>
                <div className="rounded-xl bg-slate-50 p-3"><span className="block text-xs text-slate-500">ตั้งค่าภาษี</span><strong>{data.finance.tax_configured ? "ครบเบื้องต้น" : "ยังไม่ครบ"}</strong></div>
                <div className="rounded-xl bg-red-50 p-3 text-red-800"><span className="block text-xs">ตัวกั้น</span><strong>{data.finance.open_blockers}</strong></div>
                <div className="rounded-xl bg-amber-50 p-3 text-amber-900"><span className="block text-xs">รอกระทบยอด</span><strong>{data.finance.pending_reconciliation}</strong></div>
                <div className="col-span-2 rounded-xl border border-violet-200 bg-violet-50 p-3 text-violet-900"><span className="block text-xs">Accountant sign-off</span><strong>{data.finance.accountant_signoff === "recorded" ? "บันทึกในงวดแล้ว" : "HOLD — รอผู้รับผิดชอบยืนยัน"}</strong></div>
              </div>
            ) : <CompanyStatePanel kind="permission_denied" compact />}
            {safePath(data.finance?.deep_link ?? null) ? <Button asChild className="mt-3 w-full" variant="outline"><Link to={data.finance!.deep_link!}>เปิดศูนย์ภาษี<ArrowRight className="ml-2 h-4 w-4" /></Link></Button> : null}
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" aria-labelledby="controls-title">
            <div className="flex items-center gap-2"><ShieldCheck className="h-5 w-5 text-blue-700" /><h2 id="controls-title" className="font-black">Control และ Release HOLD</h2></div>
            <div className="mt-3 space-y-2">
              {data.controls.map((control) => (
                <div key={control.key} className={cn("rounded-xl border p-3 text-sm", control.state === "enforced" ? "border-emerald-200 bg-emerald-50" : "border-violet-200 bg-violet-50")}>
                  <div className="flex items-start gap-2">{control.state === "enforced" ? <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" /> : <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0 text-violet-700" />}<div><strong>{control.label}</strong><p className="mt-0.5 text-xs leading-5 text-slate-600">{control.detail}</p></div></div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </section>

      <p className="mt-4 text-xs text-slate-500">แหล่งข้อมูล: Operational Database · อัปเดตต้นทาง {formatCompanyDateTime(data.source_updated_at)} · หน้านี้เป็น read-only orchestration และไม่เปิด Production flags</p>
    </div>
  );
}
