import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeftRight, Boxes, CheckCircle2, PackageCheck, RefreshCw, RotateCcw, Send, Truck } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import { companyDistributionApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth.store";
import type { DistributionModule, DistributionShipment } from "@/types/distribution";

const fieldClass = "mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm";
const today = (): string => new Date().toISOString().slice(0, 10);
const actionKey = (prefix: string): string => `${prefix}-${crypto.randomUUID()}`;
const qty = (value: number | string | null | undefined): string => new Intl.NumberFormat("th-TH", { maximumFractionDigits: 4 }).format(Number(value ?? 0));
const moduleLabel: Record<DistributionModule, string> = { restaurant_pos: "Restaurant POS", takeaway_pos: "Takeaway POS", retail_pos: "Retail POS" };
const statusLabel: Record<string, string> = {
  submitted: "รอจัดสรร", partially_allocated: "จัดสรรบางส่วน", allocated: "จัดสรรแล้ว", fulfilled: "ครบแล้ว", cancelled: "ยกเลิก",
  planned: "เตรียมส่ง", in_transit: "ระหว่างทาง", partially_received: "รับบางส่วน", received: "รับครบ", rejected: "ตีกลับ", partially_returned: "คืนบางส่วน", returned: "คืนแล้ว",
};

function errorMessage(error: unknown): string {
  if (typeof error === "object" && error !== null && "response" in error) {
    return (error as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? "ทำรายการไม่สำเร็จ";
  }
  return error instanceof Error ? error.message : "ทำรายการไม่สำเร็จ";
}

export default function CompanyDistributionPage(): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const dashboardQuery = useQuery({
    queryKey: ["company-distribution", "dashboard"],
    queryFn: async () => (await companyDistributionApi.dashboard()).data.data,
  });
  const dashboard = dashboardQuery.data;
  const enabled = Boolean(dashboard?.write_enabled) && (hasPermission("company.distribution.manage") || hasPermission("system.company.edit"));
  const [dateFrom, setDateFrom] = useState(() => { const day = new Date(); day.setDate(day.getDate() - 6); return day.toISOString().slice(0, 10); });
  const [dateTo, setDateTo] = useState(today());
  const reportQuery = useQuery({
    queryKey: ["company-distribution", "report", dateFrom, dateTo],
    queryFn: async () => (await companyDistributionApi.report(dateFrom, dateTo)).data.data,
    enabled: dateFrom <= dateTo,
  });
  const [demand, setDemand] = useState({ brand_id: "", branch_id: "", product_id: "", needed_on: today(), requested_qty: "" });
  const [plan, setPlan] = useState({ demand_id: "", planned_qty: "" });
  const mutation = useMutation({
    mutationFn: (input: { run: () => Promise<unknown>; message: string }) => input.run(),
    onSuccess: async (_result, input) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["company-distribution", "dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["company-distribution", "report"] }),
      ]);
      toast({ title: input.message });
    },
    onError: (error) => toast({ title: "ทำรายการไม่สำเร็จ", description: errorMessage(error), variant: "destructive" }),
  });
  const save = (message: string, run: () => Promise<unknown>): void => mutation.mutate({ message, run });
  const selectedBrand = dashboard?.setup_options.brands.find((row) => row.id === demand.brand_id);
  const demandBranches = dashboard?.setup_options.brand_branches.filter((row) => row.brand_id === demand.brand_id) ?? [];
  const demandProducts = dashboard?.setup_options.products.filter((row) => row.brand_id === demand.brand_id) ?? [];
  const openDemands = dashboard?.demands.filter((row) => !["fulfilled", "cancelled"].includes(row.status)) ?? [];
  const totals = useMemo(() => {
    const rows = dashboard?.shipments ?? [];
    return rows.reduce((sum, row) => ({
      transit: sum.transit + Number(row.in_transit_qty), received: sum.received + Number(row.net_received_qty),
      rejected: sum.rejected + Number(row.rejected_qty), returned: sum.returned + Number(row.returned_qty),
    }), { transit: 0, received: 0, rejected: 0, returned: 0 });
  }, [dashboard?.shipments]);

  if (dashboardQuery.isLoading) return <div className="rounded-xl bg-white p-8 text-center text-slate-500">กำลังโหลดงานกระจายสินค้า...</div>;
  if (!dashboard) return <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-red-700">โหลดข้อมูลงานกระจายสินค้าไม่สำเร็จ</div>;

  const act = (shipment: DistributionShipment, kind: "dispatch" | "receive" | "reject" | "return" | "cancel"): void => {
    if (kind === "dispatch") save("ส่งสินค้าและตัดคลัง READY แล้ว", () => companyDistributionApi.dispatch(shipment.id, { idempotency_key: actionKey("dispatch") }));
    if (kind === "receive") save("รับสินค้าเข้าคลังสาขาแล้ว", () => companyDistributionApi.receive(shipment.id, { idempotency_key: actionKey("receive"), cumulative_received_qty: Number(shipment.shipped_qty), finalize: true }));
    if (kind === "reject") save("บันทึกปฏิเสธส่วนที่เหลือแล้ว", () => companyDistributionApi.reject(shipment.id, { idempotency_key: actionKey("reject"), reason: "ปฏิเสธจาก Company Admin" }));
    if (kind === "return") save("คืนสินค้าเข้าคลัง READY แล้ว", () => companyDistributionApi.returnGoods(shipment.id, { idempotency_key: actionKey("return"), qty: Number(shipment.net_received_qty), reason: "คืนจากสาขาผ่าน Company Admin" }));
    if (kind === "cancel") save("ยกเลิกรายการเตรียมส่งแล้ว", () => companyDistributionApi.cancel(shipment.id, { idempotency_key: actionKey("cancel"), reason: "ยกเลิกจาก Company Admin" }));
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6" data-testid="company-distribution-page">
      <header className="rounded-2xl bg-slate-950 p-6 text-white shadow-lg">
        <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
          <div><p className="text-xs font-black uppercase tracking-[0.24em] text-cyan-300">Company Admin · Supply Chain</p><h1 className="mt-2 text-3xl font-black">Demand และกระจายสินค้าสำเร็จรูป</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">รวมคำขอจาก 3 POS แต่คงเจ้าของ Brand/Branch ชัดเจน และใช้ใบโอนสินค้าเดิมเป็นยอดสต๊อกจริงเพียงชุดเดียว</p></div>
          <Button variant="outline" className="border-slate-600 bg-slate-900 text-white" onClick={() => void dashboardQuery.refetch()}><RefreshCw className="h-4 w-4" /> โหลดล่าสุด</Button>
        </div>
      </header>
      {!enabled && <div data-testid="company-distribution-dark-launch" className="flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-900"><AlertTriangle className="h-5 w-5 shrink-0" /><div><p className="font-black">พักการส่งผลต่อสต๊อกจริงไว้ก่อน</p><p className="text-sm">ดู Demand, Shipment และ Reconciliation ได้แล้ว แต่ปุ่มสร้าง/ส่ง/รับ/ตีกลับ/คืนจะเปิดหลังผ่าน rollout sign-off</p></div></div>}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[["ระหว่างทาง", totals.transit, Truck], ["รับสุทธิ", totals.received, CheckCircle2], ["ปฏิเสธ", totals.rejected, AlertTriangle], ["คืนครัวกลาง", totals.returned, RotateCcw]].map(([label, value, Icon]) => { const CardIcon = Icon as typeof Truck; return <article key={String(label)} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><CardIcon className="h-5 w-5 text-cyan-700" /><p className="mt-4 text-sm font-semibold text-slate-500">{String(label)}</p><p className="mt-1 text-2xl font-black">{qty(value as number)}</p></article>; })}
      </section>

      <Tabs defaultValue="overview">
        <TabsList className="h-auto flex-wrap"><TabsTrigger value="overview">ภาพรวม</TabsTrigger><TabsTrigger value="demand">Demand</TabsTrigger><TabsTrigger value="shipments">ส่ง–รับ–คืน</TabsTrigger><TabsTrigger value="report">Reconciliation</TabsTrigger></TabsList>
        <TabsContent value="overview" className="space-y-5">
          <section className="overflow-hidden rounded-xl border bg-white"><div className="border-b p-5"><h2 className="font-black">คิว Demand จากทุก POS</h2><p className="text-sm text-slate-500">แยกโมดูล แบรนด์ และสาขาตั้งแต่ต้นทาง</p></div><div className="overflow-x-auto"><table className="w-full min-w-[820px] text-sm"><thead className="bg-slate-50 text-left text-xs uppercase text-slate-500"><tr><th className="px-5 py-3">ระบบ</th><th className="px-5 py-3">แบรนด์ / สาขา</th><th className="px-5 py-3">สินค้า</th><th className="px-5 py-3 text-right">ขอ / จัดสรร / รับสุทธิ</th><th className="px-5 py-3">สถานะ</th></tr></thead><tbody className="divide-y">{dashboard.demands.length ? dashboard.demands.map((row) => <tr key={row.id}><td className="px-5 py-4 font-bold">{moduleLabel[row.source_module]}</td><td className="px-5 py-4"><b>{row.brand_name}</b><p className="text-slate-500">{row.branch_name}</p></td><td className="px-5 py-4">{row.product_name}<p className="text-xs text-slate-500">ต้องการ {row.needed_on}</p></td><td className="px-5 py-4 text-right font-bold">{qty(row.requested_qty)} / {qty(row.allocated_qty)} / {qty(row.net_received_qty)} {row.unit_code}</td><td className="px-5 py-4">{statusLabel[row.status]}</td></tr>) : <tr><td colSpan={5} className="p-10 text-center text-slate-500">ยังไม่มี Demand</td></tr>}</tbody></table></div></section>
        </TabsContent>

        <TabsContent value="demand" className="space-y-5">
          <div className="grid gap-5 lg:grid-cols-2">
            <form className="space-y-4 rounded-xl border bg-white p-5" onSubmit={(event) => { event.preventDefault(); const product = demandProducts.find((row) => row.id === demand.product_id); if (!selectedBrand || !product) return; save("รับ Demand เข้าคิวแล้ว", () => companyDistributionApi.createDemand({ ...demand, source_module: selectedBrand.source_module, requested_qty: Number(demand.requested_qty), unit_code: product.unit_code ?? "ea", source_type: "company_admin_manual", source_id: `manual-${Date.now()}`, idempotency_key: actionKey("demand") })); }}>
              <h2 className="text-lg font-black">1. รับ Demand จาก POS</h2>
              <Label>แบรนด์<select required className={fieldClass} value={demand.brand_id} onChange={(event) => setDemand({ ...demand, brand_id: event.target.value, branch_id: "", product_id: "" })}><option value="">เลือกแบรนด์</option>{dashboard.setup_options.brands.map((row) => <option key={row.id} value={row.id}>{moduleLabel[row.source_module]} · {row.name}</option>)}</select></Label>
              <Label>สาขา<select required className={fieldClass} value={demand.branch_id} onChange={(event) => setDemand({ ...demand, branch_id: event.target.value })}><option value="">เลือกสาขา</option>{demandBranches.map((row) => <option key={row.branch_id} value={row.branch_id}>{row.branch_name}</option>)}</select></Label>
              <Label>สินค้า READY<select required className={fieldClass} value={demand.product_id} onChange={(event) => setDemand({ ...demand, product_id: event.target.value })}><option value="">เลือกสินค้า</option>{demandProducts.map((row) => <option key={row.id} value={row.id}>{row.name} · พร้อมส่ง {qty(row.available_qty)} {row.unit_code}</option>)}</select></Label>
              <div className="grid grid-cols-2 gap-3"><Label>วันที่ต้องการ<Input type="date" required value={demand.needed_on} onChange={(event) => setDemand({ ...demand, needed_on: event.target.value })} /></Label><Label>จำนวน<Input type="number" min="0.0001" step="0.0001" required value={demand.requested_qty} onChange={(event) => setDemand({ ...demand, requested_qty: event.target.value })} /></Label></div>
              <Button disabled={!enabled || mutation.isPending}><Boxes className="h-4 w-4" /> ส่ง Demand</Button>
            </form>
            <form className="space-y-4 rounded-xl border bg-white p-5" onSubmit={(event) => { event.preventDefault(); save("จัดสรรสินค้าและสร้างใบโอนแล้ว", () => companyDistributionApi.planShipment({ demand_id: plan.demand_id, planned_qty: Number(plan.planned_qty), idempotency_key: actionKey("plan") })); }}>
              <h2 className="text-lg font-black">2. จัดสรรจาก Brand READY</h2>
              <Label>Demand<select required className={fieldClass} value={plan.demand_id} onChange={(event) => { const row = openDemands.find((item) => item.id === event.target.value); setPlan({ demand_id: event.target.value, planned_qty: row ? String(Number(row.requested_qty) - Number(row.allocated_qty)) : "" }); }}><option value="">เลือก Demand</option>{openDemands.map((row) => <option key={row.id} value={row.id}>{moduleLabel[row.source_module]} · {row.brand_name} → {row.branch_name} · เหลือ {qty(Number(row.requested_qty) - Number(row.allocated_qty))}</option>)}</select></Label>
              <Label>จำนวนจัดสรร<Input type="number" min="0.0001" step="0.0001" required value={plan.planned_qty} onChange={(event) => setPlan({ ...plan, planned_qty: event.target.value })} /></Label>
              <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-600">ระบบจะสร้างและอนุมัติใบโอนเดิมเพื่อจองสต๊อก แต่ยังไม่ตัด READY จนกด “ส่งสินค้า”</p>
              <Button disabled={!enabled || mutation.isPending}><ArrowLeftRight className="h-4 w-4" /> สร้าง Shipment</Button>
            </form>
          </div>
        </TabsContent>

        <TabsContent value="shipments" className="space-y-4">
          {dashboard.shipments.length ? dashboard.shipments.map((row) => <article key={row.id} className="rounded-xl border bg-white p-5"><div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-center"><div><p className="text-xs font-black uppercase tracking-wider text-cyan-700">{moduleLabel[row.source_module]} · {statusLabel[row.status]}</p><h3 className="mt-1 text-lg font-black">{row.shipment_number} · {row.product_name}</h3><p className="text-sm text-slate-500">{row.brand_name} → {row.branch_name} · ใบโอน {row.transfer_number}</p><p className="mt-2 text-sm">วางแผน {qty(row.planned_qty)} · ส่ง {qty(row.shipped_qty)} · รับ {qty(row.received_qty)} · ปฏิเสธ {qty(row.rejected_qty)} · คืน {qty(row.returned_qty)} {row.unit_code}</p>{row.events.length > 0 && <p className="mt-2 text-xs text-slate-500">เหตุการณ์ล่าสุด: {row.events.slice(-4).map((event) => `${statusLabel[event.event_type] ?? event.event_type} ${qty(event.qty)}`).join(" · ")}</p>}</div><div className="flex flex-wrap gap-2">{row.status === "planned" && <><Button disabled={!enabled || mutation.isPending} onClick={() => act(row, "dispatch")}><Send className="h-4 w-4" /> ส่งสินค้า</Button><Button variant="outline" disabled={!enabled || mutation.isPending} onClick={() => act(row, "cancel")}>ยกเลิก</Button></>}{["in_transit", "partially_received"].includes(row.status) && <><Button disabled={!enabled || mutation.isPending} onClick={() => act(row, "receive")}><PackageCheck className="h-4 w-4" /> รับครบ</Button><Button variant="outline" disabled={!enabled || mutation.isPending} onClick={() => act(row, "reject")}><AlertTriangle className="h-4 w-4" /> ปฏิเสธส่วนที่เหลือ</Button></>}{["received", "rejected", "partially_returned"].includes(row.status) && Number(row.net_received_qty) > 0 && <Button variant="outline" disabled={!enabled || mutation.isPending} onClick={() => act(row, "return")}><RotateCcw className="h-4 w-4" /> คืนทั้งหมดที่เหลือ</Button>}</div></div></article>) : <div className="rounded-xl border bg-white p-10 text-center text-slate-500">ยังไม่มี Shipment</div>}
        </TabsContent>

        <TabsContent value="report" className="space-y-5">
          <section className="grid gap-4 rounded-xl border bg-white p-4 md:grid-cols-2"><Label>ตั้งแต่<Input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></Label><Label>ถึง<Input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></Label></section>
          {reportQuery.data && <><section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{[["ส่งแล้ว", reportQuery.data.totals.shipped_qty], ["รับสุทธิ", reportQuery.data.totals.net_received_qty], ["ระหว่างทาง", reportQuery.data.totals.in_transit_qty], ["ปฏิเสธ + คืน", Number(reportQuery.data.totals.rejected_qty) + Number(reportQuery.data.totals.returned_qty)]].map(([label, value]) => <article key={String(label)} className="rounded-xl border bg-white p-5"><p className="text-sm text-slate-500">{String(label)}</p><p className="mt-2 text-2xl font-black">{qty(value as number)}</p></article>)}</section><section className="overflow-hidden rounded-xl border bg-white"><div className="border-b p-5"><h2 className="font-black">ตรวจยอดแยกตามระบบ / แบรนด์ / สาขา</h2></div><div className="overflow-x-auto"><table className="w-full min-w-[850px] text-sm"><thead className="bg-slate-50 text-left text-xs uppercase text-slate-500"><tr><th className="px-5 py-3">ระบบ</th><th className="px-5 py-3">แบรนด์ / สาขา</th><th className="px-5 py-3 text-right">ส่ง</th><th className="px-5 py-3 text-right">รับสุทธิ</th><th className="px-5 py-3 text-right">ระหว่างทาง</th><th className="px-5 py-3 text-right">ปฏิเสธ / คืน</th></tr></thead><tbody className="divide-y">{reportQuery.data.by_workspace.map((row) => <tr key={`${row.source_module}-${row.brand_id}-${row.branch_id}`}><td className="px-5 py-4 font-bold">{moduleLabel[row.source_module]}</td><td className="px-5 py-4"><b>{row.brand_name}</b><p className="text-slate-500">{row.branch_name}</p></td><td className="px-5 py-4 text-right">{qty(row.shipped_qty)}</td><td className="px-5 py-4 text-right font-black">{qty(row.net_received_qty)}</td><td className="px-5 py-4 text-right">{qty(row.in_transit_qty)}</td><td className="px-5 py-4 text-right">{qty(row.rejected_qty)} / {qty(row.returned_qty)}</td></tr>)}</tbody></table></div></section></>}
        </TabsContent>
      </Tabs>
    </div>
  );
}
