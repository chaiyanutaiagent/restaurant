import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import api from "@/lib/api";
import { useAuthStore } from "@/stores/auth.store";
import type { BusinessDocumentEntry } from "@/config/businessDocuments";
import DocumentHistory from "./DocumentHistory";

type RegisterData = {
  items: { id: string; number: string; document_date: string; amount: string | null; status: string; created_at: string }[];
  has_more: boolean; company_id: string; branch_id: string; source: string;
};

export default function DocumentRegister({ entries, online }: { entries: readonly BusinessDocumentEntry[]; online: boolean }): JSX.Element {
  const { companyId, branchId, brandId, stationKey, targetDatabase } = useAuthStore();
  const [kind, setKind] = useState(entries[0]?.id ?? "");
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState({ search: "", date_from: "", date_to: "" });
  const [dates, setDates] = useState({ date_from: "", date_to: "" });
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<{ id: string; kind: string; scope: string } | null>(null);
  const scope = [companyId, branchId, brandId, stationKey, targetDatabase].join(":");
  const effectiveKind = entries.some(entry => entry.id === kind) ? kind : (entries[0]?.id ?? "");
  const unsupported = targetDatabase === "takeaway" && ["purchase_order", "goods_receipt"].includes(effectiveKind);
  const query = useQuery({
    queryKey: ["company-document-register", companyId, branchId, brandId, stationKey, targetDatabase, effectiveKind, filters, page],
    queryFn: async () => (await api.get<{ data: RegisterData }>("/company/documents/register", {
      params: { kind: effectiveKind, search: filters.search, date_from: filters.date_from || undefined, date_to: filters.date_to || undefined, page, limit: 25 },
    })).data.data,
    enabled: online && Boolean(branchId) && !stationKey && !unsupported && Boolean(effectiveKind),
    retry: false,
    gcTime: 0,
  });
  const mismatch = query.data && (query.data.company_id !== companyId || query.data.branch_id !== branchId);
  return <section className="mb-6 rounded-2xl border bg-white p-5" data-testid="document-register">
    <h2 className="text-lg font-bold">ทะเบียนอ้างอิงเอกสาร</h2>
    <p className="my-2 text-sm text-slate-600">รายการและสถานะปัจจุบันจากต้นทาง กดเลขเอกสารเพื่อดูประวัติและหลักฐาน ณ วันออก เอกสารเก่าไม่สร้างหลักฐานย้อนหลัง ไม่รวมยอดข้ามฐานข้อมูล</p>
    <form className="my-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5" onSubmit={event => { event.preventDefault(); setPage(1); setFilters({ search, ...dates }); }}>
      <label className="text-sm">ประเภทเอกสาร<select aria-label="ประเภทในทะเบียน" className="mt-1 min-h-11 w-full rounded-lg border bg-white px-2" value={effectiveKind} onChange={event => { setKind(event.target.value); setPage(1); }}>
        {entries.map(entry => <option key={entry.id} value={entry.id}>{entry.title}</option>)}
      </select></label>
      <label className="text-sm">เลขเอกสาร<Input className="mt-1 min-h-11" value={search} maxLength={100} onChange={event => setSearch(event.target.value)} /></label>
      <label className="text-sm">ตั้งแต่วันที่<Input className="mt-1 min-h-11" type="date" value={dates.date_from} onChange={event => setDates({ ...dates, date_from: event.target.value })} /></label>
      <label className="text-sm">ถึงวันที่<Input className="mt-1 min-h-11" type="date" min={dates.date_from || undefined} value={dates.date_to} onChange={event => setDates({ ...dates, date_to: event.target.value })} /></label>
      <Button className="min-h-11 self-end" disabled={!online || !branchId || Boolean(stationKey) || unsupported}>ค้นหารายการ</Button>
    </form>
    {!online ? <p role="status">ออฟไลน์ — เชื่อมต่อก่อนดูรายการเอกสาร</p>
      : !branchId ? <p role="status">กรุณาเลือกสาขาก่อนดูทะเบียนเอกสาร</p>
      : stationKey ? <p role="status">กรุณาเปลี่ยนเป็นบริบทระดับสาขา ไม่ใช่จุดขาย</p>
      : unsupported ? <p role="status">ทะเบียนจัดซื้อ Takeaway ยังไม่เชื่อมกับทะเบียนนี้</p>
      : mismatch ? <p role="alert">บริบทเอกสารไม่ตรงกับบัญชีที่ใช้งาน</p>
      : query.isError ? <div role="alert">ไม่สามารถอ่านทะเบียนได้ หรือไม่มีสิทธิ์ในบริบทนี้ <Button variant="outline" onClick={() => void query.refetch()}>ลองใหม่</Button></div>
      : query.isFetching ? <p role="status">กำลังอ่านทะเบียน…</p>
      : !query.data?.items.length ? <p role="status">ไม่พบรายการในสาขาและเงื่อนไขนี้</p>
      : <>
        <p className="mb-2 text-xs text-slate-500">แหล่งข้อมูล: {query.data.source === "purchase_operational" ? "ระบบจัดซื้อตามบริบท" : "ระบบบัญชีเดิม"} · สถานะและยอดตามต้นทาง ไม่คำนวณภาษีใหม่</p>
        <div className="overflow-x-auto"><table className="w-full min-w-[560px] text-left text-sm"><thead><tr><th className="p-2">เลขเอกสาร</th><th>วันที่</th><th>สถานะต้นทาง</th><th className="text-right">{effectiveKind === "wht_certificate" ? "ยอดหัก ณ ที่จ่าย" : "ยอดตามเอกสาร"}</th></tr></thead>
          <tbody>{query.data.items.map(row => <tr key={row.id} className="border-t"><td className="p-2 font-medium"><button type="button" className="min-h-11 text-teal-800 underline" onClick={() => setSelected({ id: row.id, kind: effectiveKind, scope })}>{row.number}</button></td><td>{row.document_date}</td><td>{row.status}</td><td className="text-right">{row.amount === null ? "—" : new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(Number(row.amount))}</td></tr>)}</tbody>
        </table></div>
      </>}
    {online && branchId && !stationKey && !unsupported && !mismatch && !query.isError && query.data ? <div className="mt-3 flex items-center justify-end gap-3"><Button variant="outline" disabled={page === 1 || query.isFetching} onClick={() => setPage(page - 1)}>ก่อนหน้า</Button><span>หน้า {page}</span><Button variant="outline" disabled={!query.data.has_more || query.isFetching} onClick={() => setPage(page + 1)}>ถัดไป</Button></div> : null}
    {selected && selected.scope === scope && selected.kind === effectiveKind && !stationKey && !mismatch ? <DocumentHistory key={`${scope}:${selected.kind}:${selected.id}`} kind={selected.kind} id={selected.id} online={online} onClose={() => setSelected(null)} /> : null}
  </section>;
}
