import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { takeawayApi, type TakeawayReceipt } from "@/lib/takeawayApi";
import { listStorePrintJobs, startStorePrint, type PrintCopy } from "@/lib/takeawayPrintJobs";
import { useAuthStore } from "@/stores/auth.store";
import { db } from "@/lib/db";

export default function TakeawayRecentBillsPage(): JSX.Element {
  const a = useAuthStore(); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const query = useQuery({ queryKey: ["takeaway", "receipts", a.companyId, a.brandId, a.branchId, a.user?.id], networkMode: "always", refetchInterval: 5000,
    queryFn: async () => {
      const jobs = await listStorePrintJobs();
      // Resolve offline local IDs after sync without rewriting the immutable print snapshot.
      for (const job of jobs) {
        if (!job.clientSaleId) continue;
        const sale = await db.takeawayPendingSales.get(job.clientSaleId);
        if (sale && [sale.company_id, sale.brand_id, sale.branch_id, sale.user_id].join(":") === job.scope && sale.server_receipt) job.receipt = sale.server_receipt;
      }
      let receipts: TakeawayReceipt[] = []; let offline = false;
      try { receipts = (await takeawayApi.receipts()).data.data; } catch { offline = true; }
      const seen = new Set(receipts.map(r => r.order_id));
      for (const job of jobs) if (!seen.has(job.receipt.order_id)) { receipts.push(job.receipt); seen.add(job.receipt.order_id); }
      return { receipts, jobs, offline };
    } });
  async function reprint(receipt: TakeawayReceipt, copies: PrintCopy[]) {
    if (copies.length === 2 && !window.confirm("พิมพ์ชุด 2 ใบซ้ำ? อาจได้กระดาษซ้ำทั้งใบลูกค้าและใบเตรียมสินค้า")) return;
    setBusy(true); setError("");
    try {
      const local = query.data?.jobs.find(j => j.receipt.order_id === receipt.order_id);
      await startStorePrint(receipt, local?.clientSaleId ?? null, copies);
    } catch (e) { setError(e instanceof Error ? e.message : "พิมพ์ไม่ได้"); }
    finally { setBusy(false); }
  }
  return <section className="space-y-4"><h1 className="text-xl font-black">บิลล่าสุด / พิมพ์ซ้ำ</h1>
    <p className="text-sm text-slate-500">ประวัติการยืนยันกระดาษ แยกใบลูกค้าและใบเตรียมสินค้า ไม่มีการพิมพ์อัตโนมัติเมื่อเปิดหน้านี้</p>
    {query.isLoading ? <p>กำลังโหลดบิล…</p> : null}
    {error || query.isError ? <p role="alert" className="text-red-700">{error || "ไม่มีสิทธิ์หรือโหลดบิลไม่สำเร็จ"}</p> : null}
    {query.data?.offline ? <p role="status" className="rounded-lg bg-amber-50 p-3">ติดต่อเซิร์ฟเวอร์ไม่ได้ แสดงเฉพาะบิลในเครื่องของผู้ใช้และสาขานี้</p> : null}
    {query.data?.receipts.length === 0 ? <p>ยังไม่มีบิล</p> : null}
    {query.data?.receipts.map(receipt => {
      const jobs = query.data.jobs.filter(j => j.receipt.order_id === receipt.order_id);
      return <article key={receipt.id} className="space-y-3 rounded-2xl border bg-white p-4">
        <h2 className="font-black">คิว {receipt.payload.queue_number ?? "OFF"} · {receipt.payload.order_number || receipt.receipt_number}</h2>
        <p className="text-sm">{new Date(receipt.issued_at).toLocaleString("th-TH")}</p>
        {(["customer", "preparation"] as const).map(copy => <p key={copy} className="text-sm">{copy === "customer" ? "ใบลูกค้า" : "ใบเตรียมสินค้า"}: ยืนยันบน server {receipt.payload.print_copies?.[copy]?.count ?? 0} ครั้ง{jobs.some(j => j.confirmed.includes(copy) && !j.audited.includes(copy)) ? " · ยืนยันในเครื่อง รอส่ง audit" : ""}{jobs.some(j => j.copies.includes(copy) && !j.confirmed.includes(copy)) ? " · รอตรวจกระดาษ/กู้คืน" : ""}</p>)}
        {!receipt.payload.print_copies && receipt.print_count > 0 ? <p className="text-sm text-amber-700">มีประวัติพิมพ์เดิม {receipt.print_count} ครั้ง ยังไม่แยกสถานะสองใบ</p> : null}
        <div className="flex flex-wrap gap-2">
          <button disabled={busy} className="rounded-lg border p-3 disabled:opacity-40" onClick={() => void reprint(receipt, ["customer"])}>พิมพ์ซ้ำใบลูกค้า</button>
          <button disabled={busy} className="rounded-lg border p-3 disabled:opacity-40" onClick={() => void reprint(receipt, ["preparation"])}>พิมพ์ซ้ำใบเตรียมสินค้า</button>
          <button disabled={busy} className="rounded-lg bg-slate-950 p-3 text-white disabled:opacity-40" onClick={() => void reprint(receipt, ["customer", "preparation"])}>พิมพ์ชุด 2 ใบ</button>
        </div>
      </article>;
    })}
  </section>;
}
