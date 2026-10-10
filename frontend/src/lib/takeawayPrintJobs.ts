import { db } from "@/lib/db";
import { takeawayApi, type TakeawayReceipt } from "@/lib/takeawayApi";
import { printTakeawayBatch, takeawayCutterCapability } from "@/lib/takeawayPrinter";
import { useAuthStore } from "@/stores/auth.store";

export type PrintCopy = "customer" | "preparation";
export type StorePrintJob = {
  key: string; id: string; scope: string; clientSaleId: string | null;
  receipt: TakeawayReceipt; copies: PrintCopy[]; confirmed: PrintCopy[]; audited: PrintCopy[];
  missing: PrintCopy[] | null; state: "prepared" | "sending" | "inspect" | "recovery" | "complete";
  attemptId?: string; error?: string; createdAt: number;
};
let transporting = false;
let syncing = false;
const changing = new Set<string>();

function scope(): string {
  const a = useAuthStore.getState();
  if (!a.accessToken || !a.companyId || !a.brandId || !a.branchId || !a.user?.id || !a.hasPermission("takeaway.sale.create")) throw new Error("ไม่มีสิทธิ์พิมพ์บิลของสาขานี้");
  const claim = JSON.parse(atob(a.accessToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
  if (claim.exp && claim.exp * 1000 <= Date.now()) throw new Error("สิทธิ์หมดอายุ กรุณาออนไลน์และเข้าสู่ระบบใหม่");
  return [a.companyId, a.brandId, a.branchId, a.user.id].join(":");
}
function changed(): void { window.dispatchEvent(new Event("takeaway-print-changed")); }
async function save(job: StorePrintJob): Promise<void> {
  if (scope() !== job.scope) throw new Error("บริบทสาขาหรือผู้ใช้เปลี่ยน ไม่ส่งงานพิมพ์");
  await db.offlineSettings.put({ key: job.key, value: JSON.stringify(job) }); changed();
}
async function read(key: string): Promise<StorePrintJob> {
  const row = await db.offlineSettings.get(key);
  const job: StorePrintJob | undefined = row ? JSON.parse(row.value) : undefined;
  if (!job || job.scope !== scope()) throw new Error("ไม่พบบิลในขอบเขตผู้ใช้นี้");
  return job;
}
export async function listStorePrintJobs(): Promise<StorePrintJob[]> {
  const current = scope();
  const rows = await db.offlineSettings.where("key").startsWith(`takeaway.print:${current}:`).toArray();
  return rows.map(row => JSON.parse(row.value) as StorePrintJob).filter(job => job.scope === current).sort((a, b) => b.createdAt - a.createdAt);
}

async function transmit(job: StorePrintJob, copies: PrintCopy[]): Promise<void> {
  if (!await takeawayCutterCapability()) {
    job.state = "recovery"; job.missing = copies;
    job.error = "ยังไม่ยืนยัน Auto Cutter: ยังไม่ได้ส่งกระดาษ ไปตั้งค่าเครื่องพิมพ์และทดสอบตัดขาดจริงก่อน";
    await save(job); return;
  }
  job.state = "sending"; job.attemptId = crypto.randomUUID(); job.error = undefined;
  await save(job); // Persist intent BEFORE handing any bytes to native.
  try {
    await printTakeawayBatch(job.receipt, copies, job.attemptId);
  } catch (error) {
    job.error = `${error instanceof Error ? error.message : "ไม่ทราบผล Bluetooth"} — ตรวจดูกระดาษก่อนกู้คืน ระบบไม่พิมพ์ซ้ำอัตโนมัติ`;
  }
  job.state = "inspect"; job.missing = null;
  await save(job);
}

export async function startStorePrint(receipt: TakeawayReceipt, clientSaleId: string | null, copies: PrintCopy[] = ["customer", "preparation"], initial = false): Promise<void> {
  if (transporting) return;
  transporting = true;
  try {
    const current = scope();
    // Reprints must be re-authorized server-side; a caller cannot inject a foreign receipt.
    if (!clientSaleId) {
      receipt = (await takeawayApi.receipt(receipt.order_id)).data.data;
    } else {
      const sale = await db.takeawayPendingSales.get(clientSaleId);
      if (!sale || [sale.company_id, sale.brand_id, sale.branch_id, sale.user_id].join(":") !== current) throw new Error("ไม่พบบิลในสาขานี้");
      receipt = sale.server_receipt ?? sale.local_receipt;
      if (!initial && sale.status === "synced" && sale.server_order && navigator.onLine) {
        receipt = (await takeawayApi.receipt(sale.server_order.id)).data.data;
      }
    }
    const id = crypto.randomUUID();
    const key = `takeaway.print:${current}:${initial ? `sale:${clientSaleId}` : id}`;
    const job: StorePrintJob = { key, id, scope: current, receipt, clientSaleId, copies, confirmed: [], audited: [], missing: null, state: "prepared", createdAt: Date.now() };
    const inserted = await db.transaction("rw", db.offlineSettings, async () => {
      if (await db.offlineSettings.get(key)) return false;
      await db.offlineSettings.put({ key, value: JSON.stringify(job) }); return true;
    });
    if (!inserted) { changed(); return; } // Never resume an interrupted initial batch automatically.
    await transmit(job, copies);
  } finally { transporting = false; changed(); }
}

export async function recoverStorePrint(key: string): Promise<void> {
  if (transporting || changing.has(key)) return;
  transporting = true; changing.add(key);
  try {
    const job = await read(key);
    if (job.state !== "recovery" || !job.missing?.length) throw new Error("ต้องยืนยันว่าใบใดขาดก่อนพิมพ์ซ้ำ");
    await transmit(job, job.missing.filter(copy => !job.confirmed.includes(copy)));
  } finally { transporting = false; changing.delete(key); changed(); }
}

export async function confirmStorePrint(key: string, missing: PrintCopy[]): Promise<void> {
  if (transporting || changing.has(key)) return;
  changing.add(key);
  try {
    const job = await read(key);
    if (job.state === "complete") return;
    job.missing = job.copies.filter(copy => missing.includes(copy) && !job.confirmed.includes(copy));
    job.confirmed = job.copies.filter(copy => job.confirmed.includes(copy) || !missing.includes(copy));
    job.state = job.missing.length ? "recovery" : "complete";
    await save(job);
  } finally { changing.delete(key); }
  await syncStorePrintAudits();
}

export async function syncStorePrintAudits(): Promise<void> {
  if (syncing || !navigator.onLine) return;
  syncing = true;
  try {
    for (const job of await listStorePrintJobs()) {
      if (changing.has(job.key)) continue;
      let orderId = job.receipt.order_id;
      if (job.clientSaleId) {
        const sale = await db.takeawayPendingSales.get(job.clientSaleId);
        if (!sale || [sale.company_id, sale.brand_id, sale.branch_id, sale.user_id].join(":") !== job.scope || sale.status !== "synced" || !sale.server_order) continue;
        orderId = sale.server_order.id;
      }
      if (orderId.startsWith("local:")) continue;
      for (const copy of job.confirmed.filter(c => !job.audited.includes(c))) {
        try {
          // Both copies share one batch UUID. Server derives a unique key per copy.
          await takeawayApi.markReceiptPrinted(orderId, copy, `batch:${job.id}:${copy}`, job.id);
          const latest = await read(job.key);
          if (!latest.audited.includes(copy)) latest.audited.push(copy);
          await save(latest);
        } catch { break; } // Audit retries only. NEVER resend paper or create a sale.
      }
    }
  } finally { syncing = false; }
}

export async function assertPrintJobsSettled(): Promise<void> {
  if (transporting || (await listStorePrintJobs()).some(j => j.state !== "complete" || j.confirmed.some(c => !j.audited.includes(c)))) {
    throw new Error("มีงานพิมพ์รอตรวจหรือ audit ค้างส่ง ไปที่บิลล่าสุด / พิมพ์ซ้ำก่อนออกจากระบบ");
  }
}

export function isStorePrintTransporting(): boolean { return transporting; }
