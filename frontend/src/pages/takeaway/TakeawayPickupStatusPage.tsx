import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, ChefHat, Clock3, PackageCheck, XCircle } from "lucide-react";
import { useParams } from "react-router-dom";
import { takeawayPublicApi } from "@/lib/takeawayApi";

const labels = {
  awaiting_payment: "รอชำระเงิน",
  queued: "รับออเดอร์แล้ว",
  preparing: "กำลังเตรียม",
  ready: "พร้อมรับ",
  picked_up: "รับสินค้าแล้ว",
  cancelled: "ยกเลิกแล้ว",
} as const;

export default function TakeawayPickupStatusPage(): JSX.Element {
  const { token = "" } = useParams();
  const query = useQuery({
    queryKey: ["takeaway", "public-pickup", token],
    queryFn: async () => (await takeawayPublicApi.pickupStatus(token)).data.data,
    enabled: Boolean(token),
    refetchInterval: 5_000,
    retry: 1,
  });
  const order = query.data;
  const Icon = order?.fulfillment_status === "ready" ? PackageCheck
    : order?.fulfillment_status === "picked_up" ? CheckCircle2
      : order?.fulfillment_status === "cancelled" ? XCircle
        : order?.fulfillment_status === "preparing" ? ChefHat : Clock3;
  const accent = order?.fulfillment_status === "ready" ? "bg-emerald-500"
    : order?.fulfillment_status === "picked_up" ? "bg-sky-500"
      : order?.fulfillment_status === "cancelled" ? "bg-rose-500" : "bg-amber-400";

  return (
    <main className="grid min-h-screen place-items-center bg-slate-950 p-5 text-slate-950">
      <section className="w-full max-w-lg overflow-hidden rounded-[2rem] bg-white shadow-2xl">
        <header className="bg-emerald-500 p-6 text-center"><p className="text-sm font-black uppercase tracking-[0.25em]">Foodchainservice</p><h1 className="mt-1 text-2xl font-black">สถานะรับสินค้า</h1></header>
        {query.isLoading ? <div className="p-12 text-center text-slate-500">กำลังตรวจสอบคิว…</div> : null}
        {query.isError ? <div className="p-12 text-center"><XCircle className="mx-auto h-14 w-14 text-rose-500" /><h2 className="mt-4 text-xl font-black">ไม่พบคิวนี้หรือ QR หมดอายุ</h2><p className="mt-2 text-sm text-slate-500">กรุณาติดต่อพนักงานหน้าร้าน</p></div> : null}
        {order ? <div className="p-8 text-center"><div className={`mx-auto grid h-24 w-24 place-items-center rounded-full ${accent}`}><Icon className="h-12 w-12 text-white" /></div><p className="mt-6 text-sm font-bold text-slate-500">หมายเลขคิว</p><p className="text-7xl font-black tabular-nums">{order.queue_number}</p><div className="mt-6 rounded-2xl bg-slate-100 p-4"><p className="text-2xl font-black">{labels[order.fulfillment_status]}</p><p className="mt-2 text-lg font-bold text-emerald-700">ยอด {new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(Number(order.total_amount))}</p><p className="mt-1 text-xs text-slate-500">{order.order_number}</p></div><p className="mt-5 text-sm text-slate-500">หน้านี้อัปเดตอัตโนมัติทุก 5 วินาที</p></div> : null}
      </section>
    </main>
  );
}
