import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { isAxiosError } from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import DocumentHistory from "@/components/company/DocumentHistory";
import api from "@/lib/api";
import { useAuthStore } from "@/stores/auth.store";

type Doc = { id: string; kind: string; number: string; total_amount: string };
type Sale = { id: string; company_id: string; branch_id: string; status: string; description: string;
  buyer: { name: string }; due_date: string; total_amount: string; paid_amount: string; created_by: string;
  items: { name: string; quantity: string; total_amount: string; stocked: boolean }[]; documents?: Doc[] };
type Options = { customers: { id: string; name: string; code: string }[];
  products: { id: string; name: string; price: string; vat_type: string }[];
  locations: { id: string; name: string }[]; notice: string };
const states: Record<string, string> = { draft: "รออนุมัติ", approved: "อนุมัติแล้ว / รอส่งมอบ", invoiced: "แจ้งหนี้แล้ว",
  partial: "ชำระบางส่วน", paid: "ชำระครบ", cancelled: "ยกเลิก" };
const money = (v: string | number): string => new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(Number(v));
const control = "min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3 py-2";

export default function CreditSalesPage(): JSX.Element {
  const auth = useAuthStore();
  return <CreditSalesWorkspace key={`${auth.companyId}:${auth.branchId}:${auth.stationKey}:${auth.targetDatabase}:${auth.user?.id}`} />;
}

function CreditSalesWorkspace(): JSX.Element {
  const { companyId, branchId, stationKey, permissions, user } = useAuthStore();
  const can = (permission: string): boolean => permissions.includes("*") || permissions.includes(permission);
  const [online, setOnline] = useState(navigator.onLine);
  const [selected, setSelected] = useState<string | null>(null);
  const [document, setDocument] = useState<Doc | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [customer, setCustomer] = useState("");
  const [description, setDescription] = useState("");
  const [due, setDue] = useState("");
  const [lines, setLines] = useState([{ product_id: "", quantity: "1" }]);
  const [location, setLocation] = useState("");
  const [receiver, setReceiver] = useState("");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("bank_transfer");
  const [reference, setReference] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requests = useRef(new Map<string, string>());
  const pending = useRef(false);
  const allowed = Boolean(companyId && branchId && !stationKey && can("accounting.invoice.view"));
  useEffect(() => {
    const update = (): void => setOnline(navigator.onLine);
    window.addEventListener("online", update); window.addEventListener("offline", update);
    return () => { window.removeEventListener("online", update); window.removeEventListener("offline", update); };
  }, []);
  const list = useQuery({ queryKey: ["credit-sales", companyId, branchId, page],
    queryFn: async () => (await api.get<{ data: { items: Sale[]; has_more: boolean } }>("/company/credit-sales", { params: { page } })).data.data,
    enabled: allowed && online, retry: false, gcTime: 0 });
  const options = useQuery({ queryKey: ["credit-options", companyId, branchId, search],
    queryFn: async () => (await api.get<{ data: Options }>("/company/credit-sales/options", { params: { search } })).data.data,
    enabled: allowed && online, retry: false, gcTime: 0 });
  const detail = useQuery({ queryKey: ["credit-detail", companyId, branchId, selected],
    queryFn: async () => (await api.get<{ data: Sale }>(`/company/credit-sales/${selected}`)).data.data,
    enabled: allowed && online && Boolean(selected), retry: false, gcTime: 0 });
  const sale = detail.data?.company_id === companyId && detail.data.branch_id === branchId ? detail.data : undefined;
  const disabled = busy || !online || list.isFetching || detail.isFetching || Boolean(list.error || detail.error);

  async function submit(action: string): Promise<void> {
    if (pending.current || disabled) return;
    if (action !== "create" && !reason.trim()) { setError("กรุณาระบุเหตุผล / หมายเหตุรายการ"); return; }
    if (action === "deliver" && !window.confirm("ส่งมอบเต็มใบ ตัดสต๊อก และลงลูกหนี้ใน UAT พร้อมกัน ยืนยันหรือไม่?")) return;
    if (action === "receive" && !window.confirm("ยืนยันว่าตรวจหลักฐานรับเงินจริงในชุดทดสอบแล้ว? ระบบนี้ไม่ได้ตรวจธนาคารอัตโนมัติ")) return;
    const path = action === "create" ? "/company/credit-sales" : `/company/credit-sales/${selected}/${action}`;
    const body = action === "create" ? { customer_id: customer, description, due_date: due, items: lines }
      : action === "deliver" ? { reason, location_id: location || null, received_by: receiver }
      : action === "receive" ? { reason, amount, method, reference } : { reason };
    const signature = JSON.stringify({ path, body });
    const key = requests.current.get(signature) ?? crypto.randomUUID();
    requests.current.set(signature, key); // Reuse on uncertain network outcomes, never blindly duplicate receipts.
    pending.current = true; setBusy(true); setError("");
    try {
      const response = await api.post<{ data: Sale }>(path, { ...body, request_key: key });
      const now = useAuthStore.getState();
      if (now.companyId !== companyId || now.branchId !== branchId) return;
      setSelected(response.data.data.id);
      if (action === "create") { setDescription(""); setLines([{ product_id: "", quantity: "1" }]); }
      if (action === "receive") { setAmount(""); setReference(""); }
      await list.refetch();
      if (selected === response.data.data.id) await detail.refetch();
    } catch (e) {
      const value = isAxiosError(e) ? e.response?.data?.detail : null;
      setError(typeof value === "string" ? value : "บันทึกไม่ได้ กรุณาตรวจข้อมูลหรือโหลดสถานะใหม่ก่อนลองคำขอเดิมอีกครั้ง");
    } finally { pending.current = false; setBusy(false); }
  }
  if (!allowed) return <p role="alert">ต้องมีสิทธิ์ดูใบแจ้งหนี้ และเลือกบริบทสาขา ไม่ใช่จุดขาย</p>;
  return <div className="space-y-5" data-testid="credit-sales">
    <header><h1 className="text-2xl font-bold">ขายเชื่อและลูกหนี้</h1><Link className="text-teal-700 underline" to="/company/documents">ศูนย์เอกสารและประวัติ</Link></header>
    <div className="rounded-xl bg-amber-50 p-4 text-sm text-amber-950">UAT เท่านั้น — ส่งมอบเต็มใบ → แจ้งหนี้ → วางบิล → รับเงินบางส่วน/ทั้งหมด ราคามาจากระบบและต้องมีคนอื่นอนุมัติ
      <br />ไม่ใช่เอกสารภาษีจริง ไม่ส่งยอดให้บริษัทผู้ซื้ออัตโนมัติ ไม่รวมโอนภายในบริษัท ส่งบางส่วน ลดหนี้ คืนเงิน หรือหัก ณ ที่จ่ายจากลูกค้า</div>
    {!online && <p role="status" className="rounded-xl bg-slate-100 p-4">ออฟไลน์ — หยุดบันทึกและซ่อนข้อมูลจนเชื่อมต่อใหม่</p>}
    {error && <p role="alert" className="rounded-xl bg-red-50 p-4 text-red-800">{error}</p>}
    {online && <>
      {(list.error || options.error) && <div role="alert">อ่านข้อมูลไม่สำเร็จหรือไม่มีสิทธิ์ <Button onClick={() => { void list.refetch(); void options.refetch(); }}>ลองใหม่</Button></div>}
      {list.isFetching && <p role="status">กำลังตรวจข้อมูลล่าสุด…</p>}
      {can("accounting.invoice.create") && options.data && !options.error && <form className="space-y-3 rounded-2xl border bg-white p-4" onSubmit={e => { e.preventDefault(); void submit("create"); }}>
        <h2 className="font-semibold">สร้างร่างใบเสนอราคา</h2>
        <div className="grid gap-3 md:grid-cols-3">
          <label>ลูกค้า<select aria-label="ลูกค้า" className={control} required value={customer} onChange={e => setCustomer(e.target.value)}><option value="">เลือกลูกค้า</option>{options.data.customers.map(c => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}</select></label>
          <label>ชื่องาน<Input className="min-h-11" required maxLength={500} value={description} onChange={e => setDescription(e.target.value)} /></label>
          <label>กำหนดชำระ<Input className="min-h-11" required type="date" value={due} onChange={e => setDue(e.target.value)} /></label>
        </div>
        <label className="block">ค้นหาสินค้า<Input className="min-h-11" value={search} onChange={e => setSearch(e.target.value)} /></label>
        {lines.map((line, index) => <div className="flex gap-2" key={index}>
          <select aria-label={`สินค้า ${index + 1}`} required className={control} value={line.product_id} onChange={e => setLines(lines.map((l, i) => i === index ? { ...l, product_id: e.target.value } : l))}>
            <option value="">เลือกสินค้า / บริการ</option>{options.data?.products.map(p => <option key={p.id} value={p.id}>{p.name} · {money(p.price)} ({p.vat_type})</option>)}
          </select>
          <Input aria-label={`จำนวน ${index + 1}`} className="min-h-11 max-w-28" required type="number" min="0.0001" step="0.0001" value={line.quantity} onChange={e => setLines(lines.map((l, i) => i === index ? { ...l, quantity: e.target.value } : l))} />
          <Button type="button" variant="outline" disabled={lines.length === 1} onClick={() => setLines(lines.filter((_, i) => i !== index))}>ลบ</Button>
        </div>)}
        <div className="flex flex-wrap gap-2"><Button type="button" variant="outline" disabled={lines.length >= 100} onClick={() => setLines([...lines, { product_id: "", quantity: "1" }])}>เพิ่มรายการ</Button><Button disabled={disabled || options.isFetching}>สร้างร่าง</Button></div>
        <p className="text-xs text-slate-500">{options.data.notice} · เพิ่มข้อมูลลูกค้าได้ในระบบลูกค้าเดิม</p>
      </form>}
      {!list.error && !list.isFetching && <section className="rounded-2xl border bg-white p-4"><h2 className="mb-3 font-semibold">รายการในสาขาที่เลือก</h2>
        {!list.data?.items.length && <p>ยังไม่มีรายการขายเชื่อ</p>}
        <div className="grid gap-3 md:grid-cols-2">{list.data?.items.map(s => <button type="button" key={s.id} className="min-h-24 rounded-xl border p-3 text-left hover:bg-slate-50" onClick={() => { setSelected(s.id); setDocument(null); setReason(""); setError(""); }}>
          <strong>{s.description}</strong><p>{s.buyer.name} · {states[s.status]}</p><p>{money(s.total_amount)} · ค้าง {money(Number(s.total_amount) - Number(s.paid_amount))}</p></button>)}</div>
        <div className="mt-3 flex gap-3"><Button variant="outline" disabled={page === 1} onClick={() => setPage(page - 1)}>ก่อนหน้า</Button><span>หน้า {page}</span><Button variant="outline" disabled={!list.data?.has_more} onClick={() => setPage(page + 1)}>ถัดไป</Button></div>
      </section>}
      {selected && (detail.isFetching ? <p role="status">กำลังตรวจรายละเอียด…</p> : detail.error ? <p role="alert">อ่านรายละเอียดไม่ได้ <Button onClick={() => void detail.refetch()}>ลองใหม่</Button></p> : sale && <section className="space-y-3 rounded-2xl border bg-white p-4">
        <h2 className="text-xl font-semibold">{sale.description}</h2><p>{sale.buyer.name} · {states[sale.status]} · กำหนดชำระ {sale.due_date}</p>
        {sale.items.map((i, n) => <p key={n}>{i.name} × {i.quantity} = {money(i.total_amount)} {i.stocked ? "(ตัดสต๊อก)" : "(ไม่ตัดสต๊อก)"}</p>)}
        <p className="font-semibold">รวม {money(sale.total_amount)} · รับแล้ว {money(sale.paid_amount)} · ค้าง {money(Number(sale.total_amount) - Number(sale.paid_amount))}</p>
        <label className="block">เหตุผล / หมายเหตุ<Input className="min-h-11" maxLength={1000} value={reason} onChange={e => setReason(e.target.value)} /></label>
        {sale.status === "draft" && <><p>ต้องให้พนักงานอีกคนที่มีสิทธิ์อนุมัติขายเชื่อเปิดรายการนี้</p><Button disabled={disabled || !can("accounting.invoice.approve") || sale.created_by === user?.id} onClick={() => void submit("approve")}>อนุมัติใบเสนอราคา</Button></>}
        {sale.status === "approved" && <div className="grid gap-3 md:grid-cols-3">
          <label>คลังส่งสินค้า<select className={control} value={location} onChange={e => setLocation(e.target.value)}><option value="">เลือกคลัง (บริการไม่ต้องเลือก)</option>{options.data?.locations.map(l => <option value={l.id} key={l.id}>{l.name}</option>)}</select></label>
          <label>ชื่อผู้รับมอบ<Input className="min-h-11" value={receiver} maxLength={200} onChange={e => setReceiver(e.target.value)} /></label>
          <Button className="self-end" disabled={disabled || !can("accounting.invoice.create") || (sale.items.some(i => i.stocked) && !can("inventory.stock.adjust"))} onClick={() => void submit("deliver")}>ส่งมอบและแจ้งหนี้</Button>
        </div>}
        {["invoiced", "partial"].includes(sale.status) && <>
          <Button disabled={disabled || !can("accounting.invoice.create") || sale.documents?.some(d => d.kind === "billing_notice")} onClick={() => void submit("bill")}>ออกใบวางบิล</Button>
          {can("accounting.payment.create") && <div className="grid gap-3 md:grid-cols-4">
            <label>ยอดรับเงิน<Input className="min-h-11" type="number" min="0.01" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} /></label>
            <label>วิธีรับ<select className={control} value={method} onChange={e => setMethod(e.target.value)}><option value="bank_transfer">โอนธนาคาร (ตรวจหลักฐานเอง)</option><option value="cash">เงินสด</option></select></label>
            <label>หลักฐาน / เลขอ้างอิง<Input className="min-h-11" value={reference} maxLength={200} onChange={e => setReference(e.target.value)} /></label>
            <Button className="self-end" disabled={disabled} onClick={() => void submit("receive")}>รับเงินและออกใบรับเงิน</Button>
          </div>}
        </>}
        {["draft", "approved"].includes(sale.status) && <Button variant="outline" disabled={disabled || !can("accounting.invoice.create")} onClick={() => { if (window.confirm("ยกเลิกรายการนี้?")) void submit("cancel"); }}>ยกเลิกก่อนส่งมอบ</Button>}
        <div className="flex flex-wrap gap-2">{sale.documents?.map(d => <Button variant="outline" key={d.id} onClick={() => setDocument(d)}>{d.number} · {money(d.total_amount)}</Button>)}</div>
      </section>)}
      {document && <DocumentHistory key={document.id} kind={document.kind} id={document.id} online={online} onClose={() => setDocument(null)} />}
    </>}
  </div>;
}
