import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Factory, PackageCheck, ShoppingBag, Warehouse } from "lucide-react";
import { Link } from "react-router-dom";
import { takeawayApi } from "@/lib/takeawayApi";
import { useAuthStore } from "@/stores/auth.store";

const cards = [
  { to: "/takeaway/store/orders", permission: "takeaway.sale.create", title: "ขายและชำระก่อนผลิต", detail: "รับเงิน ออกเลขคิว ส่งครัว และออกใบเสร็จในรายการเดียว", icon: ShoppingBag, color: "bg-emerald-500" },
  { to: "/takeaway/store/kitchen", permission: "takeaway.kitchen.manage", title: "ครัวและจุดรับสินค้า", detail: "เรียงคิวจากชำระแล้วจนถึงพร้อมรับและรับสินค้า", icon: PackageCheck, color: "bg-amber-400" },
  { to: "/takeaway/central/production", permission: "takeaway.production.manage", title: "ผลิตหลายแบรนด์", detail: "สูตรและล็อตผลิตแยกแบรนด์ แต่ตัดวัตถุดิบกองกลางร่วมกัน", icon: Factory, color: "bg-violet-500" },
  { to: "/takeaway/central/stock", permission: "takeaway.stock.manage", title: "สต๊อกส่วนกลาง", detail: "ยอดเดียวต่อสินค้าและตำแหน่ง พร้อมประวัติรับ จ่าย โอน และของเสีย", icon: Warehouse, color: "bg-sky-500" },
];

export default function TakeawayDashboardPage(): JSX.Element {
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const statusQuery = useQuery({ queryKey: ["takeaway", "status"], queryFn: async () => (await takeawayApi.status()).data.data });
  const context = statusQuery.data;
  return (
    <div className="space-y-5">
      <section className="overflow-hidden rounded-3xl bg-slate-950 p-6 text-white shadow-xl md:p-8">
        <div className="flex flex-wrap items-center justify-between gap-5">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.28em] text-emerald-400">Phase 6 workspace</p>
            <h1 className="mt-2 text-3xl font-black md:text-4xl">Take away POS</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-300">ร้านรับสินค้าจากส่วนกลาง ขายหน้าร้านแบบชำระก่อนผลิต และส่งยอดแยกธุรกิจกลับ ERP กลาง</p>
          </div>
          <div className="rounded-2xl border border-slate-700 bg-slate-900 px-5 py-4">
            <p className="text-xs text-slate-400">สถานะบริการ</p>
            <p className="mt-1 flex items-center gap-2 font-bold"><span className={`h-2.5 w-2.5 rounded-full ${context?.writes_enabled ? "bg-emerald-400" : "bg-amber-400"}`} />{statusQuery.isLoading ? "กำลังตรวจ" : context?.writes_enabled ? "UAT ข้อมูลทดสอบ" : "Dark launch · อ่านอย่างเดียว"}</p>
          </div>
        </div>
      </section>
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {cards.filter((card) => hasPermission(card.permission)).map((card) => (
          <Link key={card.to} to={card.to} className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
            <div className={`inline-flex rounded-xl p-3 text-white ${card.color}`}><card.icon className="h-6 w-6" /></div>
            <h2 className="mt-4 font-black">{card.title}</h2>
            <p className="mt-1 min-h-10 text-sm text-slate-500">{card.detail}</p>
            <span className="mt-4 flex items-center gap-1 text-sm font-bold text-emerald-700">{context?.writes_enabled ? "เปิดใช้งาน" : "เปิดดูหน้าจอ"} <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" /></span>
          </Link>
        ))}
      </section>
      {!statusQuery.isLoading && !context?.writes_enabled ? <section className="rounded-2xl border border-amber-300 bg-amber-50 p-5 text-sm text-amber-950"><p className="font-black">ขอบเขตที่ยัง HOLD</p><p className="mt-1">รายการขายจริง · ข้อมูล Chambo จริง · Payment/Tax Provider จริง · Production activation · Owner/Canary sign-off</p></section> : null}
      <section className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-5 text-sm md:grid-cols-3">
        <div><p className="font-bold">แยกขอบเขตข้อมูล</p><p className="mt-1 text-slate-500">Takeaway มีฐานปฏิบัติการของตัวเอง ไม่ปน Restaurant</p></div>
        <div><p className="font-bold">ใช้วัตถุดิบร่วม</p><p className="mt-1 text-slate-500">แบรนด์ต่างกันตัดยอดวัตถุดิบกองกลางเดียวกันได้</p></div>
        <div><p className="font-bold">ย้อนกลับได้</p><p className="mt-1 text-slate-500">นำเข้า Chambo แบบตรวจสอบก่อน และเก็บประวัติโดยไม่ยิงผลกระทบซ้ำ</p></div>
      </section>
    </div>
  );
}
