import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CreditCard, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { platformApi, platformErrorMessage } from "@/lib/platformApi";

function money(satang: number | null, currency: string): string {
  if (satang === null) return "ยังไม่กำหนดราคา";
  return new Intl.NumberFormat("th-TH", { style: "currency", currency }).format(satang / 100);
}

export default function PlatformBillingPage(): JSX.Element {
  const queryClient = useQueryClient();
  const overview = useQuery({
    queryKey: ["platform", "billing"],
    queryFn: async () => (await platformApi.billingOverview()).data.data,
  });
  const starter = overview.data?.plans.find((plan) => plan.code === "starter") ?? overview.data?.plans[0];
  const [amountBaht, setAmountBaht] = useState("");
  const [isPublic, setIsPublic] = useState(false);
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (!starter) return;
    setAmountBaht(starter.unit_amount_satang === null ? "" : String(starter.unit_amount_satang / 100));
    setIsPublic(starter.is_public);
  }, [starter]);

  const save = useMutation({
    mutationFn: async () => {
      if (!starter) throw new Error("ไม่พบ Plan ที่จะแก้ไข");
      if (!reason.trim()) throw new Error("กรุณาระบุเหตุผลสำหรับ Audit Log");
      const parsed = amountBaht.trim() === "" ? null : Number(amountBaht);
      if (parsed !== null && (!Number.isFinite(parsed) || parsed < 0)) throw new Error("ราคาไม่ถูกต้อง");
      return platformApi.upsertBillingPlan({
        code: starter.code,
        name: starter.name,
        description: starter.description,
        currency: starter.currency,
        billing_interval: starter.billing_interval,
        unit_amount_satang: parsed === null ? null : Math.round(parsed * 100),
        feature_flags: starter.feature_flags,
        plan_limits: starter.plan_limits,
        is_public: isPublic,
        is_active: starter.is_active,
        reason,
      });
    },
    onSuccess: async () => {
      setReason("");
      await queryClient.invalidateQueries({ queryKey: ["platform", "billing"] });
    },
  });

  if (overview.isLoading) return <p className="text-slate-400">กำลังโหลด Billing...</p>;
  if (overview.error || !overview.data) return <p className="text-red-300">{platformErrorMessage(overview.error)}</p>;
  const data = overview.data;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-300">SaaS Commercial Control</p>
        <h2 className="mt-2 text-3xl font-bold">Plan และ Billing</h2>
        <p className="mt-2 text-sm text-slate-400">หน่วยเงินเป็นสตางค์ในระบบ และทุกการแก้ไขมี Audit Log</p>
      </div>

      <section className="rounded-2xl border border-amber-800 bg-amber-950/30 p-5 text-amber-100">
        <div className="flex gap-3"><AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" /><div><p className="font-semibold">ยังไม่เปิดรับเงินจริง</p><p className="mt-1 text-sm">Provider: {data.provider} · Live charging: {data.live_charging_enabled ? "enabled" : "disabled"} การเชื่อม checkout, บัตร และ webhook ต้องรออนุมัติ Scope ผู้ให้บริการแยกต่างหาก</p></div></div>
      </section>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <article className="rounded-xl border border-slate-700 bg-slate-900 p-4"><p className="text-xs text-slate-400">Plans</p><p className="mt-2 text-2xl font-bold">{data.plans.length}</p></article>
        <article className="rounded-xl border border-slate-700 bg-slate-900 p-4"><p className="text-xs text-slate-400">Subscriptions</p><p className="mt-2 text-2xl font-bold">{Object.values(data.subscription_counts).reduce((sum, value) => sum + value, 0)}</p></article>
        <article className="rounded-xl border border-slate-700 bg-slate-900 p-4"><p className="text-xs text-slate-400">Invoices</p><p className="mt-2 text-2xl font-bold">{Object.values(data.invoice_counts).reduce((sum, value) => sum + value, 0)}</p></article>
        <article className="rounded-xl border border-slate-700 bg-slate-900 p-4"><p className="text-xs text-slate-400">Collection</p><p className="mt-2 text-lg font-bold">{data.collection_available ? "พร้อม" : "ปิดไว้"}</p></article>
      </div>

      {starter ? <section className="rounded-2xl border border-slate-700 bg-slate-900 p-6">
        <div className="flex items-center gap-3"><CreditCard className="h-6 w-6 text-emerald-300" /><div><h3 className="text-xl font-semibold">{starter.name}</h3><p className="text-sm text-slate-400">{money(starter.unit_amount_satang, starter.currency)} / {starter.billing_interval}</p></div></div>
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <div className="space-y-2"><Label htmlFor="billing-plan-price" className="text-slate-300">ราคาต่อรอบ (บาท)</Label><Input id="billing-plan-price" type="number" min="0" step="0.01" value={amountBaht} onChange={(event) => setAmountBaht(event.target.value)} placeholder="เว้นว่าง = ยังไม่ตัดสินราคา" /></div>
          <div className="space-y-2"><Label htmlFor="billing-plan-reason" className="text-slate-300">เหตุผล</Label><Input id="billing-plan-reason" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="จำเป็นสำหรับ Audit Log" /></div>
        </div>
        <label className="mt-4 flex items-center gap-3 text-sm"><input type="checkbox" checked={isPublic} onChange={(event) => setIsPublic(event.target.checked)} />แสดง Plan นี้ต่อสาธารณะ</label>
        {save.error ? <p className="mt-4 text-sm text-red-300">{platformErrorMessage(save.error)}</p> : null}
        <Button className="mt-5 bg-emerald-400 text-slate-950 hover:bg-emerald-300" onClick={() => save.mutate()} disabled={save.isPending}><Save className="h-4 w-4" />บันทึก Plan</Button>
      </section> : null}

      <section className="rounded-2xl border border-slate-700 bg-slate-900 p-5 text-sm text-slate-300"><p className="font-semibold">จัดการรายบริษัท</p><p className="mt-1 text-slate-400">เปิด “บริษัทลูกค้า” แล้วเลือก Company เพื่อดูสถานะ subscription และ invoice โดยข้อมูลธุรกิจของ tenant จะไม่ถูกนำมาแสดงใน Billing ส่วนกลาง</p></section>
    </div>
  );
}
