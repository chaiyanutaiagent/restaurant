import { useQuery } from "@tanstack/react-query";
import { Download, FlaskConical, TrendingDown } from "lucide-react";
import { useMemo, useState } from "react";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/stores/auth.store";
import { authApi } from "@/lib/api";
import { formatThaiCurrency } from "@/lib/cartUtils";

type UsageItem = {
  ingredient_id: string;
  ingredient_name: string;
  ingredient_sku: string;
  theoretical_qty: number;
  unit: string;
  latest_unit_cost: number;
  total_cost: number;
};

type Report = {
  branch_id: string;
  date_from: string;
  date_to: string;
  items: UsageItem[];
  grand_total_cost: number;
};

function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

function sevenDaysAgoStr(): string {
  const d = new Date();
  d.setDate(d.getDate() - 6);
  return d.toISOString().slice(0, 10);
}

function downloadCsv(report: Report): void {
  const header = "วัตถุดิบ,SKU,ปริมาณ (ทฤษฎี),หน่วย,ราคาต่อหน่วย,ต้นทุนรวม";
  const rows = report.items.map((i) =>
    [i.ingredient_name, i.ingredient_sku, i.theoretical_qty, i.unit, i.latest_unit_cost, i.total_cost].join(",")
  );
  rows.push(`,,,,รวมทั้งหมด,${report.grand_total_cost}`);
  const csv = "﻿" + [header, ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `ingredient-usage-${report.date_from}-${report.date_to}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function IngredientReportPage(): JSX.Element {
  const branchId = useAuthStore((s) => s.branchId);
  const [dateFrom, setDateFrom] = useState(sevenDaysAgoStr());
  const [dateTo, setDateTo] = useState(todayStr());
  const [sortBy, setSortBy] = useState<"cost" | "qty" | "name">("cost");
  const [search, setSearch] = useState("");

  const reportQuery = useQuery({
    queryKey: ["ingredient-report", branchId, dateFrom, dateTo],
    queryFn: async () => {
      const res = await authApi.get(
        `/restaurant/reports/ingredients?branch_id=${branchId}&date_from=${dateFrom}&date_to=${dateTo}`
      );
      return res.data.data as Report;
    },
    enabled: Boolean(branchId) && Boolean(dateFrom) && Boolean(dateTo),
  });

  const report = reportQuery.data;

  const sortedItems = useMemo(() => {
    if (!report) return [];
    let items = [...report.items];
    if (search.trim()) {
      const q = search.toLowerCase();
      items = items.filter((i) => i.ingredient_name.toLowerCase().includes(q) || i.ingredient_sku.toLowerCase().includes(q));
    }
    if (sortBy === "cost") return items.sort((a, b) => b.total_cost - a.total_cost);
    if (sortBy === "qty") return items.sort((a, b) => b.theoretical_qty - a.theoretical_qty);
    return items.sort((a, b) => a.ingredient_name.localeCompare(b.ingredient_name, "th"));
  }, [report, sortBy, search]);

  // คำนวณ top 3 สำหรับ chart bar
  const maxCost = sortedItems[0]?.total_cost ?? 1;

  const costShare = useMemo(() => {
    if (!report || report.grand_total_cost === 0) return [];
    return sortedItems.slice(0, 5).map((i) => ({
      name: i.ingredient_name,
      pct: ((i.total_cost / report.grand_total_cost) * 100).toFixed(1),
      cost: i.total_cost,
    }));
  }, [sortedItems, report]);

  return (
    <div>
      <PageHeader
        title="รายงานการใช้วัตถุดิบ"
        subtitle="ประมาณการจากยอดขาย × สูตรอาหาร"
        actions={
          report && report.items.length > 0 ? (
            <Button variant="outline" onClick={() => downloadCsv(report)}>
              <Download className="mr-2 h-4 w-4" />
              Export CSV
            </Button>
          ) : undefined
        }
      />

      <div className="space-y-6 p-6">
        {/* Filter Bar */}
        <div className="flex flex-wrap items-end gap-4 rounded-2xl border border-slate-200 bg-white p-4">
          <div>
            <label className="text-xs text-slate-500">จากวันที่</label>
            <input
              type="date"
              className="mt-1 block h-10 rounded-xl border border-slate-300 px-3 text-sm"
              value={dateFrom}
              max={dateTo}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-slate-500">ถึงวันที่</label>
            <input
              type="date"
              className="mt-1 block h-10 rounded-xl border border-slate-300 px-3 text-sm"
              value={dateTo}
              min={dateFrom}
              max={todayStr()}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </div>
          <div className="flex gap-2">
            {(["7d", "30d", "today"] as const).map((preset) => {
              const label = preset === "today" ? "วันนี้" : preset === "7d" ? "7 วัน" : "30 วัน";
              return (
                <button
                  key={preset}
                  type="button"
                  onClick={() => {
                    const to = todayStr();
                    const d = new Date();
                    if (preset === "today") { setDateFrom(to); setDateTo(to); return; }
                    d.setDate(d.getDate() - (preset === "7d" ? 6 : 29));
                    setDateFrom(d.toISOString().slice(0, 10));
                    setDateTo(to);
                  }}
                  className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs hover:bg-slate-100"
                >
                  {label}
                </button>
              );
            })}
          </div>
          <div className="ml-auto">
            <input
              type="text"
              placeholder="ค้นหาวัตถุดิบ..."
              className="h-10 rounded-xl border border-slate-300 px-3 text-sm w-48"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        {reportQuery.isLoading && (
          <div className="py-12 text-center text-slate-500">กำลังคำนวณ...</div>
        )}

        {report && report.items.length === 0 && (
          <div className="rounded-2xl border border-dashed border-slate-300 py-16 text-center text-slate-400">
            <FlaskConical className="mx-auto mb-3 h-10 w-10" />
            <p className="font-medium">ไม่มีข้อมูล</p>
            <p className="mt-1 text-sm">ยังไม่มียอดขายในช่วงเวลานี้ หรือยังไม่ได้ตั้งค่าสูตรอาหาร</p>
          </div>
        )}

        {report && report.items.length > 0 && (
          <>
            {/* Summary Cards */}
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <SummaryCard
                label="ต้นทุนวัตถุดิบรวม"
                value={formatThaiCurrency(report.grand_total_cost)}
                sub={`${dateFrom} – ${dateTo}`}
                color="orange"
              />
              <SummaryCard
                label="จำนวนวัตถุดิบ"
                value={`${report.items.length} รายการ`}
                color="blue"
              />
              <SummaryCard
                label="วัตถุดิบแพงสุด"
                value={report.items[0]?.ingredient_name ?? "-"}
                sub={formatThaiCurrency(report.items[0]?.total_cost ?? 0)}
                color="red"
              />
              <SummaryCard
                label="ต้นทุนเฉลี่ย/รายการ"
                value={formatThaiCurrency(report.grand_total_cost / report.items.length)}
                color="emerald"
              />
            </div>

            {/* Top 5 Bar Chart */}
            {costShare.length > 0 && (
              <div className="rounded-2xl border border-slate-200 bg-white p-5">
                <h3 className="mb-4 font-semibold text-slate-800 flex items-center gap-2">
                  <TrendingDown className="h-5 w-5 text-orange-500" />
                  Top 5 วัตถุดิบที่ใช้ต้นทุนสูงสุด
                </h3>
                <div className="space-y-3">
                  {costShare.map((item, i) => (
                    <div key={item.name}>
                      <div className="flex items-center justify-between text-sm mb-1">
                        <span className="font-medium text-slate-800">{i + 1}. {item.name}</span>
                        <span className="text-slate-500">{formatThaiCurrency(item.cost)} ({item.pct}%)</span>
                      </div>
                      <div className="h-3 rounded-full bg-slate-100 overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${["bg-orange-500", "bg-orange-400", "bg-orange-300", "bg-amber-400", "bg-amber-300"][i]}`}
                          style={{ width: `${item.pct}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Sort controls */}
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-500">เรียงตาม:</span>
              {(["cost", "qty", "name"] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setSortBy(s)}
                  className={`rounded-full px-3 py-1 text-xs ${sortBy === s ? "bg-orange-500 text-white" : "border border-slate-200 bg-white text-slate-600"}`}
                >
                  {s === "cost" ? "ต้นทุนสูงสุด" : s === "qty" ? "ปริมาณมากสุด" : "ชื่อ ก-ฮ"}
                </button>
              ))}
              <span className="ml-auto text-xs text-slate-400">{sortedItems.length} รายการ</span>
            </div>

            {/* Ingredient Table */}
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
              <table className="w-full text-sm">
                <thead className="border-b border-slate-200 bg-slate-50">
                  <tr>
                    <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">วัตถุดิบ</th>
                    <th className="px-5 py-3 text-right text-xs font-semibold uppercase tracking-wider text-slate-500">ปริมาณ (ทฤษฎี)</th>
                    <th className="px-5 py-3 text-right text-xs font-semibold uppercase tracking-wider text-slate-500">ราคา/หน่วย</th>
                    <th className="px-5 py-3 text-right text-xs font-semibold uppercase tracking-wider text-slate-500">ต้นทุนรวม</th>
                    <th className="px-5 py-3 text-right text-xs font-semibold uppercase tracking-wider text-slate-500">% ของทั้งหมด</th>
                    <th className="w-32 px-5 py-3" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {sortedItems.map((item) => {
                    const costPct = report.grand_total_cost > 0
                      ? (item.total_cost / report.grand_total_cost) * 100
                      : 0;
                    const barWidth = (item.total_cost / maxCost) * 100;
                    return (
                      <tr key={item.ingredient_id} className="hover:bg-orange-50/40">
                        <td className="px-5 py-4">
                          <p className="font-medium text-slate-900">{item.ingredient_name}</p>
                          <p className="text-xs text-slate-400">{item.ingredient_sku}</p>
                        </td>
                        <td className="px-5 py-4 text-right font-medium text-slate-700">
                          {Number(item.theoretical_qty).toFixed(2)}
                          <span className="ml-1 text-xs text-slate-400">{item.unit}</span>
                        </td>
                        <td className="px-5 py-4 text-right text-slate-600">
                          {formatThaiCurrency(item.latest_unit_cost)}
                          <span className="text-xs text-slate-400">/{item.unit}</span>
                        </td>
                        <td className="px-5 py-4 text-right font-bold text-slate-900">
                          {formatThaiCurrency(item.total_cost)}
                        </td>
                        <td className="px-5 py-4 text-right">
                          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${costPct >= 20 ? "bg-red-100 text-red-700" : costPct >= 10 ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-600"}`}>
                            {costPct.toFixed(1)}%
                          </span>
                        </td>
                        <td className="px-5 py-4">
                          <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                            <div
                              className="h-full rounded-full bg-orange-400 transition-all"
                              style={{ width: `${barWidth}%` }}
                            />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot className="border-t-2 border-slate-200 bg-orange-50">
                  <tr>
                    <td className="px-5 py-4 font-bold text-slate-800">รวมทั้งหมด</td>
                    <td colSpan={2} />
                    <td className="px-5 py-4 text-right text-xl font-black text-orange-700">
                      {formatThaiCurrency(report.grand_total_cost)}
                    </td>
                    <td colSpan={2} />
                  </tr>
                </tfoot>
              </table>
            </div>

            {/* Note */}
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              <strong>หมายเหตุ:</strong> ตัวเลขนี้คือ <em>ประมาณการทฤษฎี</em> คำนวณจากยอดขาย × สูตรอาหาร
              ควรเทียบกับการนับสต็อกจริง (Stock Count) เพื่อหา variance
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function SummaryCard({
  label, value, sub, color,
}: {
  label: string; value: string; sub?: string;
  color: "orange" | "blue" | "red" | "emerald";
}): JSX.Element {
  const colors = {
    orange: "border-orange-200 bg-orange-50",
    blue: "border-blue-200 bg-blue-50",
    red: "border-red-200 bg-red-50",
    emerald: "border-emerald-200 bg-emerald-50",
  };
  const textColors = {
    orange: "text-orange-700",
    blue: "text-blue-700",
    red: "text-red-700",
    emerald: "text-emerald-700",
  };
  return (
    <div className={`rounded-2xl border p-4 ${colors[color]}`}>
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`mt-1 text-xl font-bold ${textColors[color]}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-slate-400">{sub}</p>}
    </div>
  );
}
