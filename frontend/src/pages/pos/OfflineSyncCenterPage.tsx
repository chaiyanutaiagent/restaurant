import { liveQuery } from "dexie";
import { AlertTriangle, ArrowLeft, CloudUpload, RefreshCw, ShieldCheck, Wifi, WifiOff } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";
import type { RestaurantPendingOrder } from "@/lib/db";
import {
  getRestaurantOutboxSummary,
  inquireRestaurantOperation,
  listRestaurantOutbox,
  retryRestaurantNeedsReview,
  syncRestaurantPendingOrders,
  type RestaurantOutboxSummary,
} from "@/lib/restaurantOffline";
import { useOnlineStatus } from "@/lib/syncService";

const EMPTY_SUMMARY: RestaurantOutboxSummary = {
  pending: 0, syncing: 0, acknowledged: 0, reconciled: 0,
  needsReview: 0, rejected: 0, quarantined: 0, unknown: 0,
};

const STATUS_LABEL: Record<string, string> = {
  pending_sync: "รอส่ง", syncing: "กำลังส่ง", server_acknowledged: "Server รับแล้ว",
  reconciled: "กระทบยอดแล้ว", needs_review: "ต้องตรวจสอบ", rejected: "ถูกปฏิเสธ",
  quarantined: "กักรายการ", unknown: "ยังไม่ทราบผล",
};

export default function OfflineSyncCenterPage(): JSX.Element {
  const { brandSlug } = useParams<{ brandSlug?: string }>();
  const isOnline = useOnlineStatus();
  const { toast } = useToast();
  const [rows, setRows] = useState<RestaurantPendingOrder[]>([]);
  const [summary, setSummary] = useState<RestaurantOutboxSummary>(EMPTY_SUMMARY);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const subscription = liveQuery(async () => ({
      rows: await listRestaurantOutbox(brandSlug),
      summary: await getRestaurantOutboxSummary(brandSlug),
    })).subscribe({
      next: (value) => { setRows(value.rows); setSummary(value.summary); },
      error: () => undefined,
    });
    return () => subscription.unsubscribe();
  }, [brandSlug]);

  const activeCount = useMemo(() => summary.pending + summary.syncing + summary.acknowledged + summary.unknown, [summary]);
  const backPath = brandSlug ? `/store/${brandSlug}/orders` : "/counter/orders";

  async function syncNow(): Promise<void> {
    setBusy(true);
    try {
      await syncRestaurantPendingOrders(brandSlug);
      toast({ title: "ตรวจและซิงก์ Outbox แล้ว", description: "รายการ Unknown ถูก inquiry ก่อนเสมอ" });
    } catch (error) {
      toast({ title: "ซิงก์ไม่สำเร็จ", description: error instanceof Error ? error.message : "โปรดลองใหม่", variant: "destructive" });
    } finally { setBusy(false); }
  }

  return (
    <main className="min-h-screen bg-slate-50 p-4 text-slate-950 md:p-6">
      <div className="mx-auto max-w-6xl space-y-4">
        <header className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border bg-white p-4 shadow-sm">
          <div className="flex items-center gap-3">
            <Button asChild variant="outline" size="icon" className="h-11 w-11"><Link to={backPath}><ArrowLeft className="h-5 w-5" /></Link></Button>
            <div><h1 className="text-xl font-black">Offline Sync Center</h1><p className="text-sm text-slate-500">Outbox เข้ารหัส · inquiry ก่อน replay · ไม่มีปุ่มลบรายการ</p></div>
          </div>
          <div className="flex items-center gap-2">
            <Badge className={isOnline ? "bg-emerald-600" : "bg-amber-600"}>{isOnline ? <Wifi className="mr-1 h-3.5 w-3.5" /> : <WifiOff className="mr-1 h-3.5 w-3.5" />}{isOnline ? "ออนไลน์" : "ออฟไลน์"}</Badge>
            <Button className="h-11" disabled={!isOnline || busy} onClick={() => void syncNow()}><RefreshCw className={`mr-2 h-4 w-4 ${busy ? "animate-spin" : ""}`} />ตรวจและซิงก์</Button>
          </div>
        </header>

        <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            ["รอผล", activeCount, "text-blue-700"], ["ต้องตรวจ", summary.needsReview, "text-orange-700"],
            ["กักไว้", summary.quarantined, "text-red-700"], ["สำเร็จ", summary.reconciled, "text-emerald-700"],
          ].map(([label, value, color]) => <div key={String(label)} className="rounded-2xl border bg-white p-4"><p className="text-sm text-slate-500">{label}</p><p className={`mt-1 text-3xl font-black ${color}`}>{value}</p></div>)}
        </section>

        {(summary.unknown > 0 || summary.quarantined > 0) && <div role="alert" className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-amber-950"><p className="flex items-center gap-2 font-bold"><AlertTriangle className="h-5 w-5" />มีรายการที่ห้ามยิงซ้ำอัตโนมัติโดยไม่ตรวจ</p><p className="mt-1 text-sm">Unknown จะ inquiry ด้วย Client Operation ID เดิม ส่วน Quarantined ต้องให้ผู้ดูแลตรวจหลักฐานและความถูกต้อง</p></div>}

        <section className="overflow-hidden rounded-2xl border bg-white shadow-sm">
          <div className="border-b p-4"><h2 className="font-bold">รายการในเครื่อง</h2></div>
          {rows.length === 0 ? <div className="p-12 text-center text-slate-500"><ShieldCheck className="mx-auto mb-3 h-10 w-10" />ยังไม่มีรายการ Outbox</div> : (
            <div className="divide-y">
              {rows.map((row) => <article key={row.client_order_id} className="grid gap-3 p-4 md:grid-cols-[1fr_auto] md:items-center">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2"><Badge variant="outline">{STATUS_LABEL[row.status] ?? row.status}</Badge><span className="font-mono text-xs text-slate-500">Seq {row.sequence_no ?? "-"}</span></div>
                  <p className="mt-2 truncate font-mono text-sm">{row.client_operation_id ?? row.client_order_id}</p>
                  <p className="mt-1 text-xs text-slate-500">พยายาม {row.attempts} ครั้ง · {new Date(row.created_at).toLocaleString("th-TH")}</p>
                  {row.last_error && <p className="mt-2 text-sm text-red-700">{row.last_error_code ? `${row.last_error_code}: ` : ""}{row.last_error}</p>}
                </div>
                <div className="flex gap-2">
                  {row.status === "unknown" && <Button variant="outline" className="h-11" disabled={!isOnline} onClick={() => void inquireRestaurantOperation(row.client_order_id)}>Inquiry</Button>}
                  {row.status === "needs_review" && <Button variant="outline" className="h-11" disabled={!isOnline} onClick={() => void retryRestaurantNeedsReview(brandSlug)}><CloudUpload className="mr-2 h-4 w-4" />ลองใหม่</Button>}
                </div>
              </article>)}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
