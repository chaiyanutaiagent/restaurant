import { BarChart2, Clock, CreditCard, ReceiptText, Settings, ShoppingCart } from "lucide-react";
import { Link } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/stores/auth.store";

const adminItems = [
  {
    title: "ขายหน้าร้าน",
    to: "/pos",
    permission: "pos.sale.create",
    icon: ShoppingCart,
    tone: "bg-emerald-600",
  },
  {
    title: "ประวัติกะ",
    to: "/shift-history",
    permission: "pos.report.view",
    icon: Clock,
    tone: "bg-sky-600",
  },
  {
    title: "รายงาน POS",
    to: "/reports",
    permission: "pos.report.view",
    icon: BarChart2,
    tone: "bg-blue-600",
  },
  {
    title: "PromptPay / ใบเสร็จ",
    to: "/settings",
    permission: "system.company.edit",
    icon: ReceiptText,
    tone: "bg-slate-700",
  },
  {
    title: "วิธีชำระเงิน",
    to: "/settings",
    permission: "system.company.edit",
    icon: CreditCard,
    tone: "bg-indigo-600",
  },
  {
    title: "ตั้งค่า POS",
    to: "/settings",
    permission: "system.company.edit",
    icon: Settings,
    tone: "bg-zinc-700",
  },
];

export default function POSAdminPage(): JSX.Element {
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const visibleItems = adminItems.filter((item) => hasPermission(item.permission));

  return (
    <div>
      <PageHeader
        title="POS Admin"
        subtitle="จัดการงานหลังบ้านของจุดขาย"
        actions={
          hasPermission("pos.sale.create") ? (
            <Button asChild>
              <Link to="/pos">เปิด POS</Link>
            </Button>
          ) : null
        }
      />

      {visibleItems.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
          ยังไม่มีเมนู POS Admin สำหรับสิทธิ์ของผู้ใช้นี้
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
