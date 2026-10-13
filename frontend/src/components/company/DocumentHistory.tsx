import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import api from "@/lib/api";
import { useAuthStore } from "@/stores/auth.store";

type History = {
  company_id: string; branch_id: string; number: string; status: string; original_available: boolean;
  snapshot: null | { captured_at: string; captured_by: string; sha256: string; template_version: string };
  events: { sequence: number; action: string; actor_id: string; occurred_at: string; reason: string | null; payload: object }[];
  legacy_audit: { action: string; actor_id: string; occurred_at: string }[];
  has_more: boolean; correction_policy: string;
};
const labels: Record<string, string> = { draft_created: "สร้างร่าง", before_revision: "ร่างก่อนแก้ไข", draft_revised: "แก้ไขร่าง",
  submitted: "ส่งอนุมัติ", issued: "อนุมัติ / บันทึกหลักฐาน", cancelled: "ยกเลิก", credit_note_linked: "เชื่อมใบลดหนี้",
  print_original: "ขอดาวน์โหลดต้นฉบับ", print_copy: "ขอดาวน์โหลดสำเนา" };

export default function DocumentHistory({ kind, id, online, onClose }: { kind: string; id: string; online: boolean; onClose: () => void }): JSX.Element {
  const { companyId, branchId, brandId, stationKey, targetDatabase, permissions } = useAuthStore();
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const query = useQuery({
    queryKey: ["document-history", companyId, branchId, brandId, stationKey, targetDatabase, kind, id, page],
    queryFn: async () => (await api.get<{ data: History }>(`/company/documents/${kind}/${id}/history`, { params: { page } })).data.data,
    enabled: online && Boolean(branchId) && !stationKey, retry: false, gcTime: 0,
  });
  const data = query.data;
  const scopeMatches = data?.company_id === companyId && data?.branch_id === branchId;
  async function replacePo(): Promise<void> {
    const reason = window.prompt("เหตุผลสร้างร่างทดแทนใบสั่งซื้อที่ยกเลิก (ต้องส่งอนุมัติใหม่)");
    if (!reason?.trim() || busy || !online || !scopeMatches) return;
    setBusy(true); setError("");
    try {
      await api.post(`/purchase/orders/${id}/replacement`, { reason: reason.trim() });
      void query.refetch();
    } catch { setError("สร้างร่างทดแทนไม่ได้ หรือมีร่างอยู่แล้ว กรุณาดูเลขอ้างอิงในประวัติ"); }
    finally { setBusy(false); }
  }
  async function download(variant: "original" | "copy"): Promise<void> {
    if (!online || !scopeMatches || busy) return;
    if (variant === "original" && !window.confirm("ขอต้นฉบับได้ครั้งเดียว หลังจากนี้ใช้สำเนา แม้ดาวน์โหลดครั้งนี้ไม่สำเร็จ ดำเนินการหรือไม่?")) return;
    const scope = { companyId, branchId, brandId, stationKey, targetDatabase };
    setBusy(true); setError("");
    try {
      const response = await api.post(`/company/documents/${kind}/${id}/print`, { variant }, { responseType: "blob" });
      const now = useAuthStore.getState();
      if (Object.entries(scope).some(([key, value]) => now[key as keyof typeof scope] !== value)) return;
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `${data?.number ?? id}-${variant}.${String(response.headers["content-type"]).includes("application/pdf") ? "pdf" : "html"}`;
      anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      setError("ดาวน์โหลดไม่สำเร็จ หรือออกต้นฉบับไปแล้ว กรุณาตรวจประวัติแล้วเลือกสำเนา ไม่ต้องออกธุรกรรมใหม่");
    } finally { setBusy(false); void query.refetch(); }
  }
  return <section className="my-4 rounded-xl border border-teal-200 bg-slate-50 p-4" aria-label="ประวัติเอกสาร">
    <div className="flex items-center justify-between gap-2"><h3 className="font-bold">ประวัติและหลักฐานเอกสาร</h3><Button variant="outline" onClick={onClose}>ปิดประวัติ</Button></div>
    {!online ? <p role="status">ออฟไลน์ — ไม่แสดงหลักฐานที่อาจล้าสมัย</p> : query.isFetching ? <p role="status">กำลังอ่านประวัติ…</p>
      : query.isError || !scopeMatches ? <p role="alert">อ่านหลักฐานไม่ได้ หรือบริบทไม่ตรง กรุณาตรวจสิทธิ์และสาขา</p> : data ? <>
        <p className="my-2 font-medium">{data.number} · สถานะปัจจุบัน {data.status}</p>
        <p className="text-sm text-slate-600">{data.correction_policy}</p>
        {kind === "purchase_order" && data.status === "cancelled" && (permissions.includes("*") || permissions.includes("inventory.purchase.create")) ? <Button className="my-2" variant="outline" disabled={busy} onClick={() => void replacePo()}>สร้างร่างใบสั่งซื้อทดแทน</Button> : null}
        {data.snapshot ? <div className="my-3 space-y-2 text-sm">
          <p>เก็บหลักฐานเมื่อ {new Date(data.snapshot.captured_at).toLocaleString("th-TH")} · ผู้บันทึก/อนุมัติ {data.snapshot.captured_by}</p>
          <p className="break-all text-xs">{data.snapshot.template_version} · SHA-256 {data.snapshot.sha256}</p>
          <p>ต้นฉบับและสำเนามาจากหลักฐานเดียวกัน ไม่สร้างบัญชีซ้ำ และไม่ใช่การรับรองรูปแบบภาษี</p>
          <div className="flex flex-wrap gap-2"><Button disabled={busy || !data.original_available} onClick={() => void download("original")}>ดาวน์โหลดต้นฉบับครั้งแรก</Button><Button variant="outline" disabled={busy} onClick={() => void download("copy")}>ดาวน์โหลดสำเนา</Button></div>
        </div> : <p className="my-3 rounded-lg bg-amber-50 p-3 text-sm">เอกสารเก่าหรือฉบับร่าง — ไม่มีหลักฐาน ณ วันออก ไม่สร้างหลักฐานย้อนหลัง กรุณาเปิดระบบต้นทาง</p>}
        {error ? <p role="alert" className="text-red-700">{error}</p> : null}
        {data.events.length ? <ol className="my-3 space-y-3">{data.events.map(event => <li key={event.sequence} className="rounded-lg border bg-white p-3 text-sm">
          <strong>#{event.sequence} {labels[event.action] ?? event.action}</strong> · {new Date(event.occurred_at).toLocaleString("th-TH")}
          <p className="break-all text-xs text-slate-600">ผู้ดำเนินการ: {event.actor_id}</p>{event.reason ? <p>เหตุผล: {event.reason}</p> : null}
          <details><summary className="cursor-pointer py-2">ข้อมูลที่บันทึกในรุ่นนี้</summary><pre className="max-h-72 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(event.payload, null, 2)}</pre></details>
        </li>)}</ol> : <p className="my-3 text-sm">ยังไม่มีเหตุการณ์ในทะเบียนใหม่</p>}
        <div className="flex gap-2"><Button variant="outline" disabled={page === 1} onClick={() => setPage(page - 1)}>ประวัติก่อนหน้า</Button><Button variant="outline" disabled={!data.has_more} onClick={() => setPage(page + 1)}>ประวัติถัดไป</Button></div>
        {data.legacy_audit.length ? <details className="mt-3 text-sm"><summary>บันทึกระบบเดิม (ไม่ใช่ snapshot ย้อนหลัง)</summary>{data.legacy_audit.map((item, index) => <p key={index} className="break-all">{item.occurred_at} · {item.action} · {item.actor_id}</p>)}</details> : null}
      </> : null}
  </section>;
}
