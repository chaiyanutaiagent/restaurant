import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Boxes, Factory, PackageCheck, Play, RefreshCw, RotateCcw, Scale, Warehouse } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import { companyKitchenApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth.store";

const fieldClass = "mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm";
const today = (): string => new Date().toISOString().slice(0, 10);
const key = (prefix: string): string => `${prefix}-${crypto.randomUUID()}`;
const number = (value: number | string | null): string => new Intl.NumberFormat("th-TH", { maximumFractionDigits: 4 }).format(Number(value ?? 0));
const money = (value: number | string): string => new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(Number(value));

function errorMessage(error: unknown): string {
  if (typeof error === "object" && error !== null && "response" in error) {
    return (error as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? "บันทึกไม่สำเร็จ";
  }
  return error instanceof Error ? error.message : "บันทึกไม่สำเร็จ";
}

export default function CompanyKitchenPage(): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const dashboardQuery = useQuery({
    queryKey: ["company-kitchen", "dashboard"],
    queryFn: async () => (await companyKitchenApi.dashboard()).data.data,
  });
  const dashboard = dashboardQuery.data;
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const enabled = Boolean(dashboard?.write_enabled) && (
    hasPermission("company.kitchen.manage") || hasPermission("system.company.edit")
  );
  const [dateFrom, setDateFrom] = useState(() => { const value = new Date(); value.setDate(value.getDate() - 6); return value.toISOString().slice(0, 10); });
  const [dateTo, setDateTo] = useState(today());
  const reportQuery = useQuery({
    queryKey: ["company-kitchen", "report", dateFrom, dateTo],
    queryFn: async () => (await companyKitchenApi.report(dateFrom, dateTo)).data.data,
    enabled: dateFrom <= dateTo,
  });
  const [kitchen, setKitchen] = useState({ branch_id: "", raw_location_id: "", name: "ครัวกลาง", timezone: "Asia/Bangkok" });
  const [ingredient, setIngredient] = useState({ canonical_product_id: "", code: "", name: "", base_unit_code: "g", unit_dimension: "mass" });
  const [alias, setAlias] = useState({ ingredient_id: "", brand_id: "", source_product_id: "", source_unit_code: "g", conversion_factor: "1", supplier_sku: "" });
  const [receipt, setReceipt] = useState({ ingredient_id: "", lot_code: "", qty: "", unit_cost: "", expires_on: "" });
  const [demand, setDemand] = useState({ brand_id: "", branch_id: "", output_product_id: "", needed_on: today(), requested_qty: "", unit_code: "ชิ้น" });
  const [order, setOrder] = useState({ demand_id: "", brand_id: "", output_product_id: "", planned_date: today(), planned_qty: "" });

  useEffect(() => {
    if (dashboard?.kitchen) setKitchen({ branch_id: dashboard.kitchen.branch_id, raw_location_id: dashboard.kitchen.raw_location_id, name: dashboard.kitchen.name, timezone: dashboard.kitchen.timezone });
  }, [dashboard?.kitchen]);

  const mutation = useMutation({
    mutationFn: (input: { run: () => Promise<unknown>; message: string }) => input.run(),
    onSuccess: async (_result, input) => {
      await Promise.all([queryClient.invalidateQueries({ queryKey: ["company-kitchen", "dashboard"] }), queryClient.invalidateQueries({ queryKey: ["company-kitchen", "report"] })]);
      toast({ title: input.message });
    },
    onError: (error) => toast({ title: "ทำรายการไม่สำเร็จ", description: errorMessage(error), variant: "destructive" }),
  });
  const totalOnHand = useMemo(
    () => dashboard?.ingredients.reduce((sum, row) => sum + Number(row.qty_on_hand), 0) ?? 0,
    [dashboard?.ingredients],
  );

  if (dashboardQuery.isLoading) return <div className="rounded-xl bg-white p-8 text-center text-slate-500">กำลังโหลดครัวกลาง...</div>;
  if (!dashboard) return <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-red-700">โหลดข้อมูลครัวกลางไม่สำเร็จ</div>;

  const options = dashboard.setup_options;
  const rawProducts = options.products.filter((row) => row.inventory_role === "central_raw" && row.brand_id === null);
  const aliasProducts = options.products.filter((row) => row.inventory_role === "central_raw" && (row.brand_id === null || row.brand_id === alias.brand_id));
  const demandProducts = options.products.filter((row) => row.inventory_role === "central_ready" && row.brand_id === demand.brand_id);
  const orderProducts = options.products.filter((row) => row.inventory_role === "central_ready" && row.brand_id === order.brand_id);
  const demandBranches = options.branches.filter((branch) =>
    options.brand_branches.some((mapping) =>
      mapping.brand_id === demand.brand_id && mapping.branch_id === branch.id
    )
  );
  const openDemands = dashboard.demands.filter((row) => row.status === "submitted");
  const activeOrders = dashboard.orders.filter((row) => ["planned", "in_progress"].includes(row.status));
  const save = (message: string, run: () => Promise<unknown>): void => mutation.mutate({ message, run });

  return (
    <div className="mx-auto max-w-7xl space-y-6" data-testid="company-kitchen-page">
      <header className="rounded-2xl bg-slate-950 p-6 text-white shadow-lg">
        <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end"><div><p className="text-xs font-black uppercase tracking-[0.24em] text-emerald-300">Company Admin · Central Kitchen</p><h1 className="mt-2 text-3xl font-black">ครัวกลางและวัตถุดิบร่วม</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">วัตถุดิบหนึ่งกองใช้ได้หลายแบรนด์ แต่สูตร ใบผลิต ผลผลิต ต้นทุน และรายงานยังแยกเจ้าของชัดเจน</p></div><Button variant="outline" className="border-slate-600 bg-slate-900 text-white" onClick={() => void dashboardQuery.refetch()}><RefreshCw className="h-4 w-4" /> โหลดล่าสุด</Button></div>
      </header>
      {!enabled && <div data-testid="company-kitchen-dark-launch" className="flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-900"><AlertTriangle className="h-5 w-5 shrink-0" /><div><p className="font-black">พักการตัดสต๊อกจริงไว้ก่อน</p><p className="text-sm">หน้าและรายงานพร้อมแล้ว ปุ่มบันทึกจะเปิดหลังผ่านการทดสอบและอนุมัติ rollout</p></div></div>}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["สถานะครัว", dashboard.kitchen ? "ตั้งค่าแล้ว" : "รอตั้งค่า", Factory],
          ["วัตถุดิบกลาง", `${dashboard.ingredients.length} รายการ`, Boxes],
          ["ยอดรวมทุก Lot", number(totalOnHand), Scale],
          ["ใบผลิตรอดำเนินการ", `${activeOrders.length} ใบ`, PackageCheck],
        ].map(([label, value, Icon]) => { const CardIcon = Icon as typeof Factory; return <article key={String(label)} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><CardIcon className="h-5 w-5 text-emerald-600" /><p className="mt-4 text-sm font-semibold text-slate-500">{String(label)}</p><p className="mt-1 text-2xl font-black">{String(value)}</p></article>; })}
      </section>

      <Tabs defaultValue="overview">
        <TabsList className="h-auto flex-wrap"><TabsTrigger value="overview">ภาพรวม</TabsTrigger><TabsTrigger value="setup">ตั้งค่าและ Mapping</TabsTrigger><TabsTrigger value="production">Demand และผลิต</TabsTrigger><TabsTrigger value="report">รายงาน</TabsTrigger></TabsList>
        <TabsContent value="overview" className="space-y-5">
          <section className="overflow-hidden rounded-xl border border-slate-200 bg-white"><div className="border-b p-5"><h2 className="font-black">สต๊อกวัตถุดิบกลาง</h2><p className="text-sm text-slate-500">รวมทุก lot ในหน่วยกลาง</p></div><div className="overflow-x-auto"><table className="w-full min-w-[620px] text-sm"><thead className="bg-slate-50 text-left text-xs uppercase text-slate-500"><tr><th className="px-5 py-3">รหัส</th><th className="px-5 py-3">วัตถุดิบ</th><th className="px-5 py-3">มิติ</th><th className="px-5 py-3 text-right">คงเหลือ</th></tr></thead><tbody className="divide-y">{dashboard.ingredients.length ? dashboard.ingredients.map((row) => <tr key={row.id}><td className="px-5 py-4 font-mono text-xs">{row.code}</td><td className="px-5 py-4 font-bold">{row.name}</td><td className="px-5 py-4 text-slate-500">{row.unit_dimension}</td><td className="px-5 py-4 text-right font-black">{number(row.qty_on_hand)} {row.base_unit_code}</td></tr>) : <tr><td colSpan={4} className="p-10 text-center text-slate-500">ยังไม่มีวัตถุดิบกลาง</td></tr>}</tbody></table></div></section>
          <section className="rounded-xl border border-slate-200 bg-white"><div className="border-b p-5"><h2 className="font-black">ใบผลิตล่าสุด</h2><p className="text-sm text-slate-500">ผลผลิตยังแยกคลัง READY ตามแบรนด์</p></div><div className="divide-y">{dashboard.orders.length ? dashboard.orders.slice(0, 10).map((row) => <div key={row.id} className="flex justify-between p-5"><div><p className="font-black">{row.order_number} · {row.output_product_name}</p><p className="text-sm text-slate-500">{row.brand_name} · {row.planned_date} · {row.status}</p></div><p className="font-black">{number(row.actual_output_qty ?? row.planned_qty)} {row.output_unit_code}</p></div>) : <p className="p-10 text-center text-slate-500">ยังไม่มีใบผลิต</p>}</div></section>
        </TabsContent>

        <TabsContent value="setup" className="space-y-5">
          <div className="grid gap-5 lg:grid-cols-2">
            <form className="space-y-4 rounded-xl border bg-white p-5" onSubmit={(e) => { e.preventDefault(); save("บันทึกครัวกลางแล้ว", () => companyKitchenApi.configure(kitchen)); }}><h2 className="text-lg font-black">1. ตั้งค่าคลังครัวกลาง</h2><Label>สาขา<select required className={fieldClass} value={kitchen.branch_id} onChange={(e) => setKitchen({ ...kitchen, branch_id: e.target.value, raw_location_id: "" })}><option value="">เลือกสาขา</option>{options.branches.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></Label><Label>คลัง RAW กลาง<select required className={fieldClass} value={kitchen.raw_location_id} onChange={(e) => setKitchen({ ...kitchen, raw_location_id: e.target.value })}><option value="">เลือกคลัง</option>{options.locations.filter((row) => row.branch_id === kitchen.branch_id).map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></Label><Label>ชื่อครัว<Input required value={kitchen.name} onChange={(e) => setKitchen({ ...kitchen, name: e.target.value })} /></Label><Button disabled={!enabled || mutation.isPending}><Warehouse className="h-4 w-4" /> บันทึก</Button></form>
            <form className="space-y-4 rounded-xl border bg-white p-5" onSubmit={(e) => { e.preventDefault(); save("สร้างวัตถุดิบกลางแล้ว", () => companyKitchenApi.createIngredient(ingredient)); }}><h2 className="text-lg font-black">2. สร้างรหัสวัตถุดิบกลาง</h2><Label>สินค้า Company<select required className={fieldClass} value={ingredient.canonical_product_id} onChange={(e) => { const product = rawProducts.find((row) => row.id === e.target.value); setIngredient({ ...ingredient, canonical_product_id: e.target.value, name: product?.name ?? "", code: product?.sku ?? "", base_unit_code: product?.unit_code ?? "g" }); }}><option value="">เลือก central_raw ที่ไม่ผูกแบรนด์</option>{rawProducts.map((row) => <option key={row.id} value={row.id}>{row.name} · {row.sku}</option>)}</select></Label><div className="grid grid-cols-2 gap-3"><Label>รหัส<Input required value={ingredient.code} onChange={(e) => setIngredient({ ...ingredient, code: e.target.value })} /></Label><Label>ชื่อ<Input required value={ingredient.name} onChange={(e) => setIngredient({ ...ingredient, name: e.target.value })} /></Label></div><div className="grid grid-cols-2 gap-3"><Label>หน่วยกลาง<Input required value={ingredient.base_unit_code} onChange={(e) => setIngredient({ ...ingredient, base_unit_code: e.target.value })} /></Label><Label>มิติ<select className={fieldClass} value={ingredient.unit_dimension} onChange={(e) => setIngredient({ ...ingredient, unit_dimension: e.target.value })}><option value="mass">น้ำหนัก</option><option value="volume">ปริมาตร</option><option value="count">จำนวน</option></select></Label></div><Button disabled={!enabled || mutation.isPending}><Boxes className="h-4 w-4" /> สร้าง</Button></form>
            <form className="space-y-4 rounded-xl border bg-white p-5" onSubmit={(e) => { e.preventDefault(); save("เชื่อมสูตรแบรนด์แล้ว", () => companyKitchenApi.createAlias({ ...alias, conversion_factor: Number(alias.conversion_factor) })); }}><h2 className="text-lg font-black">3. เชื่อมสูตรแบรนด์</h2><Label>วัตถุดิบกลาง<select required className={fieldClass} value={alias.ingredient_id} onChange={(e) => setAlias({ ...alias, ingredient_id: e.target.value })}><option value="">เลือกวัตถุดิบ</option>{dashboard.ingredients.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></Label><Label>แบรนด์<select required className={fieldClass} value={alias.brand_id} onChange={(e) => setAlias({ ...alias, brand_id: e.target.value, source_product_id: "" })}><option value="">เลือกแบรนด์</option>{options.brands.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></Label><Label>สินค้าในสูตร<select required className={fieldClass} value={alias.source_product_id} onChange={(e) => { const product = aliasProducts.find((row) => row.id === e.target.value); setAlias({ ...alias, source_product_id: e.target.value, source_unit_code: product?.unit_code ?? alias.source_unit_code }); }}><option value="">เลือกสินค้า</option>{aliasProducts.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></Label><div className="grid grid-cols-2 gap-3"><Label>หน่วยต้นทาง<Input value={alias.source_unit_code} onChange={(e) => setAlias({ ...alias, source_unit_code: e.target.value })} /></Label><Label>ตัวคูณ<Input type="number" step="0.00000001" min="0.00000001" value={alias.conversion_factor} onChange={(e) => setAlias({ ...alias, conversion_factor: e.target.value })} /></Label></div><Button disabled={!enabled || mutation.isPending}>บันทึก Mapping</Button></form>
            <form className="space-y-4 rounded-xl border bg-white p-5" onSubmit={(e) => { e.preventDefault(); save("รับวัตถุดิบเข้า Lot แล้ว", () => companyKitchenApi.receive({ ...receipt, qty: Number(receipt.qty), unit_cost: Number(receipt.unit_cost), expires_on: receipt.expires_on || null, idempotency_key: key("receipt"), reference_type: "manual_goods_receipt", reference_id: receipt.lot_code })); }}><h2 className="text-lg font-black">4. รับเข้า Lot</h2><Label>วัตถุดิบ<select required className={fieldClass} value={receipt.ingredient_id} onChange={(e) => setReceipt({ ...receipt, ingredient_id: e.target.value })}><option value="">เลือกวัตถุดิบ</option>{dashboard.ingredients.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></Label><div className="grid grid-cols-2 gap-3"><Label>เลข Lot<Input required value={receipt.lot_code} onChange={(e) => setReceipt({ ...receipt, lot_code: e.target.value })} /></Label><Label>หมดอายุ<Input type="date" value={receipt.expires_on} onChange={(e) => setReceipt({ ...receipt, expires_on: e.target.value })} /></Label></div><div className="grid grid-cols-2 gap-3"><Label>จำนวน<Input required type="number" min="0.0001" step="0.0001" value={receipt.qty} onChange={(e) => setReceipt({ ...receipt, qty: e.target.value })} /></Label><Label>ต้นทุน/หน่วย<Input required type="number" min="0" step="0.0001" value={receipt.unit_cost} onChange={(e) => setReceipt({ ...receipt, unit_cost: e.target.value })} /></Label></div><Button disabled={!enabled || mutation.isPending || !dashboard.kitchen}>รับเข้าครัว</Button></form>
          </div>
          <section className="rounded-xl border bg-white p-5"><h2 className="font-black">Mapping ปัจจุบัน</h2><div className="mt-4 grid gap-3 md:grid-cols-2">{dashboard.aliases.map((row) => <div key={row.id} className="rounded-lg border p-4"><p className="font-black">{row.ingredient_name}</p><p className="text-sm text-slate-500">{row.brand_name}: {row.source_product_name} · ×{String(row.conversion_factor)}</p></div>)}</div></section>
        </TabsContent>

        <TabsContent value="production" className="space-y-5">
          <div className="grid gap-5 lg:grid-cols-2">
            <form className="space-y-4 rounded-xl border bg-white p-5" onSubmit={(e) => { e.preventDefault(); save("ส่ง Demand แล้ว", () => companyKitchenApi.createDemand({ ...demand, requested_qty: Number(demand.requested_qty), source_type: "manual_branch_demand", source_id: `manual-${Date.now()}`, idempotency_key: key("demand") })); }}><h2 className="text-lg font-black">1. Demand จากสาขา</h2><Label>แบรนด์<select required className={fieldClass} value={demand.brand_id} onChange={(e) => setDemand({ ...demand, brand_id: e.target.value, branch_id: "", output_product_id: "" })}><option value="">เลือกแบรนด์</option>{options.brands.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></Label><Label>สาขา<select required className={fieldClass} value={demand.branch_id} onChange={(e) => setDemand({ ...demand, branch_id: e.target.value })}><option value="">เลือกสาขา</option>{demandBranches.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></Label><Label>สินค้าสำเร็จรูป<select required className={fieldClass} value={demand.output_product_id} onChange={(e) => { const product = demandProducts.find((row) => row.id === e.target.value); setDemand({ ...demand, output_product_id: e.target.value, unit_code: product?.unit_code ?? demand.unit_code }); }}><option value="">เลือกสินค้า</option>{demandProducts.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></Label><div className="grid grid-cols-2 gap-3"><Label>วันที่ต้องการ<Input type="date" value={demand.needed_on} onChange={(e) => setDemand({ ...demand, needed_on: e.target.value })} /></Label><Label>จำนวน<Input required type="number" min="0.0001" step="0.0001" value={demand.requested_qty} onChange={(e) => setDemand({ ...demand, requested_qty: e.target.value })} /></Label></div><Button disabled={!enabled || mutation.isPending}>ส่ง Demand</Button></form>
            <form className="space-y-4 rounded-xl border bg-white p-5" onSubmit={(e) => { e.preventDefault(); save("สร้างใบผลิตแล้ว", () => companyKitchenApi.createOrder({ ...order, demand_id: order.demand_id || null, planned_qty: Number(order.planned_qty), idempotency_key: key("order") })); }}><h2 className="text-lg font-black">2. สร้างใบผลิตจากสูตร</h2><Label>Demand<select className={fieldClass} value={order.demand_id} onChange={(e) => { const row = openDemands.find((item) => item.id === e.target.value); setOrder(row ? { demand_id: row.id, brand_id: row.brand_id, output_product_id: row.output_product_id, planned_date: row.needed_on, planned_qty: String(row.requested_qty) } : { ...order, demand_id: "" }); }}><option value="">ไม่ผูก Demand</option>{openDemands.map((row) => <option key={row.id} value={row.id}>{row.brand_name} · {row.output_product_name} · {number(row.requested_qty)}</option>)}</select></Label><Label>แบรนด์<select required className={fieldClass} value={order.brand_id} onChange={(e) => setOrder({ ...order, brand_id: e.target.value, output_product_id: "" })}><option value="">เลือกแบรนด์</option>{options.brands.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></Label><Label>สินค้า<select required className={fieldClass} value={order.output_product_id} onChange={(e) => setOrder({ ...order, output_product_id: e.target.value })}><option value="">เลือกสินค้า</option>{orderProducts.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></Label><div className="grid grid-cols-2 gap-3"><Label>วันผลิต<Input type="date" value={order.planned_date} onChange={(e) => setOrder({ ...order, planned_date: e.target.value })} /></Label><Label>จำนวน<Input required type="number" min="0.0001" step="0.0001" value={order.planned_qty} onChange={(e) => setOrder({ ...order, planned_qty: e.target.value })} /></Label></div><Button disabled={!enabled || mutation.isPending || !dashboard.kitchen}><Factory className="h-4 w-4" /> สร้างใบผลิต</Button></form>
          </div>
          <section className="rounded-xl border bg-white"><div className="border-b p-5"><h2 className="font-black">คิวใบผลิต</h2><p className="text-sm text-slate-500">ตัด FIFO จากกองกลาง รับผลผลิตเข้า READY ของแบรนด์</p></div><div className="divide-y">{dashboard.orders.length ? dashboard.orders.map((row) => <div key={row.id} className="flex flex-col justify-between gap-3 p-5 lg:flex-row lg:items-center"><div><p className="font-black">{row.order_number} · {row.output_product_name}</p><p className="text-sm text-slate-500">{row.brand_name} · {number(row.planned_qty)} {row.output_unit_code} · {row.status}</p><p className="mt-1 text-xs text-slate-500">{row.inputs.map((item) => `${item.ingredient_name} ${number(item.actual_qty ?? item.planned_qty)} ${item.base_unit_code}`).join(" · ")}</p></div><div className="flex gap-2">{row.status === "planned" && <Button size="sm" disabled={!enabled || mutation.isPending} onClick={() => save("เริ่มผลิตแล้ว", () => companyKitchenApi.startOrder(row.id))}><Play className="h-4 w-4" /> เริ่ม</Button>}{row.status === "in_progress" && <Button size="sm" disabled={!enabled || mutation.isPending} onClick={() => save("ยืนยันผลิตและตัดสต๊อกแล้ว", () => companyKitchenApi.completeOrder(row.id, { completion_key: key("complete"), actual_output_qty: Number(row.planned_qty), waste_qty: 0, inputs: [] }))}><PackageCheck className="h-4 w-4" /> ผลิตเสร็จ</Button>}{row.status === "completed" && <Button size="sm" variant="outline" disabled={!enabled || mutation.isPending} onClick={() => save("ย้อนใบผลิตแล้ว", () => companyKitchenApi.reverseOrder(row.id, { reversal_key: key("reverse"), reason: "ย้อนรายการจาก Company Admin" }))}><RotateCcw className="h-4 w-4" /> ย้อน</Button>}</div></div>) : <p className="p-10 text-center text-slate-500">ยังไม่มีใบผลิต</p>}</div></section>
        </TabsContent>

        <TabsContent value="report" className="space-y-5">
          <section className="grid gap-4 rounded-xl border bg-white p-4 md:grid-cols-2"><Label>ตั้งแต่<Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></Label><Label>ถึง<Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></Label></section>
          {reportQuery.data && <><section className="grid gap-4 lg:grid-cols-3">{reportQuery.data.production_by_brand.map((row) => <article key={row.brand_id} className="rounded-xl border bg-white p-5"><p className="text-sm text-slate-500">แบรนด์</p><h3 className="text-xl font-black">{row.brand_name}</h3><div className="mt-4 grid grid-cols-2 gap-3 text-sm"><span>ใบผลิต <b>{row.completed_count}/{row.order_count}</b></span><span>ต้นทุน <b>{money(row.input_cost)}</b></span><span>ผลผลิต <b>{number(row.output_qty)}</b></span><span>สูญเสีย <b>{number(row.waste_qty)}</b></span></div></article>)}</section><section className="overflow-hidden rounded-xl border bg-white"><div className="border-b p-5"><h2 className="font-black">การใช้วัตถุดิบแยกแบรนด์</h2></div><div className="overflow-x-auto"><table className="w-full min-w-[700px] text-sm"><thead className="bg-slate-50 text-left text-xs uppercase text-slate-500"><tr><th className="px-5 py-3">แบรนด์</th><th className="px-5 py-3">วัตถุดิบ</th><th className="px-5 py-3 text-right">ใช้</th><th className="px-5 py-3 text-right">ย้อน</th><th className="px-5 py-3 text-right">ต้นทุนสุทธิ</th></tr></thead><tbody className="divide-y">{reportQuery.data.ingredient_usage.map((row) => <tr key={`${row.brand_id}-${row.ingredient_id}`}><td className="px-5 py-4 font-bold">{row.brand_name}</td><td className="px-5 py-4">{row.ingredient_name}</td><td className="px-5 py-4 text-right">{number(row.consumed_qty)} {row.unit_code}</td><td className="px-5 py-4 text-right">{number(row.reversed_qty)}</td><td className="px-5 py-4 text-right font-black">{money(row.net_cost)}</td></tr>)}</tbody></table></div></section></>}
        </TabsContent>
      </Tabs>
    </div>
  );
}
