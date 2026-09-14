import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CircleDollarSign,
  Clock3,
  Factory,
  ReceiptText,
  RefreshCw,
  RotateCcw,
  ShoppingBag,
  Store,
  UtensilsCrossed,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { membershipApi } from "@/lib/api";
import type {
  ReportingModuleKey,
  SharedSalesMetrics,
  SharedSalesReport,
} from "@/types/sharedReporting";

const moduleDefinitions: Array<{
  key: ReportingModuleKey;
  label: string;
  description: string;
  icon: typeof Store;
  color: string;
}> = [
  { key: "restaurant_pos", label: "Restaurant POS", description: "ร้านอาหารและบริการที่โต๊ะ", icon: UtensilsCrossed, color: "bg-orange-500" },
  { key: "takeaway_pos", label: "Takeaway POS", description: "หน้าร้านรับสินค้าจากส่วนกลาง", icon: ShoppingBag, color: "bg-emerald-600" },
  { key: "retail_pos", label: "Retail POS", description: "ขายปลีกสินค้าและบริการทั่วไป", icon: Store, color: "bg-blue-600" },
];

const zeroMetrics: SharedSalesMetrics = {
  order_count: 0,
  void_count: 0,
  refund_count: 0,
  gross_sales: 0,
  discount_amount: 0,
  tax_amount: 0,
  refund_amount: 0,
  net_sales: 0,
};

function dateInputValue(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function money(value: number | string): string {
  return new Intl.NumberFormat("th-TH", {
    style: "currency",
    currency: "THB",
    maximumFractionDigits: 2,
  }).format(Number(value));
}

function count(value: number): string {
  return new Intl.NumberFormat("th-TH").format(value);
}

function statusLabel(status: string): string {
  return ({
    completed: "สำเร็จ",
    paid: "ชำระแล้ว",
    partially_refunded: "คืนบางส่วน",
    refunded: "คืนเงินแล้ว",
    voided: "ยกเลิก",
  } as Record<string, string>)[status] ?? status;
}

function freshnessMessage(report: SharedSalesReport): { title: string; detail: string; className: string } {
  const state = report.freshness;
  if (state.status === "current") {
    return {
      title: "ข้อมูล Shadow ล่าสุด",
      detail: `อัปเดตล่าสุด ${state.last_projected_at ? new Date(state.last_projected_at).toLocaleString("th-TH") : "ยังไม่มีรายการ"} · ยังไม่ใช้แทนรายงานต้นทาง`,
      className: "border-emerald-200 bg-emerald-50 text-emerald-800",
    };
  }
  if (state.status === "degraded") {
    return {
      title: "ข้อมูลบางแหล่งมีปัญหา",
      detail: `กรุณาเทียบรายงานต้นทางก่อนใช้งาน${state.failed_sources.length ? ` · ${state.failed_sources.join(", ")}` : ""}`,
      className: "border-red-200 bg-red-50 text-red-800",
    };
  }
  if (state.status === "stale") {
    return {
      title: "ข้อมูลอาจไม่ล่าสุด",
      detail: "ตัวรวบรวมข้อมูลไม่ได้ตอบกลับตามเวลาที่กำหนด กรุณาเทียบรายงานต้นทาง",
      className: "border-amber-200 bg-amber-50 text-amber-800",
    };
  }
  return {
    title: state.status === "disabled" ? "รายงานรวมยังไม่เปิดใช้งาน" : "ยังไม่มีข้อมูลรายงานรวม",
    detail: "หน้านี้อยู่ในโหมด Shadow และไม่กระทบการขายของ Restaurant, Takeaway หรือ Retail",
    className: "border-blue-200 bg-blue-50 text-blue-800",
  };
}

export default function CompanyReportsPage(): JSX.Element {
  const today = useMemo(() => new Date(), []);
  const firstDay = useMemo(() => {
    const value = new Date(today);
    value.setDate(value.getDate() - 6);
    return value;
  }, [today]);
  const [dateFrom, setDateFrom] = useState(dateInputValue(firstDay));
  const [dateTo, setDateTo] = useState(dateInputValue(today));
  const [moduleKey, setModuleKey] = useState<ReportingModuleKey | "all">("all");

  const reportQuery = useQuery({
    queryKey: ["membership", "shared-sales-report", dateFrom, dateTo, moduleKey],
    queryFn: async () => (await membershipApi.sharedSalesReport({
      date_from: dateFrom,
      date_to: dateTo,
      ...(moduleKey === "all" ? {} : { module_key: moduleKey }),
    })).data.data,
    enabled: Boolean(dateFrom && dateTo && dateFrom <= dateTo),
    refetchInterval: 60_000,
  });

  const report = reportQuery.data;
  const freshness = report ? freshnessMessage(report) : null;
  const moduleRows = new Map(report?.modules.map((row) => [row.module_key, row]) ?? []);

  return (
    <div className="mx-auto max-w-7xl space-y-6" data-testid="company-shared-report">
      <header className="rounded-2xl bg-slate-950 p-6 text-white shadow-lg">
        <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.24em] text-blue-300">Company Admin · Shadow report</p>
            <h1 className="mt-2 text-2xl font-black md:text-3xl">รายงานยอดขายรวมทุกระบบ</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">รวมยอดระดับ Company แต่ยังคงแยกโมดูล แบรนด์ และสาขา ข้อมูลนี้ใช้ตรวจเทียบระหว่างช่วงปรับระบบเท่านั้น</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" className="border-slate-600 bg-slate-900 text-white hover:bg-slate-800">
              <Link to="/company-kitchen"><Factory className="h-4 w-4" /> รายงานครัวกลาง</Link>
            </Button>
            <Button variant="outline" className="border-slate-600 bg-slate-900 text-white hover:bg-slate-800" onClick={() => void reportQuery.refetch()} disabled={reportQuery.isFetching}>
              <RefreshCw className={`h-4 w-4 ${reportQuery.isFetching ? "animate-spin" : ""}`} /> โหลดล่าสุด
            </Button>
          </div>
        </div>
      </header>

      <section className="grid gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm md:grid-cols-3">
        <label className="text-sm font-bold text-slate-700">ตั้งแต่
          <input aria-label="ตั้งแต่" type="date" className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 font-normal" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
        </label>
        <label className="text-sm font-bold text-slate-700">ถึง
          <input aria-label="ถึง" type="date" className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 font-normal" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
        </label>
        <label className="text-sm font-bold text-slate-700">ระบบ
          <select aria-label="ระบบ" className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 font-normal" value={moduleKey} onChange={(event) => setModuleKey(event.target.value as ReportingModuleKey | "all")}>
            <option value="all">ทุกระบบ</option>
            {moduleDefinitions.map((definition) => <option key={definition.key} value={definition.key}>{definition.label}</option>)}
          </select>
        </label>
      </section>

      {dateFrom > dateTo ? <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">วันที่เริ่มต้องไม่เกินวันที่สิ้นสุด</div> : null}
      {reportQuery.isError ? <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">โหลดรายงานไม่สำเร็จ การขายในแต่ละระบบยังทำงานตามปกติ</div> : null}
      {reportQuery.isLoading ? <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-slate-500">กำลังรวบรวมข้อมูล...</div> : null}

      {report && freshness ? (
        <>
          <section data-testid={`report-freshness-${report.freshness.status}`} className={`flex gap-3 rounded-xl border p-4 ${freshness.className}`}>
            {report.freshness.status === "degraded" || report.freshness.status === "stale" ? <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" /> : <Clock3 className="mt-0.5 h-5 w-5 shrink-0" />}
            <div><p className="font-black">{freshness.title}</p><p className="mt-1 text-sm">{freshness.detail}</p></div>
          </section>

          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              { label: "ยอดสุทธิ", value: money(report.totals.net_sales), icon: CircleDollarSign },
              { label: "ออเดอร์", value: count(report.totals.order_count), icon: ReceiptText },
              { label: "คืนเงิน", value: money(report.totals.refund_amount), icon: RotateCcw },
              { label: "รายการยกเลิก", value: count(report.totals.void_count), icon: AlertTriangle },
            ].map(({ label, value, icon: Icon }) => (
              <article key={label} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <Icon className="h-5 w-5 text-blue-600" /><p className="mt-4 text-sm font-semibold text-slate-500">{label}</p><p className="mt-1 text-2xl font-black text-slate-950">{value}</p>
              </article>
            ))}
          </section>

          <section>
            <div className="mb-3"><p className="text-xs font-bold uppercase tracking-[0.2em] text-blue-600">Module breakdown</p><h2 className="mt-1 text-xl font-black text-slate-950">แยกตามระบบ POS</h2></div>
            <div className="grid gap-4 lg:grid-cols-3">
              {moduleDefinitions.filter((definition) => moduleKey === "all" || definition.key === moduleKey).map((definition) => {
                const Icon = definition.icon;
                const metrics = moduleRows.get(definition.key) ?? zeroMetrics;
                return (
                  <article key={definition.key} data-testid={`report-module-${definition.key}`} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                    <div className="flex items-start justify-between"><div className={`flex h-11 w-11 items-center justify-center rounded-lg text-white ${definition.color}`}><Icon className="h-5 w-5" /></div><span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-bold text-slate-600">{count(metrics.order_count)} ออเดอร์</span></div>
                    <h3 className="mt-4 text-lg font-black text-slate-950">{definition.label}</h3><p className="text-sm text-slate-500">{definition.description}</p>
                    <p className="mt-5 text-sm font-semibold text-slate-500">ยอดสุทธิ</p><p className="text-2xl font-black text-slate-950">{money(metrics.net_sales)}</p>
                    <div className="mt-4 grid grid-cols-2 gap-2 text-xs text-slate-600"><span>ยอดก่อนคืน {money(metrics.gross_sales)}</span><span>คืนเงิน {money(metrics.refund_amount)}</span></div>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-200 p-5"><div className="flex items-center gap-3"><Building2 className="h-5 w-5 text-blue-600" /><div><h2 className="font-black text-slate-950">ยอดตามแบรนด์และสาขา</h2><p className="text-sm text-slate-500">Company รวม แต่ไม่ปะปนขอบเขต Workspace</p></div></div></div>
            <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr><th className="px-5 py-3">ระบบ</th><th className="px-5 py-3">แบรนด์ / สาขา</th><th className="px-5 py-3 text-right">ออเดอร์</th><th className="px-5 py-3 text-right">คืนเงิน</th><th className="px-5 py-3 text-right">ยอดสุทธิ</th></tr></thead><tbody className="divide-y divide-slate-100">
              {report.workspaces.length ? report.workspaces.map((row) => <tr key={`${row.module_key}-${row.brand_id}-${row.branch_id}`}><td className="px-5 py-4 font-bold text-slate-700">{moduleDefinitions.find((item) => item.key === row.module_key)?.label ?? row.module_key}</td><td className="px-5 py-4"><p className="font-bold text-slate-950">{row.brand_name}</p><p className="text-slate-500">{row.branch_name}</p></td><td className="px-5 py-4 text-right">{count(row.order_count)}</td><td className="px-5 py-4 text-right">{money(row.refund_amount)}</td><td className="px-5 py-4 text-right font-black">{money(row.net_sales)}</td></tr>) : <tr><td colSpan={5} className="px-5 py-10 text-center text-slate-500">ยังไม่มีข้อมูลในช่วงวันที่เลือก</td></tr>}
            </tbody></table></div>
          </section>

          <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-200 p-5"><h2 className="font-black text-slate-950">เอกสารล่าสุด</h2><p className="text-sm text-slate-500">เปิดกลับไประบบต้นทางตามโมดูลของรายการ</p></div>
            <div className="divide-y divide-slate-100">{report.recent_documents.length ? report.recent_documents.map((document) => <div key={`${document.module_key}-${document.source_document_id}`} className="flex flex-col justify-between gap-3 p-5 md:flex-row md:items-center"><div><p className="font-black text-slate-950">{document.document_number ?? document.source_document_id}</p><p className="text-sm text-slate-500">{document.brand_name} · {document.branch_name} · {statusLabel(document.source_status)}</p></div><div className="flex items-center gap-4"><p className="font-black text-slate-950">{money(document.net_sales)}</p><Link className="inline-flex items-center gap-1 text-sm font-bold text-blue-700" to={document.entry_route}>เปิดระบบ <ArrowRight className="h-4 w-4" /></Link></div></div>) : <p className="p-8 text-center text-sm text-slate-500">ยังไม่มีเอกสารในช่วงวันที่เลือก</p>}</div>
          </section>
        </>
      ) : null}
    </div>
  );
}
