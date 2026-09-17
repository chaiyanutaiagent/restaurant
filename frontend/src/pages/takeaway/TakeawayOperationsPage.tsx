import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ClipboardCheck, Loader2, Maximize2, Play, RefreshCw, Search, Volume2, VolumeX } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useToast } from "@/components/ui/use-toast";
import { takeawayApi, type TakeawayRecord } from "@/lib/takeawayApi";
import { useAuthStore } from "@/stores/auth.store";

export type TakeawaySection = "kitchen" | "pickup" | "central" | "production" | "stock" | "transfers" | "credits" | "reports" | "import" | "erp";

const meta: Record<TakeawaySection, { title: string; detail: string }> = {
  kitchen: { title: "คิวครัว", detail: "เปลี่ยนสถานะจากรอทำ เป็นกำลังทำ และพร้อมรับ" },
  pickup: { title: "จุดรับสินค้า", detail: "ตรวจเลขคิวและยืนยันว่าลูกค้ารับสินค้าแล้ว" },
  central: { title: "ออเดอร์ถึงส่วนกลาง", detail: "รองรับรายการประจำ รายการเพิ่ม และสินค้านอกแคตตาล็อก" },
  production: { title: "การผลิต", detail: "ผลิตแยกแบรนด์และตัดวัตถุดิบจากยอดกองกลาง" },
  stock: { title: "สต๊อกร่วม", detail: "ตรวจยอดตามคลัง ล็อต และบันทึกรับเข้า ปรับยอด หรือของเสีย" },
  transfers: { title: "โอนสินค้า", detail: "ส่งจากส่วนกลางไปสาขา พร้อมสถานะส่งและรับ" },
  credits: { title: "วงเงินแฟรนไชส์", detail: "กำหนดเพดานและดูยอดใช้วงเงินแยกสาขา" },
  reports: { title: "รายงาน Takeaway", detail: "ยอดขายแยกจาก Restaurant และ Retail แต่ส่งรวม ERP ได้" },
  import: { title: "นำเข้าข้อมูล Chambo", detail: "ตรวจความครบถ้วนและความปลอดภัยก่อนอนุญาตให้นำเข้า" },
  erp: { title: "เชื่อม ERP กลาง", detail: "ติดตามเหตุการณ์ที่รอส่งและกระทบยอดแบบรันซ้ำได้" },
};

function today(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok" }).format(new Date());
}

function asText(value: unknown, fallback = "-"): string {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function statusClass(value: unknown): string {
  return ["ready", "received", "completed", "processed", "paid", "picked_up"].includes(String(value))
    ? "bg-emerald-100 text-emerald-800"
    : ["rejected", "cancelled", "failed", "refunded"].includes(String(value))
      ? "bg-rose-100 text-rose-800"
      : "bg-amber-100 text-amber-800";
}

function RecordList({ rows, section, onAction, busy, canManageCentral, canAcknowledgeErp }: { rows: TakeawayRecord[]; section: TakeawaySection; onAction: (row: TakeawayRecord, action: string) => void; busy: boolean; canManageCentral: boolean; canAcknowledgeErp: boolean }): JSX.Element {
  if (!rows.length) return <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-slate-500">ยังไม่มีรายการในส่วนนี้</div>;
  return <div className="grid gap-3">{rows.map((row) => {
    const status = row.status ?? row.fulfillment_status;
    const title = row.order_number ?? row.batch_number ?? row.transfer_number ?? row.item_name ?? row.event_type ?? row.name ?? row.id;
    const secondary = row.queue_number ? `คิว ${asText(row.queue_number)}` : row.sku ?? row.location_id ?? row.branch_id ?? row.aggregate_type;
    return <article key={row.id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="min-w-0"><p className="truncate font-black">{asText(title)}</p><p className="mt-1 truncate text-xs text-slate-500">{asText(secondary)} · {asText(row.created_at ?? row.business_date ?? row.planned_at)}</p></div>
      <div className="flex flex-wrap items-center gap-2">{status ? <span className={`rounded-full px-3 py-1 text-xs font-bold ${statusClass(status)}`}>{asText(status)}</span> : null}
        {section === "kitchen" && row.status === "queued" ? <button disabled={busy} onClick={() => onAction(row, "preparing")} className="rounded-xl bg-amber-400 px-3 py-2 text-sm font-bold">เริ่มทำ</button> : null}
        {section === "kitchen" && row.status === "preparing" ? <button disabled={busy} onClick={() => onAction(row, "ready")} className="rounded-xl bg-emerald-500 px-3 py-2 text-sm font-bold">พร้อมรับ</button> : null}
        {section === "pickup" && row.fulfillment_status === "ready" ? <button disabled={busy} onClick={() => onAction(row, "picked_up")} className="rounded-xl bg-emerald-500 px-3 py-2 text-sm font-bold">รับแล้ว</button> : null}
        {section === "central" && canManageCentral && row.status === "submitted" ? <button disabled={busy} onClick={() => onAction(row, "approved")} className="rounded-xl bg-emerald-500 px-3 py-2 text-sm font-bold">อนุมัติ</button> : null}
        {section === "central" && canManageCentral && row.status === "approved" ? <button disabled={busy} onClick={() => onAction(row, "in_production")} className="rounded-xl bg-violet-500 px-3 py-2 text-sm font-bold text-white">ส่งผลิต</button> : null}
        {section === "central" && canManageCentral && row.status === "in_production" ? <button disabled={busy} onClick={() => onAction(row, "packed")} className="rounded-xl bg-sky-500 px-3 py-2 text-sm font-bold text-white">แพ็กแล้ว</button> : null}
        {section === "central" && canManageCentral && row.status === "packed" ? <button disabled={busy} onClick={() => onAction(row, "shipped")} className="rounded-xl bg-slate-900 px-3 py-2 text-sm font-bold text-white">ส่งแล้ว</button> : null}
        {section === "transfers" && row.status === "draft" ? <button disabled={busy} onClick={() => onAction(row, "shipped")} className="rounded-xl bg-slate-900 px-3 py-2 text-sm font-bold text-white">ยืนยันส่ง</button> : null}
        {section === "transfers" && row.status === "shipped" ? <button disabled={busy} onClick={() => onAction(row, "received")} className="rounded-xl bg-emerald-500 px-3 py-2 text-sm font-bold">ยืนยันรับ</button> : null}
        {section === "erp" && canAcknowledgeErp && row.status === "pending" ? <button disabled={busy} onClick={() => onAction(row, "ack")} className="rounded-xl bg-emerald-500 px-3 py-2 text-sm font-bold">ERP รับแล้ว</button> : null}
      </div>
    </article>;
  })}</div>;
}

export default function TakeawayOperationsPage({ section, workspace = "central" }: { section: TakeawaySection; workspace?: "store" | "central" | "admin" }): JSX.Element {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const [fromDate, setFromDate] = useState(today());
  const [toDate, setToDate] = useState(today());
  const [jsonText, setJsonText] = useState('{\n  "manifest": {},\n  "mapping": {},\n  "records": []\n}');
  const [form, setForm] = useState<Record<string, string>>({ quantity: "1", unit: "ชิ้น", round_no: "1", credit_limit: "10000", opening_cash: "0" });
  const [stationFilter, setStationFilter] = useState("");
  const [queueSearch, setQueueSearch] = useState("");
  const [soundEnabled, setSoundEnabled] = useState(false);
  const knownTicketIds = useRef<Set<string>>(new Set());
  const contextQuery = useQuery({ queryKey: ["takeaway", "status"], queryFn: async () => (await takeawayApi.status()).data.data });
  const context = contextQuery.data;
  const query = useQuery({
    queryKey: ["takeaway", section, fromDate, toDate],
    queryFn: async () => {
      if (section === "kitchen") return (await takeawayApi.tickets()).data.data;
      if (section === "pickup") return (await takeawayApi.orders({ fulfillment_status: "ready" })).data.data;
      if (section === "central") return (await takeawayApi.centralOrders()).data.data;
      if (section === "production") return (await takeawayApi.productionBatches()).data.data;
      if (section === "stock") return (await takeawayApi.stock()).data.data;
      if (section === "transfers") return (await takeawayApi.transfers()).data.data;
      if (section === "credits") return (await takeawayApi.credits()).data.data;
      if (section === "erp") return (await takeawayApi.erpEvents()).data.data;
      return [];
    },
    enabled: !["reports", "import"].includes(section),
    refetchInterval: ["kitchen", "pickup"].includes(section) ? 3_000 : false,
  });
  const locationsQuery = useQuery({ queryKey: ["takeaway", "locations"], queryFn: async () => (await takeawayApi.stockLocations()).data.data, enabled: ["stock", "production", "transfers"].includes(section) });
  const reportQuery = useQuery({ queryKey: ["takeaway", "report", fromDate, toDate], queryFn: async () => (await takeawayApi.operationalSummary(fromDate, toDate)).data.data, enabled: section === "reports" });
  const erpQuery = useQuery({ queryKey: ["takeaway", "erp-reconciliation"], queryFn: async () => (await takeawayApi.erpReconciliation()).data.data, enabled: section === "erp" });
  const actionMutation = useMutation({
    mutationFn: ({ row, action }: { row: TakeawayRecord; action: string }) => {
      if (section === "kitchen") return takeawayApi.updateTicket(row.id, action as "preparing" | "ready");
      if (section === "pickup") return takeawayApi.markPickedUp(row.id);
      if (section === "central") return takeawayApi.updateCentralOrder(row.id, action);
      if (section === "transfers") return takeawayApi.updateTransfer(row.id, { status: action, idempotency_key: `web-transfer-${action}-${crypto.randomUUID()}` });
      if (section === "erp") return takeawayApi.acknowledgeErpEvent(row.id, { idempotency_key: `web-erp-${crypto.randomUUID()}`, erp_reference: `ERP-${Date.now()}` });
      throw new Error("ไม่รองรับคำสั่งนี้");
    },
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["takeaway", section] }); await queryClient.invalidateQueries({ queryKey: ["takeaway", "erp-reconciliation"] }); toast({ title: "บันทึกแล้ว" }); },
    onError: () => toast({ title: "บันทึกไม่สำเร็จ", description: "ตรวจลำดับสถานะ สิทธิ์ และยอดสต๊อก", variant: "destructive" }),
  });
  const createMutation = useMutation({
    mutationFn: async () => {
      if (!context?.brand_id) throw new Error("ไม่พบแบรนด์ Takeaway");
      if (section === "central") {
        if (!context.branch_id) throw new Error("ไม่พบสาขา");
        const round = (await takeawayApi.createCentralRound({ brand_id: context.brand_id, business_date: today(), round_no: Number(form.round_no || 1) })).data.data;
        return takeawayApi.createCentralOrder({ brand_id: context.brand_id, branch_id: context.branch_id, round_id: round.id, order_type: "unlisted", idempotency_key: `web-central-${crypto.randomUUID()}`, items: [{ item_name: form.item_name || "สินค้านอกแคตตาล็อก", quantity: form.quantity || "1", unit: form.unit || "ชิ้น", source_kind: "unlisted" }] });
      }
      if (section === "stock") return takeawayApi.stockMovement({ location_id: form.location_id, item_id: form.item_id, quantity_delta: form.quantity, unit_cost: form.unit_cost || "0", movement_type: form.movement_type || "receive", brand_id: context.brand_id, branch_id: context.branch_id, idempotency_key: `web-stock-${crypto.randomUUID()}` });
      if (section === "production") return takeawayApi.createProduction({ brand_id: context.brand_id, location_id: form.location_id, planned_at: today(), lines: [{ item_id: form.input_item_id, line_type: "input", planned_qty: form.quantity, unit: form.unit || "ชิ้น" }, { item_id: form.output_item_id, line_type: "output", planned_qty: form.quantity, unit: form.unit || "ชิ้น" }] });
      if (section === "transfers") return takeawayApi.createTransfer({ brand_id: context.brand_id, from_location_id: form.from_location_id, to_location_id: form.to_location_id, items: [{ item_id: form.item_id, requested_qty: form.quantity, unit: form.unit || "ชิ้น" }] });
      if (section === "credits") {
        if (!context.branch_id) throw new Error("ไม่พบสาขา");
        return takeawayApi.setCredit({ brand_id: context.brand_id, branch_id: context.branch_id, credit_limit: form.credit_limit || "0" });
      }
      if (section === "import") return takeawayApi.dryRunImport(JSON.parse(jsonText) as Record<string, unknown>);
      throw new Error("ไม่รองรับแบบฟอร์มนี้");
    },
    onSuccess: async (response) => { await queryClient.invalidateQueries({ queryKey: ["takeaway", section] }); const data = response.data.data; toast({ title: section === "import" ? `ผลตรวจ: ${asText(data.status)}` : "สร้างรายการแล้ว", description: section === "import" ? `รับ ${asText(data.accepted_records, "0")} · ไม่รับ ${asText(data.rejected_records, "0")}` : undefined }); },
    onError: (error) => toast({ title: "ทำรายการไม่สำเร็จ", description: error instanceof Error ? error.message : "ตรวจข้อมูลที่กรอก", variant: "destructive" }),
  });
  const rows = (query.data ?? []) as TakeawayRecord[];
  const stations = Array.from(new Set(rows.map((row) => String(row.station ?? "default")))).sort();
  const visibleRows = rows.filter((row) => {
    if (section === "kitchen" && stationFilter && String(row.station ?? "default") !== stationFilter) return false;
    if (section === "pickup" && queueSearch.trim()) {
      const needle = queueSearch.trim().toLowerCase();
      return String(row.queue_number ?? "").toLowerCase().includes(needle)
        || String(row.order_number ?? "").toLowerCase().includes(needle)
        || String(row.customer_name ?? "").toLowerCase().includes(needle);
    }
    return true;
  });
  useEffect(() => {
    if (section !== "kitchen") return;
    const currentIds = new Set(rows.map((row) => row.id));
    const hasNewTicket = knownTicketIds.current.size > 0
      && rows.some((row) => !knownTicketIds.current.has(row.id) && row.status === "queued");
    knownTicketIds.current = currentIds;
    if (!hasNewTicket || !soundEnabled) return;
    const audio = new AudioContext();
    const oscillator = audio.createOscillator();
    const gain = audio.createGain();
    oscillator.frequency.value = 880;
    gain.gain.value = 0.08;
    oscillator.connect(gain);
    gain.connect(audio.destination);
    oscillator.start();
    oscillator.stop(audio.currentTime + 0.18);
    oscillator.addEventListener("ended", () => void audio.close());
  }, [rows, section, soundEnabled]);
  const fields = useMemo(() => {
    if (section === "central") return [["round_no", "รอบสั่ง"], ["item_name", "ชื่อสินค้า"], ["quantity", "จำนวน"], ["unit", "หน่วย"]];
    if (section === "stock") return [["location_id", "คลัง"], ["item_id", "รหัสสินค้า"], ["quantity", "จำนวน (+รับ / -ปรับออก)"], ["unit_cost", "ต้นทุนต่อหน่วย"]];
    if (section === "production") return [["location_id", "คลังผลิต"], ["input_item_id", "รหัสวัตถุดิบ"], ["output_item_id", "รหัสสินค้าผลิต"], ["quantity", "จำนวน"], ["unit", "หน่วย"]];
    if (section === "transfers") return [["from_location_id", "คลังต้นทาง"], ["to_location_id", "คลังปลายทาง"], ["item_id", "รหัสสินค้า"], ["quantity", "จำนวน"], ["unit", "หน่วย"]];
    if (section === "credits") return [["credit_limit", "วงเงินใหม่ (บาท)"]];
    return [];
  }, [section]);
  const showCreate = (
    (section === "central" && hasPermission("takeaway.central_order.create") && hasPermission("takeaway.central_order.manage"))
    || (section === "production" && hasPermission("takeaway.production.manage"))
    || (section === "stock" && hasPermission("takeaway.stock.manage"))
    || (section === "transfers" && hasPermission("takeaway.transfer.manage"))
    || (section === "credits" && hasPermission("takeaway.credit.manage"))
  );
  const erpStats: Array<[string, unknown]> = [
    ["รอส่ง", erpQuery.data?.pending ?? 0],
    ["ERP รับแล้ว", erpQuery.data?.processed ?? 0],
    ["ผิดพลาด", erpQuery.data?.failed ?? 0],
  ];

  return <div className="space-y-5">
    <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-bold uppercase tracking-[0.22em] text-emerald-700">{workspace} workspace</p><h1 className="mt-1 text-2xl font-black">{meta[section].title}</h1><p className="mt-1 text-sm text-slate-500">{meta[section].detail}</p></div><div className="flex flex-wrap gap-2">{["kitchen", "pickup"].includes(section) ? <button onClick={() => void document.documentElement.requestFullscreen?.()} className="flex items-center gap-2 rounded-xl border bg-white px-4 py-2 text-sm font-bold"><Maximize2 className="h-4 w-4" /> เต็มจอ</button> : null}{section === "kitchen" ? <button onClick={() => setSoundEnabled((value) => !value)} className={`flex items-center gap-2 rounded-xl border px-4 py-2 text-sm font-bold ${soundEnabled ? "bg-emerald-50 text-emerald-800" : "bg-white"}`}>{soundEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />} เสียงแจ้งเตือน</button> : null}<button onClick={() => void query.refetch()} className="flex items-center gap-2 rounded-xl border bg-white px-4 py-2 text-sm font-bold"><RefreshCw className="h-4 w-4" /> รีเฟรช</button></div></div>
    {section === "kitchen" && stations.length > 1 ? <div className="flex gap-2 overflow-x-auto rounded-2xl bg-white p-3 shadow-sm"><button onClick={() => setStationFilter("")} className={`rounded-xl px-4 py-2 text-sm font-bold ${stationFilter === "" ? "bg-emerald-500" : "bg-slate-100"}`}>ทุกจุดผลิต</button>{stations.map((station) => <button key={station} onClick={() => setStationFilter(station)} className={`rounded-xl px-4 py-2 text-sm font-bold ${stationFilter === station ? "bg-emerald-500" : "bg-slate-100"}`}>{station}</button>)}</div> : null}
    {section === "pickup" ? <label className="flex items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-sm"><Search className="h-5 w-5 text-slate-400" /><input value={queueSearch} onChange={(event) => setQueueSearch(event.target.value)} placeholder="ค้นหาเลขคิว เลขออเดอร์ หรือลูกค้า" className="w-full bg-transparent text-sm outline-none" /></label> : null}
    {section === "reports" ? <><div className="flex flex-wrap gap-3 rounded-2xl bg-white p-4"><label className="text-sm font-bold">จาก <input type="date" className="ml-2 rounded-lg border px-3 py-2" value={fromDate} onChange={(event) => setFromDate(event.target.value)} /></label><label className="text-sm font-bold">ถึง <input type="date" className="ml-2 rounded-lg border px-3 py-2" value={toDate} onChange={(event) => setToDate(event.target.value)} /></label></div><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[["จำนวนบิล", reportQuery.data?.order_count ?? 0], ["ยอดขาย", `฿${reportQuery.data?.gross_sales ?? "0.00"}`], ["ใบสั่งส่วนกลาง", reportQuery.data?.central_orders ?? 0], ["ส่วนต่างรับของ", reportQuery.data?.central_discrepancies ?? 0], ["ชุดผลิตสำเร็จ", `${reportQuery.data?.production_completed ?? 0}/${reportQuery.data?.production_batches ?? 0}`], ["รายการโอน", reportQuery.data?.transfers ?? 0], ["ยอดใช้เครดิต", `฿${reportQuery.data?.credit_balance ?? "0.00"}`], ["ERP รอส่ง", reportQuery.data?.erp_events_pending ?? 0]].map(([label, value]) => <div key={label} className="rounded-2xl bg-white p-5 shadow-sm"><p className="text-sm text-slate-500">{label}</p><p className="mt-2 text-3xl font-black">{value}</p></div>)}</div></> : null}
    {section === "erp" ? <div className="grid gap-3 sm:grid-cols-3">{erpStats.map(([label, value]) => <div key={label} className="rounded-2xl bg-white p-4 shadow-sm"><p className="text-sm text-slate-500">{label}</p><p className="mt-1 text-2xl font-black">{asText(value)}</p></div>)}</div> : null}
    {section === "import" ? <div className="grid gap-4 lg:grid-cols-[1fr_300px]"><div className="rounded-2xl bg-white p-4 shadow-sm"><label className="text-sm font-bold">แพ็กเกจทดสอบ JSON</label><textarea value={jsonText} onChange={(event) => setJsonText(event.target.value)} className="mt-3 h-96 w-full rounded-xl border bg-slate-950 p-4 font-mono text-xs text-slate-100" /><button onClick={() => createMutation.mutate()} className="mt-3 flex items-center gap-2 rounded-xl bg-emerald-500 px-5 py-3 font-black"><ClipboardCheck className="h-5 w-5" /> ตรวจแบบไม่บันทึก</button></div><div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950"><AlertTriangle className="h-6 w-6" /><p className="mt-3 font-black">การนำเข้าจริงยังล็อกอยู่</p><p className="mt-2">ระหว่างสัญญาข้อมูลเป็นฉบับร่าง ระบบอนุญาตเฉพาะข้อมูล synthetic เท่านั้น ข้อมูล Chambo จริงต้องผ่าน dry-run และอนุมัติ cutover ก่อน</p></div></div> : null}
    {showCreate ? <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><h2 className="font-black">สร้างรายการใหม่</h2><div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">{fields.map(([key, label]) => <label key={key} className="text-xs font-bold text-slate-600">{label}{["location_id", "from_location_id", "to_location_id"].includes(key) && (locationsQuery.data ?? []).length ? <select value={form[key] ?? ""} onChange={(event) => setForm({ ...form, [key]: event.target.value })} className="mt-1 w-full rounded-xl border px-3 py-2 text-sm"><option value="">เลือกคลัง</option>{(locationsQuery.data ?? []).map((location) => <option key={location.id} value={location.id}>{asText(location.name)} · {asText(location.location_type)}</option>)}</select> : <input value={form[key] ?? ""} onChange={(event) => setForm({ ...form, [key]: event.target.value })} className="mt-1 w-full rounded-xl border px-3 py-2 text-sm" />}</label>)}</div><button disabled={createMutation.isPending} onClick={() => createMutation.mutate()} className="mt-4 flex items-center gap-2 rounded-xl bg-slate-950 px-5 py-3 font-bold text-white disabled:opacity-50">{createMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} บันทึก</button></div> : null}
    {section === "central" && workspace === "store" && !showCreate ? <div className="rounded-2xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-900">หน้านี้แสดงใบสั่งของสาขาตามสิทธิ์แล้ว ส่วนฟอร์มสั่งประจำ รายการเพิ่ม และรับของแบบละเอียดจะเชื่อมใน WP18</div> : null}
    {!section.match(/^(reports|import)$/) ? query.isLoading ? <div className="flex justify-center p-12"><Loader2 className="h-8 w-8 animate-spin text-emerald-600" /></div> : <RecordList rows={visibleRows} section={section} busy={actionMutation.isPending} canManageCentral={hasPermission("takeaway.central_order.manage")} canAcknowledgeErp={hasPermission("takeaway.erp.acknowledge")} onAction={(row, action) => actionMutation.mutate({ row, action })} /> : null}
    {section === "stock" ? <div className="rounded-2xl bg-slate-950 p-4 text-sm text-slate-300"><CheckCircle2 className="inline h-4 w-4 text-emerald-400" /> ยอดวัตถุดิบกองกลางผูกกับ บริษัท + คลัง + สินค้า + ล็อต จึงให้หลายแบรนด์ตัดจากยอดเดียวกันได้</div> : null}
  </div>;
}
