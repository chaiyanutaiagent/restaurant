import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { confirmStorePrint, recoverStorePrint, listStorePrintJobs, syncStorePrintAudits, isStorePrintTransporting } from "@/lib/takeawayPrintJobs";
import { useAuthStore } from "@/stores/auth.store";

export default function StorePrintRecovery(): JSX.Element | null {
  const a = useAuthStore(); const qc = useQueryClient();
  const [error, setError] = useState("");
  const act = async (action: () => Promise<void>): Promise<void> => {
    setError(""); try { await action(); } catch (e) { setError(e instanceof Error ? e.message : "บันทึกผลพิมพ์ไม่ได้"); }
  };
  const query = useQuery({ queryKey: ["takeaway-print-jobs", a.companyId, a.brandId, a.branchId, a.user?.id], queryFn: listStorePrintJobs, networkMode: "always", refetchInterval: 1000, enabled: a.hasPermission("takeaway.sale.create") });
  useEffect(() => {
    const update = (): void => { void qc.invalidateQueries({ queryKey: ["takeaway-print-jobs"] }); };
    const sync = (): void => { void syncStorePrintAudits().catch(() => undefined); };
    window.addEventListener("takeaway-print-changed", update); window.addEventListener("online", sync);
    const timer = window.setInterval(sync, 5000); sync();
    return () => { window.removeEventListener("takeaway-print-changed", update); window.removeEventListener("online", sync); clearInterval(timer); };
  }, [qc, a.companyId, a.brandId, a.branchId, a.user?.id]);
  const job = query.data?.find(row => row.state !== "complete");
  useEffect(() => { if (job) document.getElementById("store-print-recovery")?.scrollIntoView({ behavior: "smooth", block: "center" }); }, [job?.key, job?.state]);
  if (!job) return null;
  const busy = isStorePrintTransporting();
  const pending = job.copies.filter(copy => !job.confirmed.includes(copy));
  return <section id="store-print-recovery" role="dialog" aria-label="ตรวจผลพิมพ์" className="mx-auto my-3 max-w-5xl rounded-2xl border-2 border-amber-400 bg-amber-50 p-4">
    {error ? <p role="alert" className="text-red-700">{error}</p> : null}
    <h2 className="text-lg font-black">{busy ? "กำลังส่งชุดพิมพ์…" : "ตรวจดูกระดาษก่อนยืนยัน"}</h2>
    <p>คิว {job.receipt.payload.queue_number ?? "OFF"} · {job.receipt.payload.order_number}</p>
    <p className="my-2 text-sm">ต้องตัดขาดเป็นใบจริง ไม่ใช่เพียงเว้นบรรทัด การส่ง Bluetooth ไม่ยืนยันว่ากระดาษออกครบ</p>
    {job.error ? <p role="alert" className="my-2 text-red-700">{job.error}</p> : null}
    {!busy && job.state !== "recovery" ? <div className="flex flex-wrap gap-2">
      <button className="rounded-lg bg-emerald-700 p-3 text-white" onClick={() => void act(() => confirmStorePrint(job.key, []))}>{job.copies.length === 2 ? "กระดาษออกครบ 2 ใบ" : "กระดาษออกครบ 1 ใบ"}</button>
      {pending.includes("customer") ? <button className="rounded-lg border bg-white p-3" onClick={() => void act(() => confirmStorePrint(job.key, ["customer"]))}>ขาดใบลูกค้า</button> : null}
      {pending.includes("preparation") ? <button className="rounded-lg border bg-white p-3" onClick={() => void act(() => confirmStorePrint(job.key, ["preparation"]))}>ขาดใบเตรียมสินค้า</button> : null}
      {pending.length === 2 ? <button className="rounded-lg border bg-white p-3" onClick={() => void act(() => confirmStorePrint(job.key, pending))}>ไม่ออกทั้งสองใบ</button> : null}
    </div> : null}
    {!busy && job.state === "recovery" ? <div className="mt-3"><p>ตรวจเครื่อง/กระดาษก่อนสั่งใหม่ ไม่มีการพิมพ์ซ้ำอัตโนมัติ</p><button className="mt-2 rounded-lg bg-slate-950 p-3 text-white" onClick={() => void act(() => recoverStorePrint(job.key))}>พิมพ์เฉพาะที่ขาด: {job.missing?.map(c => c === "customer" ? "ใบลูกค้า" : "ใบเตรียมสินค้า").join(" + ")}</button></div> : null}
  </section>;
}
