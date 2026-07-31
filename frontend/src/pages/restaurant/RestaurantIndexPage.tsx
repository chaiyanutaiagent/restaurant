import { useQuery } from "@tanstack/react-query";
import { BarChart2, ChefHat, ConciergeBell, Monitor, QrCode, ShoppingBag, UtensilsCrossed } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { fbApi } from "@/lib/fbApi";
import { brandNavigationApi } from "@/lib/brandNavigationApi";
import { useAuthStore } from "@/stores/auth.store";
import PageHeader from "@/components/layout/PageHeader";

export default function RestaurantIndexPage(): JSX.Element {
  const navigate = useNavigate();
  const branchId = useAuthStore((s) => s.branchId);
  const hasPermission = useAuthStore((s) => s.hasPermission);

  const settingsQuery = useQuery({
    queryKey: ["branch-settings", branchId],
    queryFn: async () => (await fbApi.settings()).data.data,
    enabled: Boolean(branchId),
  });
  const brandNavigationQuery = useQuery({
    queryKey: ["brand-navigation"],
    queryFn: async () => (await brandNavigationApi.mine()).data.data,
    enabled: Boolean(branchId),
    staleTime: 60_000,
  });

  const settings = settingsQuery.data;
  const currentBrand = brandNavigationQuery.data?.find((brand) =>
    brand.branches.some((branch) => branch.branch_id === branchId),
  );
  const currentBrandBranch = currentBrand?.branches.find((branch) => branch.branch_id === branchId);

  if (settingsQuery.isLoading) {
    return <div className="p-8 text-center text-slate-500">กำลังโหลด...</div>;
  }

  if (!settings?.fb_setup_completed) {
    navigate("/restaurant/setup");
    return <></>;
  }

  const hasTables = settings.fb_service_mode !== "quick_service";

  const cards = [
    {
      to: "/restaurant/wap",
      permission: "fb.order.create",
      icon: <ShoppingBag className="h-7 w-7" />,
      title: "ขายหน้าร้าน / กลับบ้าน",
      desc: "รับออเดอร์ ชำระเงิน และออกเลขคิว",
      color: "bg-emerald-600",
    },
    ...(hasTables ? [
      {
        to: "/restaurant/tables",
        permission: "fb.table.manage",
        icon: <ConciergeBell className="h-7 w-7" />,
        title: "โต๊ะ / QR รับกลับ",
        desc: "เปิดโต๊ะหรือคิวรับกลับ แล้วออก QR เฉพาะรอบ",
        color: "bg-orange-500",
      },
    ] : []),
    {
      to: "/restaurant/orders",
      permission: "fb.order.create",
      icon: <UtensilsCrossed className="h-7 w-7" />,
      title: "ออเดอร์",
      desc: "ดูออเดอร์จากโต๊ะ หน้าร้าน และ QR ในที่เดียว",
      color: "bg-indigo-500",
    },
    {
      to: "/restaurant/kitchen",
      permission: "fb.kitchen.manage",
      icon: <ChefHat className="h-7 w-7" />,
      title: "Kitchen Display",
      desc: "หน้าจอครัว — รับและอัปเดตสถานะออเดอร์",
      color: "bg-red-500",
    },
    ...(settings.fb_pickup_display_enabled ? [
      {
        to: "/restaurant/pickup",
        permission: "fb.kitchen.manage",
        icon: <Monitor className="h-7 w-7" />,
        title: "หน้าจอคิวเคาน์เตอร์",
        desc: "เปิดบน TV/tablet ที่เคาน์เตอร์",
        color: "bg-emerald-500",
      },
    ] : []),
    {
      to: "/restaurant/recipes",
      permission: "fb.recipe.manage",
      icon: <UtensilsCrossed className="h-7 w-7" />,
      title: "เมนูและสูตรอาหาร",
      desc: "จัดการสูตร ต้นทุน และการตัดสต็อก",
      color: "bg-purple-500",
    },
    {
      to: "/restaurant/qr",
      permission: "fb.settings.manage",
      icon: <QrCode className="h-7 w-7" />,
      title: "QR รับออเดอร์",
      desc: hasTables ? "ดูวิธีออก QR ต่อรอบสำหรับโต๊ะและคิวรับกลับ" : "สร้าง QR สำหรับสั่งกลับบ้านและรับเลขคิว",
      color: "bg-slate-600",
    },
    {
      to: "/restaurant/reports/ingredients",
      permission: "fb.report.view",
      icon: <BarChart2 className="h-7 w-7" />,
      title: "รายงานวัตถุดิบ",
      desc: "ต้นทุน ปริมาณใช้ และ variance รายวัน/รายกะ",
      color: "bg-indigo-500",
    },
  ].filter((card) => hasPermission(card.permission));

  return (
    <div>
      <PageHeader
        title={currentBrand?.name ?? "Restaurant"}
        subtitle={`${currentBrandBranch?.branch_name ?? "สาขาปัจจุบัน"} · ${hasTables ? "ร้านมีโต๊ะและรองรับออเดอร์กลับบ้าน" : "รับออเดอร์กลับบ้านและเรียกคิว"}`}
        actions={
          hasPermission("fb.settings.manage") ? (
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" asChild>
                <Link to="/restaurant/brands">จัดการแบรนด์</Link>
              </Button>
              <Button variant="outline" asChild>
                <Link to="/restaurant/settings">ตั้งค่าร้าน</Link>
              </Button>
            </div>
          ) : null
        }
      />
      <div className="p-6">
        {cards.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
            ยังไม่มีเมนู F&B สำหรับสิทธิ์ของผู้ใช้นี้
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {cards.map((card) => (
            <Link
              key={card.to}
              to={card.to}
              className="flex items-start gap-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
            >
              <div className={`rounded-xl p-3 text-white ${card.color}`}>
                {card.icon}
              </div>
              <div>
                <div className="font-semibold text-slate-900">{card.title}</div>
                <div className="mt-1 text-sm text-slate-500">{card.desc}</div>
              </div>
            </Link>
          ))}
          </div>
        )}
      </div>
    </div>
  );
}
