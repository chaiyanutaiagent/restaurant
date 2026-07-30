import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ChefHat, Clock, Package, ShoppingCart, TrendingUp, UtensilsCrossed } from "lucide-react";
import { useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import PageHeader from "@/components/layout/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatThaiCurrency } from "@/lib/cartUtils";
import { reportApi } from "@/lib/reportApi";
import { syncStockBalances } from "@/lib/syncService";
import { authApi } from "@/lib/api";
import { branchApi } from "@/lib/adminApi";
import type { ApiResponse } from "@/types/api";
import type { DashboardStats, HourlySales } from "@/types/report";
import type { BranchSettings } from "@/types/admin";
import { useAuthStore } from "@/stores/auth.store";

export default function DashboardPage(): JSX.Element {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const branchId = useAuthStore((state) => state.branchId);
  const permissions = useAuthStore((state) => state.permissions);
  const statsQuery = useQuery({
    queryKey: ["dashboard-stats", branchId],
    queryFn: async () => {
      const response = await reportApi.dashboard(branchId ?? undefined);
      return response.data as ApiResponse<DashboardStats>;
    },
    staleTime: 300_000
  });
  const hourlyQuery = useQuery({
    queryKey: ["dashboard-hourly", branchId],
    queryFn: async () => {
      const response = await reportApi.hourlySales(undefined, branchId ?? undefined);
      return response.data as ApiResponse<HourlySales[]>;
    },
    staleTime: 300_000
  });

  // F&B data
  const fbSettingsQuery = useQuery({
    queryKey: ["branch-settings", branchId],
    queryFn: async () => (await branchApi.getSettings(branchId!)).data.data as BranchSettings,
    enabled: Boolean(branchId),
    staleTime: 300_000,
  });
  const fbEnabled = fbSettingsQuery.data?.fb_enabled ?? false;

  const fbSessionsQuery = useQuery({
    queryKey: ["dashboard-fb-sessions", branchId],
    queryFn: async () => {
      const today = new Date().toISOString().slice(0, 10);
      const res = await authApi.get(`/restaurant/sessions?date=${today}`);
      return res.data.data as { id: string; status: string; queue_number: number | null; total_amount: number }[];
    },
    enabled: fbEnabled,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const fbKitchenQuery = useQuery({
    queryKey: ["dashboard-fb-kitchen", branchId],
    queryFn: async () => {
      const res = await authApi.get("/restaurant/kitchen");
      return res.data.data as { id: string; status: string }[];
    },
    enabled: fbEnabled,
    staleTime: 15_000,
    refetchInterval: 15_000,
  });

  const fbSessions = fbSessionsQuery.data ?? [];
  const fbActive = fbSessions.filter((s) => s.status === "open" || s.status === "bill_requested").length;
  const fbBillRequested = fbSessions.filter((s) => s.status === "bill_requested").length;
  const fbRevenue = fbSessions.filter((s) => s.status === "closed").reduce((sum, s) => sum + s.total_amount, 0);
  const fbPendingTickets = (fbKitchenQuery.data ?? []).filter((t) => t.status === "pending" || t.status === "cooking").length;

  useEffect(() => {
    void syncStockBalances();
  }, []);

  const dashboardStats = statsQuery.data?.data;
  const lowStockCount = dashboardStats?.low_stock_count ?? 0;
  const comparison = dashboardStats?.compared_yesterday_pct;
  const comparisonBadge =
    comparison == null
      ? { label: "N/A", className: "bg-gray-100 text-gray-500" }
      : comparison > 0
        ? { label: `↑ +${Number(comparison).toFixed(1)}%`, className: "bg-green-50 text-green-700" }
        : comparison < 0
          ? { label: `↓ ${Number(comparison).toFixed(1)}%`, className: "bg-red-50 text-red-700" }
          : { label: "= 0.0%", className: "bg-gray-100 text-gray-600" };
  const cards = [
    {
      label: "ออร์เดอร์วันนี้",
      value: dashboardStats ? String(dashboardStats.today_orders) : null,
      subtitle: dashboardStats ? `เฉลี่ย ${formatThaiCurrency(Number(dashboardStats.today_avg_order))} / บิล` : null,
      icon: ShoppingCart,
      color: "text-blue-600 bg-blue-50"
    },
    {
      label: "ยอดขายวันนี้",
      value: dashboardStats ? formatThaiCurrency(Number(dashboardStats.today_sales)) : null,
      subtitle: dashboardStats ? `VAT ${formatThaiCurrency(Number(dashboardStats.today_vat))}` : null,
      badge: comparisonBadge,
      icon: TrendingUp,
      color: "text-green-600 bg-green-50"
    },
    {
      label: "สต็อกต่ำ",
      value: dashboardStats ? String(lowStockCount) : null,
      subtitle: "คลิกเพื่อดูรายการสินค้าใกล้หมด",
      icon: AlertTriangle,
      color: "text-orange-600 bg-orange-50",
      clickable: true
    },
    {
      label: "สินค้าทั้งหมด",
      value: dashboardStats ? String(dashboardStats.total_products) : null,
      subtitle: `เปิดกะอยู่ ${dashboardStats?.open_shifts_count ?? 0} กะ`,
      icon: Package,
      color: "text-blue-600 bg-blue-50"
    }
  ];

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="ภาพรวมระบบ" />
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        {cards.map((stat) => (
          <Card
            key={stat.label}
            className={stat.label === "สต็อกต่ำ" && lowStockCount > 0 ? "border-orange-300" : ""}
          >
            <CardContent className="p-5">
              <button
                type="button"
                className="flex w-full items-start justify-between text-left"
                onClick={() => {
                  if (stat.clickable) {
                    navigate("/stock?tab=2&filter=low");
                  }
                }}
              >
                <div>
                  <p className="text-sm text-gray-500">{stat.label}</p>
                  {stat.value === null ? (
                    <Skeleton className="mt-3 h-8 w-28" />
                  ) : (
                    <p className="mt-3 text-2xl font-semibold text-gray-900">{stat.value}</p>
                  )}
                  {stat.subtitle ? <p className="mt-2 text-xs text-gray-500">{stat.subtitle}</p> : null}
                  {"badge" in stat && stat.badge ? (
                    <span className={`mt-2 inline-flex rounded-full px-2 py-1 text-xs font-medium ${stat.badge.className}`}>
                      {stat.badge.label}
                    </span>
                  ) : null}
                </div>
                <div className={`rounded-xl p-3 ${stat.color}`}>
                  <stat.icon className="h-5 w-5" />
                </div>
              </button>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* F&B Widget */}
      {fbEnabled && (
        <div className="mt-6 rounded-2xl border border-orange-200 bg-gradient-to-r from-orange-50 to-amber-50 p-5">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <UtensilsCrossed className="h-5 w-5 text-orange-600" />
              <p className="font-semibold text-orange-900">F&B — วันนี้</p>
            </div>
            <div className="flex gap-2 text-xs">
              <Link to="/restaurant/orders" className="rounded-full bg-orange-100 px-3 py-1 font-medium text-orange-700 hover:bg-orange-200">
                ออเดอร์
              </Link>
              <Link to="/restaurant/kitchen" className="rounded-full bg-orange-100 px-3 py-1 font-medium text-orange-700 hover:bg-orange-200">
                ครัว
              </Link>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {/* Active Sessions */}
            <div className={`rounded-2xl p-4 ${fbBillRequested > 0 ? "border-2 border-amber-400 bg-amber-50 animate-pulse" : "bg-white/80"}`}>
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-blue-500" />
                <span className="text-xs text-slate-500">โต๊ะ/คิวเปิด</span>
              </div>
              <p className="mt-2 text-3xl font-black text-slate-900">{fbActive}</p>
              {fbBillRequested > 0 && (
                <p className="mt-1 text-xs font-semibold text-amber-700">⚡ เรียกบิล {fbBillRequested}</p>
              )}
            </div>

            {/* Kitchen Pending */}
            <div className="rounded-2xl bg-white/80 p-4">
              <div className="flex items-center gap-2">
                <ChefHat className="h-4 w-4 text-red-500" />
                <span className="text-xs text-slate-500">ครัวรอทำ</span>
              </div>
              <p className="mt-2 text-3xl font-black text-slate-900">{fbPendingTickets}</p>
              <p className="mt-1 text-xs text-slate-400">pending/cooking</p>
            </div>

            {/* Sessions Today */}
            <div className="rounded-2xl bg-white/80 p-4">
              <div className="flex items-center gap-2">
                <ShoppingCart className="h-4 w-4 text-emerald-500" />
                <span className="text-xs text-slate-500">session วันนี้</span>
              </div>
              <p className="mt-2 text-3xl font-black text-slate-900">{fbSessions.length}</p>
              <p className="mt-1 text-xs text-slate-400">ทั้งหมด {fbSessions.filter((s) => s.status === "closed").length} ปิดแล้ว</p>
            </div>

            {/* F&B Revenue */}
            <div className="rounded-2xl bg-white/80 p-4">
              <div className="flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-orange-500" />
                <span className="text-xs text-slate-500">รายได้ F&B</span>
              </div>
              <p className="mt-2 text-xl font-black text-orange-700">{formatThaiCurrency(fbRevenue)}</p>
              <p className="mt-1 text-xs text-slate-400">เฉพาะที่ปิดแล้ว</p>
            </div>
          </div>
        </div>
      )}

      <Card className="mt-6">
        <CardContent className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="font-semibold text-gray-900">ยอดขายรายชั่วโมงวันนี้</p>
              <p className="text-sm text-gray-500">
                ผู้ใช้งานปัจจุบัน: {user?.display_name ?? user?.username ?? "-"} · สิทธิ์ {permissions.length}
              </p>
            </div>
          </div>

          {hourlyQuery.isLoading ? (
            <Skeleton className="h-[120px] w-full" />
          ) : (
            <div className="h-[120px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={(hourlyQuery.data?.data ?? []).map((item) => ({
                    ...item,
                    label: `${String(item.hour).padStart(2, "0")}:00`
                  }))}
                >
                  <defs>
                    <linearGradient id="dashboardSalesGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#2563eb" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#2563eb" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid vertical={false} strokeDasharray="3 3" />
                  <XAxis dataKey="label" hide />
                  <YAxis hide />
                  <Tooltip formatter={(value: number) => formatThaiCurrency(Number(value))} />
                  <Area
                    type="monotone"
                    dataKey="total_amount"
                    stroke="#2563eb"
                    fill="url(#dashboardSalesGradient)"
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
