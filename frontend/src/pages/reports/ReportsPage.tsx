import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import PageHeader from "@/components/layout/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { authApi, systemApi } from "@/lib/api";
import { formatThaiCurrency } from "@/lib/cartUtils";
import { reportApi } from "@/lib/reportApi";
import type { ApiResponse } from "@/types/api";
import type { DailySalesSummary, HourlySales, SalesRangeSummary, TopProductsReport } from "@/types/report";
import type { Branch, UserBranch } from "@/types/user";

const CHART_COLORS = ["#2563eb", "#10b981", "#f97316", "#7c3aed", "#ef4444"];
const PAYMENT_LABELS: Record<string, string> = {
  cash: "เงินสด",
  promptpay: "PromptPay",
  credit_card: "บัตรเครดิต",
  bank_transfer: "โอนเงิน",
  other: "อื่นๆ"
};

function todayString(): string {
  return new Date().toISOString().slice(0, 10);
}

function firstDayOfMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
}

function thaiShort(dateString: string): string {
  const [year, month, day] = dateString.split("-");
  return `${day}/${month}`;
}

function paymentEntries(map: Record<string, number>): { name: string; amount: number }[] {
  return Object.entries(map).map(([key, amount]) => ({
    name: PAYMENT_LABELS[key] ?? key,
    amount: Number(amount)
  }));
}

function SummaryCards({
  totalOrders,
  totalAmount,
  totalVat,
  avgOrderValue
}: {
  totalOrders: number;
  totalAmount: number;
  totalVat: number;
  avgOrderValue: number;
}): JSX.Element {
  const cards = [
    { label: "ออร์เดอร์", value: String(totalOrders) },
    { label: "ยอดขาย", value: formatThaiCurrency(totalAmount) },
    { label: "VAT", value: formatThaiCurrency(totalVat) },
    { label: "เฉลี่ย/บิล", value: formatThaiCurrency(avgOrderValue) }
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.label}>
          <CardContent className="p-5">
            <p className="text-sm text-gray-500">{card.label}</p>
            <p className="mt-3 text-2xl font-semibold text-gray-900">{card.value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export default function ReportsPage(): JSX.Element {
  const [dailyDate, setDailyDate] = useState(todayString());
  const [dailyBranchId, setDailyBranchId] = useState("");
  const [rangeBranchId, setRangeBranchId] = useState("");
  const [rangeFrom, setRangeFrom] = useState(firstDayOfMonth());
  const [rangeTo, setRangeTo] = useState(todayString());
  const [topBranchId, setTopBranchId] = useState("");
  const [topFrom, setTopFrom] = useState(firstDayOfMonth());
  const [topTo, setTopTo] = useState(todayString());
  const [hourlyDate, setHourlyDate] = useState(todayString());
  const [hourlyBranchId, setHourlyBranchId] = useState("");
  const [rangeParams, setRangeParams] = useState({ from: firstDayOfMonth(), to: todayString(), branchId: "" });
  const [topParams, setTopParams] = useState({ from: firstDayOfMonth(), to: todayString(), branchId: "" });

  const branchesQuery = useQuery({
    queryKey: ["branches", "reports-page"],
    queryFn: async () => {
      try {
        const response = await systemApi.branches();
        return response.data as ApiResponse<Branch[]>;
      } catch {
        const fallback = await authApi.myBranches();
        return {
          data: fallback.data.data.map((item: UserBranch) => ({
            id: item.branch_id,
            company_id: "",
            code: item.branch_name,
            name: item.branch_name,
            name_en: null,
            is_warehouse: false,
            is_active: true,
            sort_order: 0
          })),
          meta: fallback.data.meta,
          error: fallback.data.error
        } satisfies ApiResponse<Branch[]>;
      }
    }
  });

  const dailyQuery = useQuery({
    queryKey: ["reports", "daily", dailyDate, dailyBranchId],
    queryFn: async () => {
      const response = await reportApi.dailySales(dailyDate, dailyBranchId || undefined);
      return response.data as ApiResponse<DailySalesSummary>;
    }
  });

  const rangeQuery = useQuery({
    queryKey: ["reports", "range", rangeParams.from, rangeParams.to, rangeParams.branchId],
    queryFn: async () => {
      const response = await reportApi.salesRange(
        rangeParams.from,
        rangeParams.to,
        rangeParams.branchId || undefined
      );
      return response.data as ApiResponse<SalesRangeSummary>;
    }
  });

  const topProductsQuery = useQuery({
    queryKey: ["reports", "top-products", topParams.from, topParams.to, topParams.branchId],
    queryFn: async () => {
      const response = await reportApi.topProducts(
        topParams.from,
        topParams.to,
        topParams.branchId || undefined
      );
      return response.data as ApiResponse<TopProductsReport>;
    }
  });

  const hourlyQuery = useQuery({
    queryKey: ["reports", "hourly", hourlyDate, hourlyBranchId],
    queryFn: async () => {
      const response = await reportApi.hourlySales(hourlyDate, hourlyBranchId || undefined);
      return response.data as ApiResponse<HourlySales[]>;
    }
  });

  const branches = branchesQuery.data?.data ?? [];
  const daily = dailyQuery.data?.data;
  const range = rangeQuery.data?.data;
  const topProducts = topProductsQuery.data?.data;
  const hourly = hourlyQuery.data?.data ?? [];
  const totalTopAmount = useMemo(
    () => (topProducts?.items ?? []).reduce((sum, item) => sum + Number(item.total_amount), 0),
    [topProducts?.items]
  );
  const peakHour = useMemo(
    () => hourly.reduce((peak, current) => (Number(current.total_amount) > Number(peak.total_amount) ? current : peak), hourly[0] ?? { hour: 0, total_amount: 0, total_orders: 0 }),
    [hourly]
  );

  return (
    <div>
      <PageHeader title="รายงาน" subtitle="วิเคราะห์ยอดขายและสต็อก" />

      <Tabs defaultValue="daily">
        <TabsList className="flex h-auto flex-wrap gap-2 bg-transparent p-0">
          <TabsTrigger value="daily">ยอดขายรายวัน</TabsTrigger>
          <TabsTrigger value="range">ยอดขายช่วงเวลา</TabsTrigger>
          <TabsTrigger value="top">สินค้าขายดี</TabsTrigger>
          <TabsTrigger value="hourly">รายชั่วโมง</TabsTrigger>
        </TabsList>

        <TabsContent value="daily" className="space-y-6">
          <Card>
            <CardContent className="grid gap-3 p-4 md:grid-cols-2">
              <Input type="date" value={dailyDate} onChange={(event) => setDailyDate(event.target.value)} />
              <select
                className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                value={dailyBranchId}
                onChange={(event) => setDailyBranchId(event.target.value)}
              >
                <option value="">ทุกสาขา</option>
                {branches.map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name}
                  </option>
                ))}
              </select>
            </CardContent>
          </Card>

          {dailyQuery.isLoading || !daily ? (
            <div className="space-y-4">
              <Skeleton className="h-28 w-full" />
              <Skeleton className="h-80 w-full" />
            </div>
          ) : (
            <>
              <SummaryCards
                totalOrders={daily.total_orders}
                totalAmount={Number(daily.total_amount)}
                totalVat={Number(daily.total_vat)}
                avgOrderValue={Number(daily.avg_order_value)}
              />

              <Card>
                <CardContent className="p-4">
                  <h3 className="font-semibold text-gray-900">สัดส่วนวิธีชำระเงิน</h3>
                  <div className="mt-4 grid gap-6 lg:grid-cols-[1fr_260px]">
                    <div className="h-80">
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie
                            data={paymentEntries(daily.by_payment_method)}
                            dataKey="amount"
                            nameKey="name"
                            innerRadius={70}
                            outerRadius={110}
                            paddingAngle={4}
                          >
                            {paymentEntries(daily.by_payment_method).map((entry, index) => (
                              <Cell key={entry.name} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                            ))}
                          </Pie>
                          <Tooltip formatter={(value: number) => formatThaiCurrency(Number(value))} />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                    <div className="space-y-3">
                      {paymentEntries(daily.by_payment_method).map((item, index) => (
                        <div key={item.name} className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 text-sm">
                          <span className="flex items-center gap-2">
                            <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: CHART_COLORS[index % CHART_COLORS.length] }} />
                            {item.name}
                          </span>
                          <span className="font-medium">{formatThaiCurrency(item.amount)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </>
          )}
        </TabsContent>

        <TabsContent value="range" className="space-y-6">
          <Card>
            <CardContent className="grid gap-3 p-4 md:grid-cols-4">
              <Input type="date" value={rangeFrom} onChange={(event) => setRangeFrom(event.target.value)} />
              <Input type="date" value={rangeTo} onChange={(event) => setRangeTo(event.target.value)} />
              <select
                className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                value={rangeBranchId}
                onChange={(event) => setRangeBranchId(event.target.value)}
              >
                <option value="">ทุกสาขา</option>
                {branches.map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white"
                onClick={() => setRangeParams({ from: rangeFrom, to: rangeTo, branchId: rangeBranchId })}
              >
                ดูรายงาน
              </button>
            </CardContent>
          </Card>

          {rangeQuery.isLoading || !range ? (
            <div className="space-y-4">
              <Skeleton className="h-28 w-full" />
              <Skeleton className="h-96 w-full" />
            </div>
          ) : (
            <>
              <SummaryCards
                totalOrders={range.grand_total_orders}
                totalAmount={Number(range.grand_total_amount)}
                totalVat={Number(range.grand_total_vat)}
                avgOrderValue={
                  range.grand_total_orders > 0
                    ? Number(range.grand_total_amount) / range.grand_total_orders
                    : 0
                }
              />
              <div className="grid gap-6 xl:grid-cols-2">
                <Card>
                  <CardContent className="p-4">
                    <h3 className="font-semibold text-gray-900">แนวโน้มยอดขาย</h3>
                    <div className="mt-4 h-96">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={range.days}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="date" tickFormatter={thaiShort} />
                          <YAxis yAxisId="amount" tickFormatter={(value) => `${Number(value).toLocaleString("th-TH")}`} />
                          <YAxis yAxisId="orders" orientation="right" allowDecimals={false} />
                          <Tooltip
                            formatter={(value: number, key) =>
                              key === "total_orders"
                                ? [value, "ออร์เดอร์"]
                                : [formatThaiCurrency(Number(value)), "ยอดขาย"]
                            }
                            labelFormatter={(_label: string | number, payload: any[]) =>
                              payload?.[0]?.payload?.date_thai ?? ""
                            }
                          />
                          <Legend />
                          <Line yAxisId="amount" type="monotone" dataKey="total_amount" stroke="#2563eb" name="ยอดขาย" strokeWidth={3} />
                          <Line yAxisId="orders" type="monotone" dataKey="total_orders" stroke="#f97316" name="ออร์เดอร์" strokeWidth={2} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4">
                    <h3 className="font-semibold text-gray-900">ยอดขายตามวิธีชำระเงิน</h3>
                    <div className="mt-4 h-96">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={paymentEntries(range.by_payment_method)}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="name" />
                          <YAxis tickFormatter={(value) => `${Number(value).toLocaleString("th-TH")}`} />
                          <Tooltip formatter={(value: number) => formatThaiCurrency(Number(value))} />
                          <Bar dataKey="amount" radius={[8, 8, 0, 0]}>
                            {paymentEntries(range.by_payment_method).map((item, index) => (
                              <Cell key={item.name} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </>
          )}
        </TabsContent>

        <TabsContent value="top" className="space-y-6">
          <Card>
            <CardContent className="grid gap-3 p-4 md:grid-cols-4">
              <Input type="date" value={topFrom} onChange={(event) => setTopFrom(event.target.value)} />
              <Input type="date" value={topTo} onChange={(event) => setTopTo(event.target.value)} />
              <select
                className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                value={topBranchId}
                onChange={(event) => setTopBranchId(event.target.value)}
              >
                <option value="">ทุกสาขา</option>
                {branches.map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white"
                onClick={() => setTopParams({ from: topFrom, to: topTo, branchId: topBranchId })}
              >
                ดูรายงาน
              </button>
            </CardContent>
          </Card>

          {topProductsQuery.isLoading || !topProducts ? (
            <div className="space-y-4">
              <Skeleton className="h-96 w-full" />
            </div>
          ) : (
            <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
              <Card>
                <CardContent className="p-4">
                  <h3 className="font-semibold text-gray-900">ตารางสินค้าขายดี</h3>
                  <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead>
                        <tr className="border-b text-left text-gray-500">
                          <th className="px-2 py-2">อันดับ</th>
                          <th className="px-2 py-2">สินค้า</th>
                          <th className="px-2 py-2">จำนวนขาย</th>
                          <th className="px-2 py-2">จำนวนบิล</th>
                          <th className="px-2 py-2 text-right">ยอดขาย</th>
                          <th className="px-2 py-2">% ของยอดรวม</th>
                        </tr>
                      </thead>
                      <tbody>
                        {topProducts.items.map((item, index) => {
                          const ratio = totalTopAmount > 0 ? (Number(item.total_amount) / totalTopAmount) * 100 : 0;
                          return (
                            <tr key={item.product_id} className="border-b last:border-0">
                              <td className="px-2 py-2">{index + 1}</td>
                              <td className="px-2 py-2">
                                <div className="font-medium">{item.product_name}</div>
                                <div className="text-xs text-gray-500">{item.sku}</div>
                              </td>
                              <td className="px-2 py-2">{Number(item.total_qty).toLocaleString("th-TH")}</td>
                              <td className="px-2 py-2">{item.order_count}</td>
                              <td className="px-2 py-2 text-right font-semibold">{formatThaiCurrency(Number(item.total_amount))}</td>
                              <td className="px-2 py-2">
                                <div className="h-2 w-32 rounded-full bg-gray-100">
                                  <div className="h-2 rounded-full bg-blue-600" style={{ width: `${Math.max(ratio, 4)}%` }} />
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <h3 className="font-semibold text-gray-900">Top 10 ยอดขาย</h3>
                  <div className="mt-4 h-[520px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        data={topProducts.items.slice(0, 10).map((item) => ({
                          ...item,
                          product_label:
                            item.product_name.length > 20
                              ? `${item.product_name.slice(0, 20)}...`
                              : item.product_name
                        }))}
                        layout="vertical"
                      >
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis type="number" tickFormatter={(value) => `${Number(value).toLocaleString("th-TH")}`} />
                        <YAxis type="category" dataKey="product_label" width={120} />
                        <Tooltip formatter={(value: number) => formatThaiCurrency(Number(value))} />
                        <Bar dataKey="total_amount" fill="#2563eb" radius={[0, 8, 8, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        <TabsContent value="hourly" className="space-y-6">
          <Card>
            <CardContent className="grid gap-3 p-4 md:grid-cols-3">
              <Input type="date" value={hourlyDate} onChange={(event) => setHourlyDate(event.target.value)} />
              <select
                className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                value={hourlyBranchId}
                onChange={(event) => setHourlyBranchId(event.target.value)}
              >
                <option value="">ทุกสาขา</option>
                {branches.map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name}
                  </option>
                ))}
              </select>
            </CardContent>
          </Card>

          {hourlyQuery.isLoading ? (
            <Skeleton className="h-96 w-full" />
          ) : (
            <Card>
              <CardContent className="p-4">
                <h3 className="font-semibold text-gray-900">ยอดขายรายชั่วโมง</h3>
                <div className="mt-4 h-96">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={hourly.map((item) => ({ ...item, label: `${String(item.hour).padStart(2, "0")}:00` }))}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="label" interval={1} angle={-40} textAnchor="end" height={60} />
                      <YAxis tickFormatter={(value) => `${Number(value).toLocaleString("th-TH")}`} />
                      <Tooltip
                        formatter={(value: number, key) =>
                          key === "total_orders"
                            ? [value, "จำนวนบิล"]
                            : [formatThaiCurrency(Number(value)), "ยอดขาย"]
                        }
                      />
                      <Bar dataKey="total_amount" radius={[8, 8, 0, 0]}>
                        {hourly.map((item) => (
                          <Cell
                            key={item.hour}
                            fill={item.hour === peakHour.hour && Number(item.total_amount) > 0 ? "#f97316" : "#2563eb"}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
