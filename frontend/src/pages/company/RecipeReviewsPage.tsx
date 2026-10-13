import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import api from "@/lib/api";
import { useAuthStore } from "@/stores/auth.store";

type System = "restaurant" | "takeaway";
type Item = { id: string; sku: string; name: string; unit: string };
type Line = { item_id: string | null; requested_name: string; quantity: string; unit: string };
type Proposal = { output_id: string; name: string; recipe_type: "production" | "sale"; yield_qty: string; yield_unit: string; loss_percent: string; effective_from: string; reason: string; ingredients: Line[] };
type Source = Omit<Proposal, "reason"> & { id: string; branch_id: string | null; version_no: number; is_active: boolean };
type Review = { id: string; company_id: string; brand_id: string; branch_id: string | null; source_id: string | null; system: System; revision: number; created_by: string; status: string; proposal: Proposal; baseline: Partial<Source>;
  history: { action: string; actor_id: string; reason: string; at: string; reference?: { batch_reference_cost: string | null; notice: string } }[] };
type Options = { company_id: string; manager: boolean; brands: { id: string; name: string; system: System }[]; branches: { id: string; brand_id: string; name: string; code: string }[] };
const states: Record<string, string> = { draft: "ร่าง", submitted: "รออนุมัติ", returned: "ส่งกลับแก้ไข", rejected: "ปฏิเสธ", approved_hold: "อนุมัติเนื้อหา — ยังไม่เปิดใช้" };
const style = "min-h-11 max-w-full rounded-xl border bg-white px-3 py-2";
const today = (): string => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
const blank = (): Proposal => ({ output_id: "", name: "", recipe_type: "production", yield_qty: "1", yield_unit: "kg", loss_percent: "0", effective_from: today(), reason: "", ingredients: [{ item_id: null, requested_name: "", quantity: "1", unit: "kg" }] });

export default function RecipeReviewsPage(): JSX.Element {
  const a = useAuthStore();
  return <Workspace key={`${a.companyId}:${a.brandId}:${a.branchId}:${a.stationKey}:${a.user?.id}:${a.permissions.join(",")}`} />;
}

function Workspace(): JSX.Element {
  const { companyId, brandId, branchId, user } = useAuthStore();
  const [system, setSystem] = useState<System>("restaurant");
  const [brand, setBrand] = useState(brandId ?? "");
  const [branch, setBranch] = useState(branchId ?? "");
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [term, setTerm] = useState("");
  const [search, setSearch] = useState("");
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [editor, setEditor] = useState<Proposal | null>(null);
  const [selected, setSelected] = useState<Review | null>(null);
  const [reason, setReason] = useState("");
  const [requestKey, setRequestKey] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [online, setOnline] = useState(navigator.onLine);
  const client = useQueryClient();
  useEffect(() => {
    const update = (): void => setOnline(navigator.onLine);
    window.addEventListener("online", update); window.addEventListener("offline", update);
    return () => { window.removeEventListener("online", update); window.removeEventListener("offline", update); };
  }, []);
  const options = useQuery({ queryKey: ["recipe-review-options", companyId], queryFn: async () => (await api.get<{ data: Options }>("/company/recipe-reviews/options")).data.data, retry: false, gcTime: 0, enabled: online });
  const brands = options.data?.brands.filter(b => b.system === system) ?? [];
  const valid = Boolean(options.data?.company_id === companyId && brands.some(b => b.id === brand));
  const sources = useQuery({ queryKey: ["recipe-review-sources", companyId, system, brand, term], queryFn: async () => (await api.get<{ data: Source[] }>("/company/recipe-reviews/sources", { params: { system, brand_id: brand, search: term } })).data.data, enabled: valid && online, retry: false, gcTime: 0 });
  const catalog = useQuery({ queryKey: ["recipe-review-catalog", companyId, system, brand, term], queryFn: async () => (await api.get<{ data: Item[] }>("/company/recipe-reviews/catalog", { params: { system, brand_id: brand, search: term } })).data.data, enabled: valid && online, retry: false, gcTime: 0 });
  const reviews = useQuery({ queryKey: ["recipe-reviews", companyId, system, brand, filter, page], queryFn: async () => (await api.get<{ data: { items: Review[]; has_more: boolean } }>("/company/recipe-reviews", { params: { system, brand_id: brand, state: filter, page } })).data.data, enabled: valid && online, retry: false, gcTime: 0 });
  const items = catalog.data ?? [];
  const label = (id: string | null): string => items.find(i => i.id === id)?.name ?? id ?? "ขอเพิ่มวัตถุดิบ";
  const reset = (): void => { setEditor(null); setSelected(null); setSourceId(null); setReason(""); setError(""); setRequestKey(crypto.randomUUID()); };
  const loadSource = (s: Source): void => {
    reset(); setSourceId(s.id); setBranch(options.data?.manager ? s.branch_id ?? "" : branchId ?? "");
    setEditor({ output_id: s.output_id, name: s.name, recipe_type: s.recipe_type, yield_qty: s.yield_qty, yield_unit: s.yield_unit,
      loss_percent: s.loss_percent, effective_from: today(), reason: "", ingredients: s.ingredients.map(l => ({ ...l, requested_name: "" })) });
  };
  const act = async (action: string, extra: Record<string, unknown> = {}): Promise<void> => {
    if (!online || busy) return;
    setBusy(true); setError("");
    try {
      const data = selected
        ? (await api.post<{ data: Review }>(`/company/recipe-reviews/${selected.id}/actions`, { action, revision: selected.revision, reason, ...extra })).data.data
        : (await api.post<{ data: Review }>("/company/recipe-reviews", { system, brand_id: brand, branch_id: branch || null, source_id: sourceId, request_key: requestKey, proposal: editor })).data.data;
      setSelected(data); setEditor(null); setReason("");
      await client.invalidateQueries({ queryKey: ["recipe-reviews"] });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: unknown } } };
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "บันทึกไม่ได้ ตรวจข้อมูล/สิทธิ์ หรือโหลดรายการใหม่ หากมีผู้แก้ไขพร้อมกัน");
    } finally { setBusy(false); }
  };
  const failed = options.error || sources.error || catalog.error || reviews.error;
  const rowMismatch = reviews.data?.items.some(r => r.company_id !== companyId || r.brand_id !== brand || r.system !== system);
  const ready = online && valid && !failed && !rowMismatch;
  const editable = selected && selected.created_by === user?.id && ["draft", "returned"].includes(selected.status);
  const approver = selected && options.data?.manager && selected.created_by !== user?.id && selected.status === "submitted";
  const body = (p: Partial<Proposal>): JSX.Element => <div className="space-y-2 text-sm"><p>{p.name} · {p.recipe_type === "production" ? "สูตรผลิต" : "สูตรประกอบขาย"}</p><p>ผลผลิต {p.yield_qty} {p.yield_unit} · สูญเสีย {p.loss_percent}%</p><ul className="list-inside list-disc">{p.ingredients?.map((l, i) => <li key={i}>{label(l.item_id)} {l.requested_name ? `(${l.requested_name})` : ""} — {l.quantity} {l.unit}</li>)}</ul></div>;
  return <div className="space-y-4" data-testid="recipe-reviews"><h1 className="text-2xl font-bold">ทะเบียนสูตรและอนุมัติครัวกลาง (UAT)</h1>
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-4">รุ่นทดลองงานร่างและตรวจอนุมัติเท่านั้น การอนุมัติเนื้อหายังไม่เปลี่ยนสูตรใช้งาน ไม่ย้ายหรือตัดสต๊อก
      <p className="mt-2 text-sm">สูตรเดิมยังทำงานตามระบบเดิม ยังไม่ได้บังคับทุกช่องทางผ่านการอนุมัติ ต้องตรวจการจับคู่วัตถุดิบกลางและเส้นทางตัดสต๊อกก่อนเปิดใช้ขั้นถัดไป</p></div>
    <div className="flex flex-wrap gap-3">
      <select aria-label="ระบบสูตร" className={style} value={system} disabled={busy} onChange={e => { setSystem(e.target.value as System); setBrand(""); setPage(1); reset(); }}><option value="restaurant">Restaurant</option><option value="takeaway">Takeaway</option></select>
      <select aria-label="แบรนด์สูตร" className={style} value={brand} disabled={busy} onChange={e => { setBrand(e.target.value); setBranch(options.data?.manager ? "" : branchId ?? ""); setPage(1); reset(); }}><option value="">เลือกแบรนด์</option>{brands.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select>
      <Button variant="outline" disabled={busy || !online} onClick={() => { reset(); void client.invalidateQueries({ queryKey: ["recipe-reviews"] }); void sources.refetch(); void catalog.refetch(); void options.refetch(); }}>โหลดใหม่</Button>
    </div>
    {!online && <p role="status">ออฟไลน์ — ไม่สามารถบันทึกหรืออนุมัติได้</p>}
    {(failed || rowMismatch || (options.data && options.data.company_id !== companyId)) && <p role="alert">อ่านข้อมูลไม่ได้หรือบริบทไม่ตรง กรุณาตรวจสิทธิ์แล้วโหลดใหม่</p>}
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {ready && <>
      <form className="flex gap-2" onSubmit={e => { e.preventDefault(); setTerm(search); }}><Input aria-label="ค้นหาสูตรหรือวัตถุดิบ" placeholder="ค้นหาสูตรหรือวัตถุดิบ" value={search} maxLength={100} onChange={e => setSearch(e.target.value)} /><Button>ค้นหา</Button></form>
      <section className="space-y-3 rounded-xl border bg-white p-4"><h2 className="font-semibold">สูตรเดิมจากต้นทาง — ไม่สร้างสูตรซ้ำ</h2>
        <p className="text-xs text-slate-500">แสดงสูงสุด 200 สูตร / สินค้า 250 รายการ ใช้ค้นหาเพื่อจำกัดรายการ รวมสูตรเก่าและสูตรที่ปิดใช้</p>
        <div className="flex flex-wrap gap-3"><select aria-label="สูตรต้นฉบับ" className={`${style} flex-1`} value="" disabled={busy} onChange={e => { const s = sources.data?.find(r => r.id === e.target.value); if (s) loadSource(s); }}><option value="">เลือกสูตรเพื่อทำร่างเสนอแก้ไข</option>{sources.data?.map(s => <option key={s.id} value={s.id}>{s.name} · v{s.version_no} · {s.is_active ? "เปิดใช้" : "ปิดใช้"}</option>)}</select>
          <Button disabled={busy} onClick={() => { reset(); setEditor(blank()); }}>สร้างร่างสูตรใหม่</Button></div>
      </section>
      {editor && <form className="space-y-4 rounded-xl border bg-white p-4" onSubmit={e => { e.preventDefault(); void act("save", selected ? { proposal: editor } : {}); }}>
        <h2 className="font-semibold">{selected ? "แก้ไขร่าง" : "สร้างร่าง"} — ไม่เปลี่ยนสูตรใช้งาน</h2>
        <div className="grid gap-3 md:grid-cols-2"><label>ชื่อสูตร<Input required value={editor.name} onChange={e => setEditor({ ...editor, name: e.target.value })} /></label>
          <label>สาขา<select aria-label="สาขาสูตร" className={`${style} block w-full`} value={branch} disabled={Boolean(selected)} onChange={e => setBranch(e.target.value)}>{options.data?.manager && <option value="">ทุกสาขาในแบรนด์</option>}{options.data?.branches.filter(b => b.brand_id === brand).map(b => <option key={b.id} value={b.id}>{b.code} · {b.name}</option>)}</select></label>
          <label>สินค้าผลลัพธ์<select aria-label="สินค้าผลลัพธ์" required className={`${style} block w-full`} disabled={Boolean(sourceId || selected)} value={editor.output_id} onChange={e => setEditor({ ...editor, output_id: e.target.value })}><option value="">เลือกสินค้า</option>{editor.output_id && !items.some(i => i.id === editor.output_id) && <option value={editor.output_id}>{editor.output_id}</option>}{items.map(i => <option key={i.id} value={i.id}>{i.name} ({i.sku})</option>)}</select></label>
          <label>ประเภท<select className={`${style} block w-full`} value={editor.recipe_type} onChange={e => setEditor({ ...editor, recipe_type: e.target.value as Proposal["recipe_type"] })}><option value="production">สูตรผลิต</option><option value="sale">สูตรประกอบขาย</option></select></label>
          <label>จำนวนผลผลิต<Input type="number" required min="0.0001" step="0.0001" value={editor.yield_qty} onChange={e => setEditor({ ...editor, yield_qty: e.target.value })} /></label>
          <label>หน่วยผลผลิต<Input required value={editor.yield_unit} onChange={e => setEditor({ ...editor, yield_unit: e.target.value })} /></label>
          <label>สูญเสีย (%)<Input type="number" required min="0" max="99.9999" step="0.0001" value={editor.loss_percent} onChange={e => setEditor({ ...editor, loss_percent: e.target.value })} /></label>
          <label>วันที่เสนอเริ่มใช้<Input type="date" required value={editor.effective_from} onChange={e => setEditor({ ...editor, effective_from: e.target.value })} /></label></div>
        <h3 className="font-semibold">ส่วนผสม</h3>{editor.ingredients.map((l, index) => {
          const update = (patch: Partial<Line>): void => setEditor({ ...editor, ingredients: editor.ingredients.map((v, i) => i === index ? { ...v, ...patch } : v) });
          return <div className="grid gap-2 rounded-xl bg-slate-50 p-3 md:grid-cols-4" key={index}>
            <select aria-label={`วัตถุดิบ ${index + 1}`} className={style} value={l.item_id ?? ""} onChange={e => update({ item_id: e.target.value || null, requested_name: "" })}><option value="">ขอเพิ่มวัตถุดิบ</option>{l.item_id && !items.some(i => i.id === l.item_id) && <option value={l.item_id}>{l.item_id}</option>}{items.filter(i => i.id !== editor.output_id).map(i => <option key={i.id} value={i.id}>{i.name} ({i.sku})</option>)}</select>
            {!l.item_id && <Input aria-label={`ชื่อขอเพิ่ม ${index + 1}`} placeholder="ชื่อวัตถุดิบที่ขอเพิ่ม" required value={l.requested_name} onChange={e => update({ requested_name: e.target.value })} />}
            <Input aria-label={`ปริมาณ ${index + 1}`} type="number" min="0.0001" step="0.0001" required value={l.quantity} onChange={e => update({ quantity: e.target.value })} />
            <Input aria-label={`หน่วย ${index + 1}`} placeholder="หน่วย เช่น kg, g" required value={l.unit} onChange={e => update({ unit: e.target.value })} />
            <Button type="button" variant="outline" disabled={editor.ingredients.length === 1} onClick={() => setEditor({ ...editor, ingredients: editor.ingredients.filter((_, i) => i !== index) })}>ลบแถว</Button></div>;
        })}
        <Button type="button" variant="outline" disabled={editor.ingredients.length >= 200} onClick={() => setEditor({ ...editor, ingredients: [...editor.ingredients, { item_id: null, requested_name: "", quantity: "1", unit: "kg" }] })}>เพิ่มส่วนผสม</Button>
        <label className="block">เหตุผลเสนอสูตร<Input required minLength={3} value={editor.reason} onChange={e => { setEditor({ ...editor, reason: e.target.value }); setReason(e.target.value); }} /></label>
        <Button disabled={busy}>บันทึกร่าง</Button>
      </form>}
      <section className="space-y-3 rounded-xl border bg-white p-4"><h2 className="font-semibold">คำขอและผลตรวจ</h2>
        <select aria-label="สถานะคำขอ" className={style} value={filter} onChange={e => { setFilter(e.target.value); setPage(1); reset(); }}><option value="all">ทุกสถานะ</option>{Object.entries(states).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select>
        {!reviews.data?.items.length && <p>ยังไม่มีคำขอตามตัวกรอง</p>}
        <div className="grid gap-3 md:grid-cols-2">{reviews.data?.items.map(r => <button disabled={busy} className="min-h-16 rounded-xl border p-3 text-left" key={r.id} onClick={() => { reset(); setSelected(r); setBranch(r.branch_id ?? ""); }}><strong>{r.proposal.name}</strong><p>{states[r.status]} · ครั้งที่ {r.revision}</p></button>)}</div>
        <div className="flex gap-3"><Button variant="outline" disabled={page === 1 || busy} onClick={() => { setPage(page - 1); reset(); }}>ก่อนหน้า</Button><span>หน้า {page}</span><Button variant="outline" disabled={!reviews.data?.has_more || busy} onClick={() => { setPage(page + 1); reset(); }}>ถัดไป</Button></div>
      </section>
      {selected && !editor && <section className="space-y-4 rounded-xl border bg-white p-4"><h2 className="font-semibold">{selected.proposal.name} · {states[selected.status]}</h2>
        <div className="grid gap-4 md:grid-cols-2"><div className="rounded-xl bg-slate-50 p-3"><h3>ก่อนแก้ไข</h3>{selected.source_id ? body(selected.baseline) : <p>สูตรใหม่</p>}</div><div className="rounded-xl bg-blue-50 p-3"><h3>สูตรที่เสนอ</h3>{body(selected.proposal)}</div></div>
        {selected.history.at(-1)?.reference && <p className="text-sm">ต้นทุนอ้างอิงต่อชุด: {selected.history.at(-1)?.reference?.batch_reference_cost ?? "ยังคำนวณไม่ได้"} · {selected.history.at(-1)?.reference?.notice}</p>}
        {(editable || approver) && <Input aria-label="เหตุผลการดำเนินการ" placeholder="เหตุผลการดำเนินการ (อย่างน้อย 3 ตัวอักษร)" value={reason} onChange={e => setReason(e.target.value)} />}
        {editable && <div className="flex gap-3"><Button variant="outline" disabled={busy} onClick={() => { setEditor(structuredClone(selected.proposal)); setReason(selected.proposal.reason); }}>แก้ไขร่าง</Button><Button disabled={busy || reason.trim().length < 3} onClick={() => void act("submit")}>ส่งอนุมัติ</Button></div>}
        {approver && <><p className="text-sm">วัตถุดิบที่ขอเพิ่มต้องจับคู่รายการที่มีอยู่และหน่วยเข้ากันได้ก่อนอนุมัติ หากยังไม่มี ให้ผู้ดูแลตรวจรายการกลางก่อน ไม่สร้างสต๊อกจากหน้านี้</p>
          {selected.proposal.ingredients.map((l, index) => !l.item_id && <div key={index} className="flex flex-wrap gap-2"><span>{l.requested_name}</span><select aria-label={`จับคู่วัตถุดิบ ${index + 1}`} className={style} value="" disabled={busy || reason.trim().length < 3} onChange={e => void act("resolve", { line_index: index, item_id: e.target.value })}><option value="">จับคู่รายการอนุมัติแล้ว</option>{items.map(i => <option key={i.id} value={i.id}>{i.name} ({i.sku})</option>)}</select></div>)}
          <div className="flex flex-wrap gap-3">{[["approve", "อนุมัติเนื้อหา (ยังไม่เปิดใช้)"], ["return", "ส่งกลับแก้ไข"], ["reject", "ปฏิเสธ"]].map(([action, name]) => <Button key={action} disabled={busy || reason.trim().length < 3} onClick={() => void act(action)}>{name}</Button>)}</div></>}
        <h3 className="font-semibold">ประวัติการตัดสินใจ</h3>{selected.history.map((h, i) => <p className="break-all text-sm" key={i}>{new Date(h.at).toLocaleString("th-TH")} · {h.action} · {h.reason} · ผู้ดำเนินการ {h.actor_id}</p>)}
      </section>}
    </>}
  </div>;
}
