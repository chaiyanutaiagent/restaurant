import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, BarChart2, Boxes, ClipboardList, Coins, Factory, Loader2, PackageCheck, Store, Truck } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { wapApi } from "@/lib/wapApi";

function todayString(): string {
  return new Date().toISOString().slice(0, 10);
}

function firstDayOfMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
}

function money(value: number): string {
  return value.toLocaleString("th-TH", { style: "currency", currency: "THB" });
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    submitted: "ส่งแล้ว",
    reserved_credit: "กันเครดิตแล้ว",
    approved: "อนุมัติแล้ว",
    packed: "แพ็กแล้ว",
    shipped: "จัดส่งแล้ว",
    received: "รับแล้ว",
    cancelled: "ยกเลิก",
  };
  return labels[status] ?? status;
}

function recipeTypeLabel(type: string): string {
  return type === "production_recipe" ? "สูตรผลิต" : "สูตรขาย";
}

export default function RestaurantCentralReportsPage(): JSX.Element {
  const { brandSlug } = useParams<{ brandSlug?: string }>();
  const [dateFrom, setDateFrom] = useState(firstDayOfMonth());
  const [dateTo, setDateTo] = useState(todayString());
  const centralBase = brandSlug ? `/central/${brandSlug}` : "/restaurant";

  const reportQuery = useQuery({
    queryKey: ["brand-operations-report", brandSlug, dateFrom, dateTo],
    queryFn: async () => {
      if (!brandSlug) throw new Error("ไม่พบแบรนด์");
      return (await wapApi.brandOperationsReport(brandSlug, { date_from: dateFrom, date_to: dateTo })).data.data;
    },
    enabled: Boolean(brandSlug),
  });
  const todayReportQuery = useQuery({
    queryKey: ["brand-operations-report", brandSlug, "today", todayString()],
    queryFn: async () => {
      if (!brandSlug) throw new Error("ไม่พบแบรนด์");
      const today = todayString();
      return (await wapApi.brandOperationsReport(brandSlug, { date_from: today, date_to: today })).data.data;
    },
    enabled: Boolean(brandSlug),
  });
  const stockDashboardQuery = useQuery({
    queryKey: ["brand-stock-dashboard", brandSlug],
    queryFn: async () => {
      if (!brandSlug) throw new Error("ไม่พบแบรนด์");
      return (await wapApi.brandStockDashboard(brandSlug)).data.data;
    },
    enabled: Boolean(brandSlug),
  });

  const report = reportQuery.data;
  const todayReport = todayReportQuery.data;
  const totalSales = (report?.sales_by_branch ?? []).reduce((sum, item) => sum + item.total_amount, 0);
  const totalCentralOrders = (report?.central_orders_by_status ?? []).reduce((sum, item) => sum + item.order_count, 0);
  const totalCaptured = (report?.central_orders_by_status ?? []).reduce((sum, item) => sum + item.captured_amount, 0);
  const totalCredit = (report?.credit_balances ?? []).reduce((sum, item) => sum + item.available_credit, 0);
  const totalShiftClosures = (report?.shift_closures_by_branch ?? []).reduce((sum, item) => sum + item.closure_count, 0);
  const totalShipped = (report?.delivery_by_branch ?? []).reduce((sum, item) => sum + item.shipped_amount, 0);
  const todaySales = (todayReport?.sales_by_branch ?? []).reduce((sum, item) => sum + item.total_amount, 0);
  const todayPendingOrders = (todayReport?.central_orders_by_status ?? [])
    .filter((item) => ["submitted", "reserved_credit", "approved", "packed"].includes(item.status))
    .reduce((sum, item) => sum + item.order_count, 0);
  const todayPackedOrders = (todayReport?.central_orders_by_status ?? [])
    .filter((item) => ["approved", "packed"].includes(item.status))
    .reduce((sum, item) => sum + item.order_count, 0);
  const todayShippedOrders = (todayReport?.delivery_by_branch ?? []).reduce((sum, item) => sum + item.shipped_order_count, 0);
  const lowCreditAccounts = (todayReport?.credit_balances ?? []).filter((item) => item.available_credit <= 0).length;
  const stockDashboard = stockDashboardQuery.data;
  const storeQty = (stockDashboard?.stores ?? []).reduce((sum, item) => sum + item.total_qty, 0);
  const storeSkuCount = (stockDashboard?.stores ?? []).reduce((sum, item) => sum + item.sku_count, 0);

  return (
    <div className="mx-auto flex min-h-full max-w-5xl flex-col gap-4">
      <header className="rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center justify-between gap-3 p-4">
          <div className="flex min-w-0 items-center gap-3">
            <Button asChild variant="outline" size="icon" className="h-10 w-10 shrink-0">
              <Link to={`${centralBase}/orders`} aria-label="กลับหน้าใบสั่ง">
                <ArrowLeft className="h-5 w-5" />
              </Link>
            </Button>
            <div className="min-w-0">
              <h1 className="truncate text-xl font-black text-slate-950">รายงานส่วนกลาง</h1>
              <p className="truncate text-sm text-slate-500">ยอดขาย ใบสั่ง ผลิต และเครดิตของแบรนด์</p>
            </div>
          </div>
          <BarChart2 className="h-6 w-6 text-slate-500" />
        </div>
      </header>

      <section className="rounded-lg border border-slate-200 bg-white">
        <div className="flex flex-col gap-3 border-b border-slate-200 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="font-black text-slate-950">Stock Control Tower</h2>
            <p className="text-sm text-slate-500">RAW, READY, STORE-STOCK และสินค้าระหว่างทาง แยก location ชัดเจน</p>
          </div>
          <Button asChild variant="outline" size="sm"><Link to={`${centralBase}/cutover`}>ตรวจ Cutover</Link></Button>
        </div>
        {stockDashboardQuery.isLoading ? (
          <div className="flex h-28 items-center justify-center text-slate-500"><Loader2 className="mr-2 h-5 w-5 animate-spin" /> โหลด Stock Dashboard</div>
        ) : stockDashboardQuery.isError || !stockDashboard ? (
          <div className="p-4 text-sm font-semibold text-rose-700">โหลด Stock Dashboard ไม่สำเร็จ</div>
        ) : (
          <>
            <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-md border border-slate-200 p-3">
                <p className="flex items-center text-xs font-semibold text-slate-500"><Factory className="mr-1.5 h-4 w-4" /> CENTRAL-RAW</p>
                <p className="mt-1 text-xl font-black text-slate-950">{stockDashboard.central.raw.total_qty.toLocaleString("th-TH")}</p>
                <p className="text-xs text-slate-500">{stockDashboard.central.raw.sku_count} SKU · {money(stockDashboard.central.raw.total_value)}</p>
              </div>
              <div className="rounded-md border border-blue-200 bg-blue-50 p-3">
                <p className="flex items-center text-xs font-semibold text-blue-700"><Boxes className="mr-1.5 h-4 w-4" /> CENTRAL-READY</p>
                <p className="mt-1 text-xl font-black text-blue-800">{stockDashboard.central.ready.total_qty.toLocaleString("th-TH")}</p>
                <p className="text-xs text-blue-700">{stockDashboard.central.ready.sku_count} SKU · {money(stockDashboard.central.ready.total_value)}</p>
              </div>
              <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3">
                <p className="flex items-center text-xs font-semibold text-emerald-700"><Store className="mr-1.5 h-4 w-4" /> STORE-STOCK</p>
                <p className="mt-1 text-xl font-black text-emerald-800">{storeQty.toLocaleString("th-TH")}</p>
                <p className="text-xs text-emerald-700">{storeSkuCount} SKU ใน {stockDashboard.stores.length} สาขา</p>
              </div>
              <div className="rounded-md border border-cyan-200 bg-cyan-50 p-3">
                <p className="flex items-center text-xs font-semibold text-cyan-700"><Truck className="mr-1.5 h-4 w-4" /> ระหว่างทาง</p>
                <p className="mt-1 text-xl font-black text-cyan-800">{stockDashboard.in_transit.total_qty.toLocaleString("th-TH")}</p>
                <p className="text-xs text-cyan-700">{stockDashboard.in_transit.order_count} ใบโอน</p>
              </div>
            </div>
            {(stockDashboard.data_quality.blocker_count > 0 || stockDashboard.data_quality.warning_count > 0) ? (
              <div className="mx-4 mb-4 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                พบ {stockDashboard.data_quality.blocker_count} blocker และ {stockDashboard.data_quality.warning_count} คำเตือน
                {stockDashboard.data_quality.unconfigured_store_count > 0 ? ` · STORE-STOCK ยังไม่พร้อม ${stockDashboard.data_quality.unconfigured_store_count} สาขา` : ""}
              </div>
            ) : null}
            <div className="overflow-x-auto border-t border-slate-200">
              <table className="w-full min-w-[620px] text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500"><tr><th className="px-4 py-3">สาขา</th><th className="px-4 py-3">STORE-STOCK</th><th className="px-4 py-3 text-right">SKU</th><th className="px-4 py-3 text-right">คงเหลือ</th><th className="px-4 py-3 text-right">มูลค่า</th></tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {stockDashboard.stores.map((item) => (
                    <tr key={item.branch_id}>
                      <td className="px-4 py-3 font-bold text-slate-950">{item.branch_name}</td>
                      <td className={`px-4 py-3 ${item.is_valid ? "text-slate-600" : "font-bold text-rose-700"}`}>{item.store_location_name ?? "ยังไม่ตั้ง location"}</td>
                      <td className="px-4 py-3 text-right">{item.sku_count}</td>
                      <td className="px-4 py-3 text-right font-semibold">{item.total_qty.toLocaleString("th-TH")}</td>
                      <td className="px-4 py-3 text-right">{money(item.total_value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="grid gap-3 md:grid-cols-2">
          <Input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
          <Input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white">
        <div className="flex flex-col gap-3 border-b border-slate-200 p-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase text-slate-500">Today Control</p>
            <h2 className="text-lg font-black text-slate-950">ศูนย์ควบคุมงานวันนี้</h2>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to={`${centralBase}/orders`}>
                <ClipboardList className="mr-2 h-4 w-4" />
                ใบสั่ง
              </Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to={`${centralBase}/production`}>
                <PackageCheck className="mr-2 h-4 w-4" />
                ผลิต
              </Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to={`${centralBase}/credits`}>
                <Coins className="mr-2 h-4 w-4" />
                เครดิต
              </Link>
            </Button>
          </div>
        </div>
        {todayReportQuery.isLoading ? (
          <div className="flex h-28 items-center justify-center text-slate-500">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            โหลดสถานะวันนี้
          </div>
        ) : todayReportQuery.isError ? (
          <div className="p-4 text-sm font-semibold text-rose-700">โหลดสถานะวันนี้ไม่สำเร็จ</div>
        ) : (
          <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-5">
            <div className="rounded-md border border-slate-200 p-3">
              <p className="text-xs font-semibold text-slate-500">ยอดขายวันนี้</p>
              <p className="mt-1 text-xl font-black text-slate-950">{money(todaySales)}</p>
            </div>
            <div className={`rounded-md border p-3 ${todayPendingOrders > 0 ? "border-orange-200 bg-orange-50" : "border-slate-200"}`}>
              <p className="text-xs font-semibold text-slate-500">รอครัวกลางจัดการ</p>
              <p className={`mt-1 text-xl font-black ${todayPendingOrders > 0 ? "text-orange-700" : "text-slate-950"}`}>{todayPendingOrders}</p>
            </div>
            <div className="rounded-md border border-slate-200 p-3">
              <p className="text-xs font-semibold text-slate-500">รอแพ็ก/ส่ง</p>
              <p className="mt-1 text-xl font-black text-blue-700">{todayPackedOrders}</p>
            </div>
            <div className="rounded-md border border-slate-200 p-3">
              <p className="text-xs font-semibold text-slate-500">ส่งแล้ววันนี้</p>
              <p className="mt-1 flex items-center text-xl font-black text-emerald-700">
                <Truck className="mr-2 h-5 w-5" />
                {todayShippedOrders}
              </p>
            </div>
            <div className={`rounded-md border p-3 ${lowCreditAccounts > 0 ? "border-rose-200 bg-rose-50" : "border-slate-200"}`}>
              <p className="text-xs font-semibold text-slate-500">เครดิตต้องดู</p>
              <p className={`mt-1 flex items-center text-xl font-black ${lowCreditAccounts > 0 ? "text-rose-700" : "text-slate-950"}`}>
                {lowCreditAccounts > 0 ? <AlertTriangle className="mr-2 h-5 w-5" /> : null}
                {lowCreditAccounts}
              </p>
            </div>
          </div>
        )}
      </section>

      {reportQuery.isLoading ? (
        <div className="flex h-72 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          โหลดรายงาน
        </div>
      ) : reportQuery.isError ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-6 text-center font-semibold text-rose-700">
          โหลดรายงานไม่สำเร็จ
        </div>
      ) : (
        <>
          <section className="grid gap-3 sm:grid-cols-4">
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-500">ยอดขาย</p>
              <p className="mt-2 text-2xl font-black text-slate-950">{money(totalSales)}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-500">ใบสั่งกลาง</p>
              <p className="mt-2 text-2xl font-black text-orange-700">{totalCentralOrders}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-500">Capture Credit</p>
              <p className="mt-2 text-2xl font-black text-emerald-700">{money(totalCaptured)}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-500">เครดิตใช้ได้</p>
              <p className="mt-2 text-2xl font-black text-blue-700">{money(totalCredit)}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-500">ปิดกะ</p>
              <p className="mt-2 text-2xl font-black text-violet-700">{totalShiftClosures}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-500">ยอดส่งสินค้า</p>
              <p className="mt-2 text-2xl font-black text-cyan-700">{money(totalShipped)}</p>
            </div>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-slate-200 bg-white">
              <h2 className="border-b border-slate-200 p-4 font-bold text-slate-950">ยอดขายตามสาขา</h2>
              <div className="divide-y divide-slate-100">
                {(report?.sales_by_branch ?? []).length > 0 ? report?.sales_by_branch.map((item) => (
                  <div key={item.branch_id} className="flex items-center justify-between gap-3 px-4 py-3">
                    <div>
                      <p className="font-bold text-slate-950">{item.branch_name}</p>
                      <p className="text-sm text-slate-500">{item.order_count} บิล</p>
                    </div>
                    <p className="font-black text-slate-950">{money(item.total_amount)}</p>
                  </div>
                )) : <div className="p-8 text-center text-slate-500">ยังไม่มียอดขาย</div>}
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white">
              <h2 className="border-b border-slate-200 p-4 font-bold text-slate-950">ใบสั่งกลางตามสถานะ</h2>
              <div className="divide-y divide-slate-100">
                {(report?.central_orders_by_status ?? []).length > 0 ? report?.central_orders_by_status.map((item) => (
                  <div key={item.status} className="flex items-center justify-between gap-3 px-4 py-3">
                    <div>
                      <p className="font-bold text-slate-950">{statusLabel(item.status)}</p>
                      <p className="text-sm text-slate-500">captured {money(item.captured_amount)}</p>
                    </div>
                    <p className="font-black text-orange-700">{item.order_count}</p>
                  </div>
                )) : <div className="p-8 text-center text-slate-500">ยังไม่มีใบสั่งกลาง</div>}
              </div>
            </div>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-slate-200 bg-white">
              <h2 className="border-b border-slate-200 p-4 font-bold text-slate-950">ยอดขายตามแคชเชียร์</h2>
              <div className="divide-y divide-slate-100">
                {(report?.sales_by_cashier ?? []).length > 0 ? report?.sales_by_cashier.map((item) => (
                  <div key={item.user_id} className="flex items-center justify-between gap-3 px-4 py-3">
                    <div>
                      <p className="font-bold text-slate-950">{item.cashier_name}</p>
                      <p className="text-sm text-slate-500">{item.order_count} บิล</p>
                    </div>
                    <p className="font-black text-slate-950">{money(item.total_amount)}</p>
                  </div>
                )) : <div className="p-8 text-center text-slate-500">ยังไม่มียอดขายตามแคชเชียร์</div>}
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white">
              <h2 className="border-b border-slate-200 p-4 font-bold text-slate-950">ยอดปิดกะตามสาขา</h2>
              <div className="divide-y divide-slate-100">
                {(report?.shift_closures_by_branch ?? []).length > 0 ? report?.shift_closures_by_branch.map((item) => (
                  <div key={item.branch_id} className="flex items-center justify-between gap-3 px-4 py-3">
                    <div>
                      <p className="font-bold text-slate-950">{item.branch_name}</p>
                      <p className="text-sm text-slate-500">{item.closure_count} กะ / {item.order_count} บิล</p>
                    </div>
                    <p className="font-black text-violet-700">{money(item.total_amount)}</p>
                  </div>
                )) : <div className="p-8 text-center text-slate-500">ยังไม่มีข้อมูลปิดกะ</div>}
              </div>
            </div>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-slate-200 bg-white">
              <h2 className="border-b border-slate-200 p-4 font-bold text-slate-950">ยอดผลิตตามวันส่ง</h2>
              <div className="divide-y divide-slate-100">
                {(report?.production_by_date ?? []).length > 0 ? report?.production_by_date.map((item) => (
                  <div key={item.business_date} className="flex items-center justify-between gap-3 px-4 py-3">
                    <div>
                      <p className="font-bold text-slate-950">{item.business_date}</p>
                      <p className="text-sm text-slate-500">{item.order_count} ใบสั่ง</p>
                    </div>
                    <p className="font-black text-emerald-700">{item.requested_qty.toLocaleString("th-TH")}</p>
                  </div>
                )) : <div className="p-8 text-center text-slate-500">ยังไม่มียอดผลิต</div>}
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white">
              <h2 className="border-b border-slate-200 p-4 font-bold text-slate-950">เครดิตคงเหลือแฟรนไชส์</h2>
              <div className="divide-y divide-slate-100">
                {(report?.credit_balances ?? []).length > 0 ? report?.credit_balances.map((item) => (
                  <div key={item.branch_id} className="flex items-center justify-between gap-3 px-4 py-3">
                    <div>
                      <p className="font-bold text-slate-950">{item.branch_name}</p>
                      <p className="text-sm text-slate-500">กันไว้ {money(item.reserved_amount)}</p>
                    </div>
                    <p className="font-black text-blue-700">{money(item.available_credit)}</p>
                  </div>
                )) : <div className="p-8 text-center text-slate-500">ยังไม่มีบัญชีเครดิต</div>}
              </div>
            </div>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-slate-200 bg-white">
              <h2 className="border-b border-slate-200 p-4 font-bold text-slate-950">ส่งและรับสินค้าตามสาขา</h2>
              <div className="divide-y divide-slate-100">
                {(report?.delivery_by_branch ?? []).length > 0 ? report?.delivery_by_branch.map((item) => (
                  <div key={item.branch_id} className="flex items-center justify-between gap-3 px-4 py-3">
                    <div>
                      <p className="font-bold text-slate-950">{item.branch_name}</p>
                      <p className="text-sm text-slate-500">ส่ง {item.shipped_order_count} ใบ / รับ {item.received_order_count} ใบ</p>
                    </div>
                    <div className="text-right">
                      <p className="font-black text-cyan-700">{money(item.shipped_amount)}</p>
                      <p className="text-sm text-slate-500">{item.received_qty.toLocaleString("th-TH")} หน่วย</p>
                    </div>
                  </div>
                )) : <div className="p-8 text-center text-slate-500">ยังไม่มีข้อมูลส่งรับสินค้า</div>}
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white">
              <h2 className="border-b border-slate-200 p-4 font-bold text-slate-950">ยอดขายเทียบยอดเบิกเติม</h2>
              <div className="divide-y divide-slate-100">
                {(report?.sales_vs_replenishment ?? []).length > 0 ? report?.sales_vs_replenishment.map((item) => (
                  <div key={item.branch_id} className="px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-bold text-slate-950">{item.branch_name}</p>
                      <p className={item.delta_amount >= 0 ? "font-black text-emerald-700" : "font-black text-rose-700"}>
                        {money(item.delta_amount)}
                      </p>
                    </div>
                    <p className="mt-1 text-sm text-slate-500">
                      ขาย {money(item.sales_amount)} / เบิก {money(item.requested_amount)} / ส่ง {money(item.shipped_amount)}
                    </p>
                  </div>
                )) : <div className="p-8 text-center text-slate-500">ยังไม่มีข้อมูลเปรียบเทียบ</div>}
              </div>
            </div>
          </section>

          <section className="rounded-lg border border-slate-200 bg-white">
            <h2 className="border-b border-slate-200 p-4 font-bold text-slate-950">ต้นทุนตามสูตร</h2>
            <div className="divide-y divide-slate-100">
              {(report?.recipe_costs ?? []).length > 0 ? report?.recipe_costs.map((item) => (
                <div key={item.recipe_id} className="grid gap-3 px-4 py-3 md:grid-cols-[1fr_auto_auto] md:items-center">
                  <div className="min-w-0">
                    <p className="truncate font-bold text-slate-950">{item.product_name}</p>
                    <p className="truncate text-sm text-slate-500">{recipeTypeLabel(item.recipe_type)} / {item.recipe_name}</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-sm md:min-w-64">
                    <div>
                      <p className="font-semibold text-slate-500">ต้นทุน/สูตร</p>
                      <p className="font-black text-slate-950">{money(item.total_cost)}</p>
                    </div>
                    <div>
                      <p className="font-semibold text-slate-500">ต้นทุน/หน่วย</p>
                      <p className="font-black text-slate-950">{money(item.cost_per_yield)}</p>
                    </div>
                  </div>
                  <div className="text-left md:min-w-28 md:text-right">
                    <p className="text-sm font-semibold text-slate-500">Margin</p>
                    <p className={item.gross_margin_pct >= 40 ? "font-black text-emerald-700" : "font-black text-amber-700"}>
                      {item.gross_margin_pct.toFixed(1)}%
                    </p>
                  </div>
                </div>
              )) : <div className="p-8 text-center text-slate-500">ยังไม่มีสูตรสำหรับคำนวณต้นทุน</div>}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
