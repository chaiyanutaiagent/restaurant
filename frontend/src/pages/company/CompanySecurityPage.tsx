import { useQuery } from "@tanstack/react-query";
import { KeyRound, LockKeyhole, Radar, ShieldAlert } from "lucide-react";
import CompanyStatePanel from "@/components/company/CompanyStatePanel";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { companyAccessApi } from "@/lib/adminApi";
import { companyRequestState } from "@/lib/companyPresentation";

export default function CompanySecurityPage(): JSX.Element {
  const posture = useQuery({
    queryKey: ["company-access", "security"],
    queryFn: async () => (await companyAccessApi.security()).data.data,
    retry: false,
  });
  if (posture.isLoading) return <CompanyStatePanel kind="loading" />;
  if (posture.error || !posture.data) return <CompanyStatePanel kind={companyRequestState(posture.error)} onRetry={() => void posture.refetch()} />;
  const cards = [
    { icon: KeyRound, title: "การจัดการ Session", state: posture.data.session_management_enabled ? "พร้อมใช้" : "ปิด", note: "ดูและยกเลิก Session ได้จากหน้าตรวจทบทวนสิทธิ์" },
    { icon: LockKeyhole, title: "Tenant MFA", state: "HOLD", note: "ยังไม่บังคับใช้จนกว่า Product Owner จะอนุมัตินโยบายและขั้นตอนกู้คืน" },
    { icon: ShieldAlert, title: "การกู้คืนบัญชี", state: "รอข้อสรุป", note: "ยังไม่มีการเปิด reset ที่ข้ามหลักฐานหรือข้าม Company Owner" },
    { icon: Radar, title: "แจ้งเตือน Login ผิดปกติ", state: "วางแผนแล้ว", note: "ยังไม่เปิดการแจ้งเตือนจริงใน WP60" },
  ];
  return <div data-testid="company-security-page"><PageHeader title="ความปลอดภัยบริษัท" subtitle="สถานะนโยบายของบริษัทแบบอ่านอย่างเดียว จุดที่ยัง HOLD จะไม่ถูกเปิดโดยอัตโนมัติ" /><div className="grid gap-4 md:grid-cols-2">{cards.map((card) => <section key={card.title} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-start justify-between gap-3"><span className="rounded-xl bg-blue-50 p-3 text-blue-700"><card.icon className="h-6 w-6" /></span><Badge variant="outline">{card.state}</Badge></div><h2 className="mt-4 text-lg font-black">{card.title}</h2><p className="mt-1 text-sm leading-6 text-slate-600">{card.note}</p></section>)}</div><p className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">{posture.data.note}</p></div>;
}
