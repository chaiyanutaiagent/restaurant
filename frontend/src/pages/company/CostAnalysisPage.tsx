import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import api from "@/lib/api";
import { useAuthStore } from "@/stores/auth.store";

type Value = string | number | null;
type Report = { company_id: string; branch_id: string; generated_at: string; start: string; end: string;
  posting_lines: number; summary: Record<string, Value>; scenario: Record<string, Value>;
  accounts: { id: string; code: string; name: string; group: string; debit: Value; credit: Value; amount: Value }[] };
const money = (value: Value): string => value === null ? "—" : new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(Number(value));
const groups: Record<string, string> = { revenue: "รายได้", cogs: "ต้นทุนขาย", other_expense: "ค่าใช้จ่ายอื่น" };
const day = (): string => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());

export default function CostAnalysisPage(): JSX.Element {
  const a = useAuthStore();
  return <Workspace key={`${a.companyId}:${a.branchId}:${a.brandId}:${a.stationKey}:${a.user?.id}:${a.permissions.join(",")}`} />;
}

function Workspace(): JSX.Element {
  const { companyId, branchId, stationKey, permissions } = useAuthStore();
  const [start, setStart] = useState(() => `${day().slice(0, 7)}-01`);
  const [end, setEnd] = useState(day);
  const [period, setPeriod] = useState({ start, end });
  const [fixed, setFixed] = useState("");
  const [variable, setVariable] = useState("");
  const [sales, setSales] = useState("");
  const [assumptions, setAssumptions] = useState<{ fixed_cost: string; variable_pct: string; target_sales: string } | null>(null);
  const [online, setOnline] = useState(navigator.onLine);
  const [clock, setClock] = useState(Date.now());
  const allowed = Boolean(companyId && branchId && !stationKey && (permissions.includes("*") || permissions.includes("accounting.report.view")));
  useEffect(() => {
    const update = (): void => setOnline(navigator.onLine);
    globalThis.addEventListener("online", update); globalThis.addEventListener("offline", update);
    const timer = globalThis.setInterval(() => setClock(Date.now()), 30000);
    return () => { globalThis.removeEventListener("online", update); globalThis.removeEventListener("offline", update); globalThis.clearInterval(timer); };
  }, []);
  const query = useQuery({ queryKey: ["cost-analysis", companyId, branchId, period, assumptions],
    queryFn: async () => (await api.get<{ data: Report }>("/company/cost-analysis", { params: { ...period, ...assumptions } })).data.data,
    enabled: allowed && online, retry: false, gcTime: 0, staleTime: 30000 });
  const report = query.data;
  const mismatch = report && (report.company_id !== companyId || report.branch_id !== branchId || report.start !== period.start || report.end !== period.end);
  const stale = report && (!Number.isFinite(Date.parse(report.generated_at)) || clock - Date.parse(report.generated_at) > 300000);
  const ready = report && online && !query.error && !query.isFetching && !mismatch && !stale;
  if (!allowed) return <p role="alert">กรุณาเลือกสาขาและใช้สิทธิ์ดูรายงานบัญชี ไม่รองรับบริบทจุดขาย</p>;
  return <div className="space-y-5" data-testid="cost-analysis">
    <header className="flex flex-wrap items-center justify-between gap-3"><h1 className="text-2xl font-bold">ต้นทุนและจุดคุ้มทุน</h1>
      <Button variant="outline" disabled={!online || query.isFetching} onClick={() => void query.refetch()}>อัปเดตข้อมูล</Button></header>
    <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-950">
      ผลจริงจากรายการที่ลงบัญชีแล้วในบัญชีกลาง เฉพาะบริษัทและสาขาที่เลือก ตามวันที่บัญชี รวมรายการกลับบัญชีหักกลบกัน
      <br />ไม่ใช่ยอดขายรวมทุกระบบ ไม่รวมรายการที่ยังไม่ส่งเข้าบัญชี หรือค่าใช้จ่ายส่วนกลางที่ยังไม่ปันส่วนมายังสาขา
      ต้นทุนสูตรอาหารเป็นประมาณการ จึงไม่รวมซ้ำกับต้นทุนขายจริง และไม่ถือว่าต้นทุนขายทั้งหมดเป็นต้นทุนผันแปร
      <br />ชื่อบัญชีและการจัดประเภทเป็นค่าปัจจุบัน รายงานไม่ใช่งบรับรองหรือจุดคุ้มทุนที่บัญชียืนยันแล้ว
    </div>
    <form className="flex flex-wrap items-end gap-3 rounded-xl border bg-white p-4" onSubmit={e => { e.preventDefault(); setPeriod({ start, end }); setAssumptions(null); }}>
      <label>ตั้งแต่<Input aria-label="ตั้งแต่" className="min-h-11" type="date" required value={start} onChange={e => setStart(e.target.value)} /></label>
      <label>ถึง<Input aria-label="ถึง" className="min-h-11" type="date" required min={start} value={end} onChange={e => setEnd(e.target.value)} /></label>
      <Button disabled={!online}>แสดงรายงาน</Button><span className="text-sm text-slate-500">ไม่เกิน 366 วันต่อครั้ง</span>
    </form>
    {!online ? <p role="status">ออฟไลน์ — ซ่อนยอดจนเชื่อมต่อและตรวจใหม่</p> : mismatch ? <p role="alert">บริบทไม่ตรงกับบริษัท สาขา หรือช่วงวันที่</p>
      : query.error ? <p role="alert">อ่านรายงานไม่ได้ ตรวจสิทธิ์และช่วงวันที่ แล้วกดอัปเดตข้อมูล</p>
      : query.isFetching ? <p role="status">กำลังอ่านข้อมูล…</p> : stale ? <p role="status">ข้อมูลเกิน 5 นาที กรุณากดอัปเดตข้อมูล</p> : null}
    {ready && <>
      <p className="text-sm text-slate-500">ช่วง {report.start} ถึง {report.end} · {report.posting_lines} บรรทัดบัญชี · ข้อมูล ณ {new Date(report.generated_at).toLocaleString("th-TH", { timeZone: "Asia/Bangkok" })} · THB</p>
      {!report.posting_lines && <p role="status" className="rounded-xl bg-amber-50 p-4">ไม่พบรายการรายได้หรือต้นทุนที่ลงบัญชีในช่วงนี้ ไม่ได้หมายความว่าไม่มีการขายหรือไม่มีต้นทุน</p>}
      <section aria-label="ผลจากบัญชี" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">{Object.entries({ revenue: "รายได้สุทธิตามบัญชี", cogs: "ต้นทุนขายตามบัญชี", gross_profit: "กำไรขั้นต้นตามบัญชี", other_expense: "ค่าใช้จ่ายอื่นตามบัญชี", posted_result: "ผลสุทธิตามรายการที่ลงบัญชี" }).map(([key, label]) =>
        <div key={key} className="rounded-xl border bg-white p-4"><p className="text-sm text-slate-500">{label}</p><strong className="text-xl">{money(report.summary[key])}</strong></div>)}</section>
      <p>อัตรากำไรขั้นต้น {report.summary.gross_margin_pct === null ? "คำนวณไม่ได้เมื่อรายได้ไม่เป็นบวก" : `${report.summary.gross_margin_pct}%`}</p>
      <section className="rounded-xl border bg-white p-4"><h2 className="mb-3 font-semibold">รายละเอียดบัญชี — ตรวจสอบที่มาของยอด</h2>
        <div className="overflow-x-auto"><table className="w-full min-w-[650px] text-left text-sm"><thead><tr>{["บัญชี", "ประเภท", "เดบิต", "เครดิต", "ยอดสุทธิ"].map(h => <th key={h} className="p-2">{h}</th>)}</tr></thead>
          <tbody>{report.accounts.map(r => <tr key={r.id} className="border-t"><td className="p-2">{r.code} · {r.name}</td><td>{groups[r.group]}</td><td>{money(r.debit)}</td><td>{money(r.credit)}</td><td>{money(r.amount)}</td></tr>)}</tbody></table></div>
      </section>
      <section className="space-y-4 rounded-xl border border-amber-200 bg-amber-50 p-4"><h2 className="font-semibold">จำลองจุดคุ้มทุน — ไม่บันทึกบัญชี</h2>
        <p className="text-sm">กรอกสมมติฐานสำหรับช่วงเวลาเดียวกับรายงาน ใช้ยอดขายและต้นทุนไม่รวม VAT ที่ขอคืนได้ ต้นทุนคงที่ต้องไม่ซ้ำกับต้นทุนที่คิดในอัตราผันแปร ไม่มีการกรอกสมมติฐานแทนให้จากบัญชี</p>
        <form className="grid gap-3 md:grid-cols-3" onSubmit={e => { e.preventDefault(); setAssumptions({ fixed_cost: fixed, variable_pct: variable, target_sales: sales }); }}>
          <label>ต้นทุนคงที่ต่อช่วง (บาท)<Input aria-label="ต้นทุนคงที่" type="number" required min="0" max="999999999999" step="0.01" value={fixed} onChange={e => setFixed(e.target.value)} /></label>
          <label>ต้นทุนผันแปรต่อยอดขาย (%)<Input aria-label="อัตราต้นทุนผันแปร" type="number" required min="0" max="100" step="0.0001" value={variable} onChange={e => setVariable(e.target.value)} /></label>
          <label>ยอดขายเป้าหมาย (บาท)<Input aria-label="ยอดขายเป้าหมาย" type="number" required min="0" max="999999999999" step="0.01" value={sales} onChange={e => setSales(e.target.value)} /></label>
          <Button className="min-h-11" disabled={!online}>คำนวณสมมติฐาน</Button>
        </form>
        {assumptions ? <div data-testid="simulation" className="space-y-2">
          <p>สมมติฐานที่คำนวณ: คงที่ {money(report.scenario.fixed_cost)} · ผันแปร {report.scenario.variable_pct}% · ยอดขาย {money(report.scenario.target_sales)}</p>
          <p className="font-semibold">ยอดขายคุ้มทุน: {money(report.scenario.break_even_sales)}</p>
          {report.scenario.break_even_sales === null && <p role="alert">อัตราผันแปร 100% ไม่มีกำไรส่วนเกินรองรับต้นทุนคงที่ จึงไม่แสดงจุดคุ้มทุน</p>}
          <p>ผลจำลองที่ยอดขายเป้าหมาย: {money(report.scenario.projected_result)}</p>
          <p>ส่วนต่างยอดขายเป้าหมายเทียบจุดคุ้มทุน: {money(report.scenario.margin_of_safety)}</p>
        </div> : <p>กรอกครบแล้วกดคำนวณ จึงจะแสดงผลจำลอง</p>}
        <p className="text-xs">สูตร: ยอดขายคุ้มทุน = ต้นทุนคงที่ ÷ (1 − อัตราต้นทุนผันแปร) · สมมติฐานไม่ถูกบันทึกเป็นธุรกรรมหรือแผนงบประมาณ</p>
      </section>
    </>}
  </div>;
}
