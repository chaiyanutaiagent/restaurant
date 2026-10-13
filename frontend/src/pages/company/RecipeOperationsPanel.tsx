import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Material = { id: string; name: string; unit: string; code: string };
type Line = { item_id: string | null; requested_name: string; canonical_id?: string | null };
type Run = { id: string; status: string; snapshot: { stock_quantity: string; total_cost: string; request: { reason: string } } };
const style = "min-h-11 max-w-full rounded-xl border bg-white p-2";

export function MaterialApproval({ company, lines, disabled, resolve }: {
  company: string | null; lines: Line[]; disabled: boolean;
  resolve: (index: number, canonical: string | null) => void;
}): JSX.Element {
  const query = useQuery({ queryKey: ["recipe-canonical", company], queryFn: async () => (await api.get<{ data: Material[] }>("/company/recipe-reviews/canonical")).data.data, retry: false, gcTime: 0 });
  return <div className="space-y-3 rounded-xl border p-3"><h3 className="font-semibold">อนุมัติวัตถุดิบกลาง</h3>
    <p className="text-sm">สูตรผลิตต้องจับคู่ทุกแถวกับวัตถุดิบกลางของบริษัท หน่วยจะถูกตรวจและแปลงให้อัตโนมัติ การสร้างรายการไม่เพิ่มยอดสต๊อก</p>
    {query.isPending && <p>กำลังโหลดวัตถุดิบกลาง…</p>}{query.error && <p role="alert">โหลดวัตถุดิบกลางไม่ได้ กรุณาโหลดใหม่</p>}
    {query.data && lines.map((line, index) => <div key={index} className="flex flex-wrap items-center gap-2"><span>ส่วนผสม {index + 1}: {line.requested_name || line.item_id} {line.canonical_id ? "✓ จับคู่แล้ว" : ""}</span>
      <select aria-label={`วัตถุดิบกลาง ${index + 1}`} className={style} value={line.canonical_id ?? ""} disabled={disabled} onChange={e => { if (e.target.value) resolve(index, e.target.value); }}><option value="">เลือกวัตถุดิบกลาง</option>{query.data.map(m => <option key={m.id} value={m.id}>{m.name} · {m.unit}</option>)}</select>
      {!line.item_id && <Button variant="outline" disabled={disabled} onClick={() => resolve(index, null)}>อนุมัติสร้างวัตถุดิบใหม่</Button>}
    </div>)}
  </div>;
}

export function RecipeProductionPanel({ company, brand, system, reviewId, unit }: {
  company: string | null; brand: string; system: string; reviewId: string; unit: string;
}): JSX.Element {
  const [quantity, setQuantity] = useState("1");
  const [location, setLocation] = useState("");
  const [reason, setReason] = useState("");
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const client = useQueryClient();
  const locations = useQuery({ queryKey: ["recipe-output-locations", company, brand, system], queryFn: async () => (await api.get<{ data: { id: string; name: string }[] }>("/company/recipe-reviews/output-locations", { params: { system, brand_id: brand } })).data.data, retry: false, gcTime: 0 });
  const runs = useQuery({ queryKey: ["recipe-production", company, brand, system], queryFn: async () => (await api.get<{ data: Run[] }>("/company/recipe-reviews/production", { params: { system, brand_id: brand } })).data.data, retry: false, gcTime: 0 });
  const execute = async (id?: string): Promise<void> => {
    if (busy || !navigator.onLine) return;
    setBusy(true); setError("");
    try {
      if (id) await api.post(`/company/recipe-reviews/production/${id}/retry`);
      else await api.post("/company/recipe-reviews/production", { review_id: reviewId, request_key: key, quantity, output_location_id: location, reason });
      setKey(crypto.randomUUID());
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
      setError(typeof detail === "string" ? detail : "บันทึกไม่สมบูรณ์ โหลดรายการผลิตแล้วกดส่งผลผลิตซ้ำที่รายการค้าง ห้ามสร้างรายการใหม่ซ้ำ");
    } finally { await client.invalidateQueries({ queryKey: ["recipe-production"] }); setBusy(false); }
  };
  return <section className="space-y-3 rounded-xl border border-blue-200 p-4"><h3 className="font-semibold">ผลิตจากสูตรอนุมัติ — คลังวัตถุดิบกลางร่วมกัน</h3>
    <p className="text-sm">ยืนยันเมื่อผลิตจริงเท่านั้น ระบบตัดวัตถุดิบตามสูตรและบันทึกผลผลิตเข้าคลังแบรนด์ ไม่สร้างวัตถุดิบคงเหลือให้ หากส่งผลผลิตขัดข้องให้ทำต่อจากรายการค้าง</p>
    {(locations.error || runs.error) && <p role="alert">อ่านคลังหรือรายการผลิตไม่ได้ ตรวจสิทธิ์และการเปิดธุรกรรมครัวกลาง</p>}
    {locations.isPending && <p>กำลังโหลดคลัง…</p>}
    {error && <p role="alert">{error}</p>}
    {locations.data && runs.data && <><div className="flex flex-wrap gap-3"><label>ผลผลิตจริง ({unit})<Input aria-label="ผลผลิตจริง" type="number" min="0.0001" step="0.0001" value={quantity} onChange={e => setQuantity(e.target.value)} /></label>
      <label>คลังสำเร็จรูป<select aria-label="คลังผลผลิต" className={`${style} block`} value={location} onChange={e => setLocation(e.target.value)}><option value="">เลือกคลัง</option>{locations.data.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
      <label>หมายเหตุผลิต<Input aria-label="หมายเหตุผลิต" value={reason} onChange={e => setReason(e.target.value)} /></label></div>
      {!locations.data.length && <p>ยังไม่ได้ตั้งคลังสำเร็จรูปครัวกลางของแบรนด์นี้</p>}
      <Button disabled={busy || !location || Number(quantity) <= 0 || reason.trim().length < 3} onClick={() => { if (window.confirm("ยืนยันผลิตจริงและตัดวัตถุดิบกลางตามสูตรนี้?")) void execute(); }}>ยืนยันผลิตและตัดวัตถุดิบ</Button>
      <h4>รายการผลิตล่าสุดของแบรนด์</h4>{!runs.data.length && <p>ยังไม่มีรายการผลิต</p>}{runs.data.map(r => <div className="rounded-xl bg-slate-50 p-3" key={r.id}><p>{r.snapshot.request.reason} · {r.status === "completed" ? "เสร็จแล้ว" : "ตัดวัตถุดิบแล้ว รอส่งผลผลิต"} · ต้นทุน {r.snapshot.total_cost}</p>
        {r.status === "output_pending" && <Button disabled={busy} onClick={() => void execute(r.id)}>ส่งผลผลิตต่อ (ไม่ตัดวัตถุดิบซ้ำ)</Button>}</div>)}</>}
  </section>;
}
