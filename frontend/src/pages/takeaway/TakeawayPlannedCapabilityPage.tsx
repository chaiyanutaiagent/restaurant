import { ArrowLeft, Construction } from "lucide-react";
import { Link } from "react-router-dom";

const content = {
  recipes: {
    eyebrow: "WP19 · Central parity",
    title: "พื้นที่สูตร Takeaway พร้อมแล้ว",
    detail: "กำลังเชื่อมสูตรผลิต เวอร์ชัน Yield, Loss, UOM และต้นทุนเข้ากับฐาน Takeaway โดยไม่อ่าน Restaurant database ข้ามระบบ",
    back: "/takeaway/central/production",
  },
  cutover: {
    eyebrow: "WP21 · Migration gate",
    title: "พื้นที่ Cutover ถูกล็อกไว้",
    detail: "จะเปิดเมื่อ exporter, signed snapshot, reconciliation และ rollback evidence ผ่านครบ เพื่อป้องกันการนำข้อมูลจริงเข้าก่อนอนุมัติ",
    back: "/takeaway/admin/import",
  },
} as const;

export default function TakeawayPlannedCapabilityPage({ capability }: { capability: keyof typeof content }): JSX.Element {
  const item = content[capability];
  return (
    <section className="mx-auto max-w-3xl rounded-3xl border border-amber-200 bg-white p-7 shadow-sm">
      <div className="inline-flex rounded-2xl bg-amber-100 p-3 text-amber-800"><Construction className="h-7 w-7" /></div>
      <p className="mt-5 text-xs font-black uppercase tracking-[0.24em] text-amber-700">{item.eyebrow}</p>
      <h1 className="mt-2 text-3xl font-black text-slate-950">{item.title}</h1>
      <p className="mt-3 leading-7 text-slate-600">{item.detail}</p>
      <Link to={item.back} className="mt-6 inline-flex items-center gap-2 rounded-xl border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700 hover:bg-slate-50">
        <ArrowLeft className="h-4 w-4" /> กลับไปงานที่ใช้งานได้
      </Link>
    </section>
  );
}
