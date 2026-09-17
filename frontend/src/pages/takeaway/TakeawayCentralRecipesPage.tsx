import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Calculator, Loader2, PackagePlus, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { useToast } from "@/components/ui/use-toast";
import { takeawayApi, type TakeawayRecord } from "@/lib/takeawayApi";

function text(value: unknown, fallback = "-"): string {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

export default function TakeawayCentralRecipesPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [form, setForm] = useState({
    name: "",
    output_item_id: "",
    ingredient_item_id: "",
    ingredient_qty: "1",
    yield_qty: "1",
    yield_unit: "ชิ้น",
    loss_percent: "0",
    branch_id: "",
    pack_size: "1",
    safety_stock_qty: "0",
    minimum_order_qty: "0",
    lead_time_days: "1",
  });
  const contextQuery = useQuery({
    queryKey: ["takeaway", "status"],
    queryFn: async () => (await takeawayApi.status()).data.data,
  });
  const context = contextQuery.data;
  const catalogQuery = useQuery({
    queryKey: ["takeaway", "recipe-catalog", context?.brand_id],
    queryFn: async () => (await takeawayApi.catalog(context!.brand_id!)).data.data,
    enabled: Boolean(context?.brand_id),
  });
  const recipesQuery = useQuery({
    queryKey: ["takeaway", "recipes", context?.brand_id],
    queryFn: async () => (await takeawayApi.recipes({ brand_id: context!.brand_id! })).data.data,
    enabled: Boolean(context?.brand_id),
  });
  const policiesQuery = useQuery({
    queryKey: ["takeaway", "replenishment-policies", form.branch_id],
    queryFn: async () => (await takeawayApi.replenishmentPolicies({ brand_id: context!.brand_id!, branch_id: form.branch_id })).data.data,
    enabled: Boolean(context?.brand_id && form.branch_id),
  });
  const catalog = catalogQuery.data ?? [];
  const itemById = useMemo(
    () => new Map(catalog.map((row) => [row.item.id, row.item])),
    [catalog],
  );
  const recipeMutation = useMutation({
    mutationFn: async () => {
      if (!context?.brand_id || !form.output_item_id || !form.ingredient_item_id) throw new Error("กรุณาเลือกสินค้าผลิตและวัตถุดิบ");
      const ingredient = itemById.get(form.ingredient_item_id);
      return takeawayApi.createRecipe({
        brand_id: context.brand_id,
        output_item_id: form.output_item_id,
        recipe_type: "production",
        name: form.name || `สูตร ${text(itemById.get(form.output_item_id)?.name)}`,
        yield_qty: form.yield_qty,
        yield_unit: form.yield_unit,
        loss_percent: form.loss_percent,
        ingredients: [{
          item_id: form.ingredient_item_id,
          sku: text(ingredient?.sku, form.ingredient_item_id),
          quantity: form.ingredient_qty,
          unit: text(ingredient?.unit, "ชิ้น"),
          sort_order: 0,
        }],
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["takeaway", "recipes"] });
      toast({ title: "สร้างสูตรเวอร์ชันใหม่แล้ว" });
    },
    onError: (error) => toast({ title: "สร้างสูตรไม่สำเร็จ", description: error instanceof Error ? error.message : "ตรวจข้อมูลสูตร", variant: "destructive" }),
  });
  const policyMutation = useMutation({
    mutationFn: async () => {
      if (!context?.brand_id || !form.branch_id || !form.output_item_id) throw new Error("กรุณาระบุสาขาและสินค้า");
      return takeawayApi.setReplenishmentPolicy({
        brand_id: context.brand_id,
        branch_id: form.branch_id,
        item_id: form.output_item_id,
        safety_stock_percent: "0",
        safety_stock_qty: form.safety_stock_qty,
        pack_size: form.pack_size,
        lead_time_days: Number(form.lead_time_days),
        forecast_method: "auto",
        minimum_order_qty: form.minimum_order_qty,
        is_enabled: true,
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["takeaway", "replenishment-policies"] });
      toast({ title: "บันทึกกติกาเติมสินค้าแล้ว" });
    },
    onError: (error) => toast({ title: "บันทึกไม่สำเร็จ", description: error instanceof Error ? error.message : "ตรวจข้อมูล", variant: "destructive" }),
  });
  const set = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const inputClass = "mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";
  const loading = contextQuery.isLoading || catalogQuery.isLoading || recipesQuery.isLoading;

  return <div className="space-y-5">
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div><p className="text-xs font-bold uppercase tracking-[0.22em] text-emerald-700">central workspace</p><h1 className="mt-1 text-2xl font-black">สูตรและการเติมสินค้า</h1><p className="mt-1 text-sm text-slate-500">สูตรแบบมีเวอร์ชัน ตรวจสูตรวนซ้ำ คำนวณต้นทุน และกำหนด safety stock รายสาขา</p></div>
      <button onClick={() => void recipesQuery.refetch()} className="flex items-center gap-2 rounded-xl border bg-white px-4 py-2 text-sm font-bold"><RefreshCw className="h-4 w-4" /> รีเฟรช</button>
    </div>
    <div className="grid gap-4 xl:grid-cols-2">
      <section className="rounded-2xl border bg-white p-5 shadow-sm">
        <h2 className="flex items-center gap-2 font-black"><Calculator className="h-5 w-5 text-emerald-600" /> สร้างสูตรเวอร์ชันใหม่</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="text-xs font-bold text-slate-600">ชื่อสูตร<input className={inputClass} value={form.name} onChange={(event) => set("name", event.target.value)} /></label>
          <label className="text-xs font-bold text-slate-600">สินค้าผลิต<select className={inputClass} value={form.output_item_id} onChange={(event) => set("output_item_id", event.target.value)}><option value="">เลือกสินค้า</option>{catalog.map((row) => <option key={row.item.id} value={row.item.id}>{row.item.name}</option>)}</select></label>
          <label className="text-xs font-bold text-slate-600">วัตถุดิบ<select className={inputClass} value={form.ingredient_item_id} onChange={(event) => set("ingredient_item_id", event.target.value)}><option value="">เลือกวัตถุดิบ</option>{catalog.map((row) => <option key={row.item.id} value={row.item.id}>{row.item.name}</option>)}</select></label>
          <label className="text-xs font-bold text-slate-600">จำนวนวัตถุดิบ<input type="number" min="0.0001" step="0.0001" className={inputClass} value={form.ingredient_qty} onChange={(event) => set("ingredient_qty", event.target.value)} /></label>
          <label className="text-xs font-bold text-slate-600">ผลผลิต<input type="number" min="0.0001" step="0.0001" className={inputClass} value={form.yield_qty} onChange={(event) => set("yield_qty", event.target.value)} /></label>
          <label className="text-xs font-bold text-slate-600">หน่วยผลผลิต<input className={inputClass} value={form.yield_unit} onChange={(event) => set("yield_unit", event.target.value)} /></label>
          <label className="text-xs font-bold text-slate-600">สูญเสีย %<input type="number" min="0" max="99.99" step="0.01" className={inputClass} value={form.loss_percent} onChange={(event) => set("loss_percent", event.target.value)} /></label>
        </div>
        <button disabled={recipeMutation.isPending} onClick={() => recipeMutation.mutate()} className="mt-4 flex items-center gap-2 rounded-xl bg-slate-950 px-5 py-3 font-bold text-white disabled:opacity-50">{recipeMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <PackagePlus className="h-4 w-4" />} บันทึกสูตร</button>
      </section>
      <section className="rounded-2xl border bg-white p-5 shadow-sm">
        <h2 className="font-black">กติกาเติมสินค้ารายสาขา</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="text-xs font-bold text-slate-600">รหัสสาขา<input className={inputClass} value={form.branch_id} onChange={(event) => set("branch_id", event.target.value)} placeholder="เลือกจาก workspace หรือวางรหัสสาขา" /></label>
          <label className="text-xs font-bold text-slate-600">Pack size<input type="number" min="0.0001" step="0.0001" className={inputClass} value={form.pack_size} onChange={(event) => set("pack_size", event.target.value)} /></label>
          <label className="text-xs font-bold text-slate-600">Safety stock<input type="number" min="0" step="0.0001" className={inputClass} value={form.safety_stock_qty} onChange={(event) => set("safety_stock_qty", event.target.value)} /></label>
          <label className="text-xs font-bold text-slate-600">ขั้นต่ำต่อครั้ง<input type="number" min="0" step="0.0001" className={inputClass} value={form.minimum_order_qty} onChange={(event) => set("minimum_order_qty", event.target.value)} /></label>
          <label className="text-xs font-bold text-slate-600">Lead time (วัน)<input type="number" min="0" className={inputClass} value={form.lead_time_days} onChange={(event) => set("lead_time_days", event.target.value)} /></label>
        </div>
        <button disabled={policyMutation.isPending} onClick={() => policyMutation.mutate()} className="mt-4 rounded-xl bg-emerald-500 px-5 py-3 font-black disabled:opacity-50">บันทึกกติกา</button>
        <p className="mt-4 text-xs text-slate-500">กติกาที่โหลด: {policiesQuery.data?.length ?? 0} รายการ</p>
      </section>
    </div>
    <section className="rounded-2xl border bg-white p-5 shadow-sm">
      <h2 className="font-black">สูตรที่ใช้งาน</h2>
      {loading ? <div className="flex justify-center p-10"><Loader2 className="h-7 w-7 animate-spin" /></div> : !(recipesQuery.data ?? []).length ? <p className="mt-4 text-sm text-slate-500">ยังไม่มีสูตร</p> : <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{(recipesQuery.data as TakeawayRecord[]).map((row) => <article key={row.id} className="rounded-xl border border-slate-200 p-4"><p className="font-black">{text(row.name)}</p><p className="mt-1 text-xs text-slate-500">เวอร์ชัน {text(row.version_no)} · ผลผลิต {text(row.yield_qty)} {text(row.yield_unit)}</p><div className="mt-3 flex justify-between text-sm"><span>ต้นทุนวัตถุดิบ</span><strong>฿{text(row.ingredient_cost, "0.0000")}</strong></div><div className="mt-1 flex justify-between text-sm"><span>ต้นทุนต่อผลผลิต</span><strong className="text-emerald-700">฿{text(row.cost_per_yield, "0.0000")}</strong></div></article>)}</div>}
    </section>
  </div>;
}
