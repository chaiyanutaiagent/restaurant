import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import DocumentHistory from "@/components/company/DocumentHistory";
import api from "@/lib/api";
import { useAuthStore } from "@/stores/auth.store";

type Side = "payable" | "receivable";
type Row = { id: string; document_id: string | null; number: string; partner_name: string;
  due_date: string; total_amount: string; paid_amount: string; outstanding: string; days_overdue: number;
  bucket: string; balance_warning: boolean };
type Report = { company_id: string; branch_id: string; side: Side; generated_at: string; aging_date: string;
  summary: Record<string, string | number>; items: Row[]; has_more: boolean; document_kind: string;
  partners: { partner_id: string; partner_name: string; count: number; outstanding: string }[] };
const buckets: Record<string, string> = { not_due: "ยังไม่ถึงกำหนด", due_today: "ครบกำหนดวันนี้", days_1_30: "ค้าง 1–30 วัน",
  days_31_60: "ค้าง 31–60 วัน", days_61_90: "ค้าง 61–90 วัน", days_91_plus: "ค้างเกิน 90 วัน" };
const money = (value: string | number): string => new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(Number(value));
const selectStyle = "min-h-11 rounded-xl border bg-white px-3 py-2";

export default function DebtAgingPage(): JSX.Element {
  const auth = useAuthStore();
  return <Workspace key={`${auth.companyId}:${auth.branchId}:${auth.brandId}:${auth.stationKey}:${auth.user?.id}:${auth.permissions.join(",")}`} />;
}

function Workspace(): JSX.Element {
  const { companyId, branchId, stationKey, permissions } = useAuthStore();
  const can = (p: string): boolean => permissions.includes("*") || permissions.includes(p);
  const sides: Side[] = (["payable", "receivable"] as Side[]).filter(s => can(s === "payable" ? "accounting.payment.view" : "accounting.invoice.view"));
  const [side, setSide] = useState<Side>(sides[0] ?? "payable");
  const [search, setSearch] = useState("");
  const [term, setTerm] = useState("");
  const [window, setWindow] = useState("all");
  const [bucket, setBucket] = useState("all");
  const [page, setPage] = useState(1);
  const [document, setDocument] = useState<{ kind: string; id: string } | null>(null);
  const [online, setOnline] = useState(navigator.onLine);
  const [clock, setClock] = useState(Date.now());
  const allowed = Boolean(companyId && branchId && !stationKey && can("accounting.report.view") && sides.includes(side));
  useEffect(() => {
    const update = (): void => setOnline(navigator.onLine);
    globalThis.addEventListener("online", update); globalThis.addEventListener("offline", update);
    const timer = globalThis.setInterval(() => setClock(Date.now()), 30000);
    return () => { globalThis.removeEventListener("online", update); globalThis.removeEventListener("offline", update); globalThis.clearInterval(timer); };
  }, []);
  const query = useQuery({ queryKey: ["debt-aging", companyId, branchId, side, term, window, bucket, page],
    queryFn: async () => (await api.get<{ data: Report }>("/company/debt-aging", { params: { side, search: term, window, bucket, page } })).data.data,
    enabled: allowed && online, retry: false, gcTime: 0, staleTime: 30000 });
  const report = query.data;
  const mismatch = report && (report.company_id !== companyId || report.branch_id !== branchId || report.side !== side);
  const stale = report && clock - Date.parse(report.generated_at) > 300000;
  const ready = report && online && !mismatch && !query.error && !query.isFetching && !stale;
  const change = (): void => { setPage(1); setDocument(null); };
  if (!allowed) return <p role="alert">กรุณาเลือกสาขาและใช้สิทธิ์ดูรายงานบัญชี พร้อมสิทธิ์ดูเจ้าหนี้หรือลูกหนี้ ไม่รองรับบริบทจุดขาย</p>;
  return <div className="space-y-5" data-testid="debt-aging">
    <header className="flex flex-wrap items-center justify-between gap-3"><h1 className="text-2xl font-bold">อายุหนี้และกำหนดรับ–จ่าย</h1>
      <Button variant="outline" disabled={!online || query.isFetching} onClick={() => void query.refetch()}>อัปเดตยอดล่าสุด</Button></header>
    <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-950">
      ยอดหนี้ค้างปัจจุบันของสาขาที่เลือก ตามเวลาประเทศไทย ไม่ใช่ยอดย้อนหลังหรือเงินสดคาดการณ์
      <br />ลูกหนี้รวมเฉพาะงานขายเชื่อที่แจ้งหนี้แล้ว ไม่รวมยอดขาย POS เครดิตสาขา หรือค่าสมาชิก SaaS
      เจ้าหนี้ใช้ยอดคงเหลือต้นทางหลังตัดชำระ รวมส่วนที่หัก ณ ที่จ่ายแล้ว ไม่หักภาษีซ้ำ
      <br />ช่วง 7/30 วันรวมวันนี้และไม่รวมยอดเกินกำหนด ยอดสรุปทั้งหมดเป็นไปตามตัวกรอง
    </div>
    <form className="flex flex-wrap gap-3 rounded-xl border bg-white p-4" onSubmit={e => { e.preventDefault(); setTerm(search); change(); }}>
      <select aria-label="ประเภทหนี้" className={selectStyle} value={side} onChange={e => { setSide(e.target.value as Side); change(); }}>{sides.map(s => <option key={s} value={s}>{s === "payable" ? "เจ้าหนี้ — เราต้องจ่าย" : "ลูกหนี้ — เราต้องรับ"}</option>)}</select>
      <select aria-label="กำหนดชำระ" className={selectStyle} value={window} onChange={e => { setWindow(e.target.value); change(); }}>
        <option value="all">ทุกกำหนดชำระ</option><option value="overdue">เกินกำหนด</option><option value="today">วันนี้</option><option value="next7">วันนี้ถึงอีก 7 วัน</option><option value="next30">วันนี้ถึงอีก 30 วัน</option>
      </select>
      <select aria-label="ช่วงอายุหนี้" className={selectStyle} value={bucket} onChange={e => { setBucket(e.target.value); change(); }}><option value="all">ทุกช่วงอายุหนี้</option>{Object.entries(buckets).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
      <Input aria-label="ค้นหาคู่ค้าหรือเลขเอกสาร" className="min-h-11 min-w-0 flex-1 basis-60" maxLength={100} placeholder="ชื่อคู่ค้าหรือเลขเอกสาร" value={search} onChange={e => setSearch(e.target.value)} />
      <Button disabled={!online}>ค้นหา</Button>
    </form>
    {!online ? <p role="status">ออฟไลน์ — ซ่อนยอดจนเชื่อมต่อและตรวจยอดใหม่</p> : mismatch ? <p role="alert">บริบทไม่ตรงกับบริษัทและสาขาที่เลือก</p>
      : query.error ? <p role="alert">อ่านรายงานไม่ได้หรือไม่มีสิทธิ์ กรุณากดอัปเดตยอดล่าสุด</p>
      : query.isFetching ? <p role="status">กำลังอ่านยอดล่าสุด…</p> : stale ? <p role="status">ข้อมูลเกิน 5 นาที กรุณากดอัปเดตยอดล่าสุดก่อนใช้อ้างอิง</p> : null}
    {ready && <>
      <p className="text-sm text-slate-500">ข้อมูล ณ {new Date(report.generated_at).toLocaleString("th-TH", { timeZone: "Asia/Bangkok" })} · {report.summary.count} เอกสาร · THB</p>
      {Number(report.summary.warnings) > 0 && <p role="alert" className="rounded-xl bg-amber-50 p-4">พบ {report.summary.warnings} รายการที่ยอดต้นทางไม่ตรงกันหรือหลักฐานแจ้งหนี้ไม่ครบ กรุณาให้บัญชีตรวจ รายงานไม่แก้ยอดแทนต้นทาง</p>}
      <section aria-label="ยอดสรุป" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">{Object.entries({ outstanding: "คงค้างทั้งหมด", overdue: "เกินกำหนด", due_today: "ครบกำหนดวันนี้", next7: "ถึงกำหนดวันนี้–7 วัน", next30: "ถึงกำหนดวันนี้–30 วัน" }).map(([key, label]) =>
        <div className="rounded-xl border bg-white p-4" key={key}><p className="text-sm text-slate-500">{label}</p><p className="text-xl font-bold">{money(report.summary[key])}</p></div>)}</section>
      <section aria-label="อายุหนี้" className="grid gap-3 sm:grid-cols-3">{Object.entries(buckets).map(([key, label]) => <div className="rounded-xl border bg-white p-3" key={key}><p>{label}</p><strong>{money(report.summary[`bucket_${key}`])}</strong></div>)}</section>
      <section className="rounded-xl border bg-white p-4"><h2 className="mb-3 font-semibold">รายละเอียดเอกสารคงค้าง</h2>
        {!report.items.length ? <p>ไม่พบหนี้ค้างตามตัวกรองนี้</p> : <div className="overflow-x-auto"><table className="w-full min-w-[850px] text-left text-sm"><thead><tr>{["เอกสาร / คู่ค้า", "กำหนดชำระ", "อายุหนี้", "ยอดเต็ม", "ตัดชำระแล้ว", "คงเหลือ"].map(h => <th className="p-2" key={h}>{h}</th>)}</tr></thead>
          <tbody>{report.items.map(r => <tr className="border-t" key={r.id}><td className="p-2">{r.document_id ? <button className="min-h-11 text-teal-700 underline" onClick={() => setDocument({ kind: report.document_kind, id: r.document_id! })}>{r.number}</button> : r.number}<p>{r.partner_name}</p>{r.balance_warning && <p className="text-amber-800">ต้องตรวจต้นทาง</p>}</td>
            <td>{r.due_date}</td><td>{r.days_overdue ? `${r.days_overdue} วัน` : buckets[r.bucket]}</td><td>{money(r.total_amount)}</td><td>{money(r.paid_amount)}</td><td className="font-semibold">{money(r.outstanding)}</td></tr>)}</tbody></table></div>}
        <div className="mt-4 flex items-center justify-end gap-3"><Button variant="outline" disabled={page === 1} onClick={() => { setPage(page - 1); setDocument(null); }}>ก่อนหน้า</Button><span>หน้า {page}</span><Button variant="outline" disabled={!report.has_more} onClick={() => { setPage(page + 1); setDocument(null); }}>ถัดไป</Button></div>
      </section>
      <section className="rounded-xl border bg-white p-4"><h2 className="font-semibold">คู่ค้ายอดค้างสูงสุด 20 รายการตามตัวกรอง</h2><p className="mb-3 text-xs text-slate-500">ชื่อลูกหนี้ตามเอกสารเดิม หากเปลี่ยนชื่ออาจแยกแถว</p>
        <div className="grid gap-3 md:grid-cols-2">{report.partners.map((p, i) => <div key={`${p.partner_id}:${i}`} className="rounded-xl bg-slate-50 p-3"><p>{p.partner_name}</p><strong>{money(p.outstanding)}</strong> · {p.count} เอกสาร</div>)}</div>
      </section>
      <Link className="inline-block text-teal-700 underline" to={side === "payable" ? "/payable?tab=invoices" : "/company/credit-sales"}>ไปหน้าต้นทางเพื่อรับ–จ่ายเงิน</Link>
    </>}
    {ready && document && <DocumentHistory key={document.id} kind={document.kind} id={document.id} online={online} onClose={() => setDocument(null)} />}
  </div>;
}
