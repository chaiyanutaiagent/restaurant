import { BarChart2, ChefHat, QrCode, Settings, Store, Table2, UtensilsCrossed } from "lucide-react";
import { Link } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/stores/auth.store";

const adminItems: Array<{
  title: string;
  to: string;
  permission?: string;
  permissions?: string[];
  icon: typeof Settings;
  tone: string;
}> = [
  {
    title: "ตั้งค่าร้านอาหาร",
    to: "/restaurant/settings",
    permission: "fb.settings.manage",
    icon: Settings,
    tone: "bg-orange-600",
  },
  {
    title: "Brand Admin",
    to: "/restaurant/brands",
    permission: "fb.settings.manage",
    icon: Store,
    tone: "bg-emerald-700",
  },
  {
    title: "ผังโต๊ะ",
    to: "/restaurant/tables",
    permission: "fb.table.manage",
    icon: Table2,
    tone: "bg-amber-600",
  },
  {
    title: "QR Menu",
    to: "/restaurant/qr",
    permission: "fb.settings.manage",
    icon: QrCode,
    tone: "bg-slate-700",
  },
  {
    title: "สูตรอาหาร",
    to: "/restaurant/recipes",
    permission: "fb.recipe.manage",
    icon: UtensilsCrossed,
    tone: "bg-purple-600",
  },
  {
    title: "Kitchen",
    to: "/restaurant/kitchen",
    permissions: ["fb.kitchen.ticket.manage", "fb.kitchen.manage"],
    icon: ChefHat,
    tone: "bg-red-600",
  },
  {
    title: "รายงานวัตถุดิบ",
    to: "/restaurant/reports/ingredients",
    permission: "fb.report.view",
    icon: BarChart2,
    tone: "bg-blue-600",
  },
];

export default function RestaurantAdminPage(): JSX.Element {
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const visibleItems = adminItems.filter((item) =>
    item.permissions?.some((permission) => hasPermission(permission))
    ?? (item.permission ? hasPermission(item.permission) : false)
  );

  return (
    <div>
      <PageHeader
        title="Restaurant Admin"
        subtitle="จัดการหลังบ้านของร้านอาหาร"
        actions={
          hasPermission("fb.order.create") ? (
            <Button asChild>
              <Link to="/restaurant/orders">ออเดอร์วันนี้</Link>
            </Button>
          ) : null
        }
      />

      {visibleItems.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
          ยังไม่มีเมนู Restaurant Admin สำหรับสิทธิ์ของผู้ใช้นี้
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {visibleItems.map((item) => (
            <Link
              key={`${item.title}-${item.to}`}
              to={item.to}
              className="flex min-h-[8rem] items-start gap-4 rounded-lg border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
            >
              <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-white ${item.tone}`}>
                <item.icon className="h-5 w-5" />
              </div>
              <div>
                <div className="font-semibold text-slate-950">{item.title}</div>
                <div className="mt-2 text-sm text-slate-500">{item.to}</div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
