import { AlertTriangle, CheckCircle2, Loader2, ShieldCheck } from "lucide-react";
import { useTakeawayReleaseGate } from "@/hooks/useTakeawayReleaseGate";

export default function TakeawayReleaseBanner(): JSX.Element {
  const gate = useTakeawayReleaseGate();
  if (gate.isLoading) {
    return <div className="mb-4 flex min-h-12 items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 text-sm font-bold text-slate-500"><Loader2 className="h-4 w-4 animate-spin" />กำลังตรวจ Release Gate จาก Server</div>;
  }
  if (gate.isError) {
    return <div className="mb-4 flex min-h-12 items-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 text-sm font-bold text-rose-800"><AlertTriangle className="h-4 w-4" />อ่านสถานะ Release Gate ไม่ได้ — ปิดการทำรายการไว้ก่อน</div>;
  }
  if (gate.writesEnabled) {
    return <div className="mb-4 flex min-h-12 items-center gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 text-sm font-bold text-emerald-900"><CheckCircle2 className="h-4 w-4" />UAT synthetic transaction mode · ห้ามใช้ข้อมูลหรือลูกค้าจริง</div>;
  }
  return <div className="mb-4 flex min-h-12 items-center gap-2 rounded-2xl border border-amber-300 bg-amber-50 px-4 text-sm font-bold text-amber-950" data-testid="takeaway-write-hold"><ShieldCheck className="h-4 w-4 shrink-0" /><span>Dark launch · ดูข้อมูล, รายงาน, Import dry-run และ Cutover preview ได้ แต่ Server ปิดธุรกรรม Takeaway จริงจนผ่าน Owner/Canary Gate</span></div>;
}
