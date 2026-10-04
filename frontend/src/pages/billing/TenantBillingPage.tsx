import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, CreditCard } from "lucide-react";
import { membershipApi } from "@/lib/api";

function money(satang: number, currency: string): string {
  return new Intl.NumberFormat("th-TH", { style: "currency", currency }).format(satang / 100);
}

export default function TenantBillingPage(): JSX.Element {
  const billing = useQuery({
    queryKey: ["membership", "billing"],
    queryFn: async () => (await membershipApi.billing()).data.data,
  });
  if (billing.isLoading) return <p className="text-gray-500">กำลังโหลดข้อมูลแพ็กเกจ...</p>;
  if (billing.error || !billing.data) return <p className="text-red-600">ไม่สามารถโหลดข้อมูล Billing ได้</p>;
  const data = billing.data;
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div><h1 className="text-2xl font-bold text-gray-900">แพ็กเกจและการเรียกเก็บเงิน</h1><p className="mt-1 text-sm text-gray-500">หน้านี้แสดงสถานะเท่านั้น การเปลี่ยน Plan ต้องติดต่อผู้ดูแลระบบ</p></div>
      {!data.collection_available ? <section className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-900"><div className="flex gap-3"><AlertTriangle className="h-5 w-5 shrink-0" /><div><p className="font-semibold">ระบบรับชำระค่าสมาชิกยังไม่เปิดใช้งาน</p><p className="mt-1 text-sm">ยังไม่มีการหักบัตรหรือเรียกเก็บเงินจริงจากหน้านี้</p></div></div></section> : null}
      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-xl border bg-white p-5 shadow-sm"><div className="flex items-center gap-3"><CreditCard className="h-6 w-6 text-blue-600" /><h2 className="text-lg font-semibold">Plan ปัจจุบัน</h2></div><p className="mt-4 text-2xl font-bold">{data.plan?.name ?? "ยังไม่มี Plan"}</p><p className="mt-1 text-sm text-gray-500">{data.plan?.unit_amount_satang == null ? "ยังไม่กำหนดราคา" : `${money(data.plan.unit_amount_satang, data.plan.currency)} / ${data.plan.billing_interval}`}</p></section>
        <section className="rounded-xl border bg-white p-5 shadow-sm"><div className="flex items-center gap-3"><CheckCircle2 className="h-6 w-6 text-emerald-600" /><h2 className="text-lg font-semibold">Subscription</h2></div><p className="mt-4 text-2xl font-bold">{data.subscription?.status ?? "ไม่มีข้อมูล"}</p><p className="mt-1 text-sm text-gray-500">{data.subscription?.current_period_end ? `รอบปัจจุบันถึง ${new Date(data.subscription.current_period_end).toLocaleDateString("th-TH")}` : "ยังไม่มีรอบเรียกเก็บเงิน"}</p></section>
      </div>
      <section className="rounded-xl border bg-white p-5 shadow-sm"><h2 className="text-lg font-semibold">ใบแจ้งหนี้</h2>{data.invoices.length ? <div className="mt-4 divide-y">{data.invoices.map((invoice) => <div key={invoice.id} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm"><div><p className="font-medium">{invoice.invoice_number}</p><p className="text-gray-500">{new Date(invoice.created_at).toLocaleDateString("th-TH")}</p></div><div className="text-right"><p className="font-semibold">{money(invoice.total_satang, invoice.currency)}</p><p className="text-gray-500">{invoice.status}</p></div></div>)}</div> : <p className="mt-3 text-sm text-gray-500">ยังไม่มีใบแจ้งหนี้</p>}</section>
    </div>
  );
}
