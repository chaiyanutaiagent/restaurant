import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Banknote, Clock3, Loader2, LockKeyhole, Play, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useToast } from "@/components/ui/use-toast";
import { useTakeawayReleaseGate } from "@/hooks/useTakeawayReleaseGate";
import { takeawayApi, type TakeawayRecord } from "@/lib/takeawayApi";
import { hasUnsyncedTakeawaySales } from "@/lib/takeawayOffline";

function today(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok" }).format(new Date());
}

function amount(value: unknown): string {
  const numeric = Number(value ?? 0);
  return Number.isFinite(numeric) ? numeric.toLocaleString("th-TH", { minimumFractionDigits: 2 }) : "0.00";
}

export default function TakeawayShiftPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const releaseGate = useTakeawayReleaseGate();
  const writesEnabled = releaseGate.writesEnabled;
  const [openingCash, setOpeningCash] = useState("0");
  const [countedCash, setCountedCash] = useState("0");
  const [note, setNote] = useState("");
  const shiftsQuery = useQuery({
    queryKey: ["takeaway", "shifts"],
    queryFn: async () => (await takeawayApi.shifts()).data.data,
  });
  const rows = (shiftsQuery.data ?? []) as TakeawayRecord[];
  const activeShift = useMemo(() => rows.find((row) => row.status === "open") ?? null, [rows]);
  const summaryQuery = useQuery({
    queryKey: ["takeaway", "shift-summary", activeShift?.id],
    queryFn: async () => (await takeawayApi.shiftSummary(activeShift!.id)).data.data,
    enabled: Boolean(activeShift?.id),
    refetchInterval: 10_000,
  });
  useEffect(() => {
    if (summaryQuery.data?.expected_cash && countedCash === "0") {
      setCountedCash(summaryQuery.data.expected_cash);
    }
  }, [countedCash, summaryQuery.data?.expected_cash]);
  const mutation = useMutation({
    mutationFn: async (action: "open" | "close") => {
      if (!writesEnabled) throw new Error("การเปิด/ปิดกะยังถูกล็อกในช่วง Dark launch");
      if (action === "open") {
        return takeawayApi.openShift({ business_date: today(), opening_cash: openingCash || "0" });
      }
      if (!activeShift) throw new Error("ไม่พบกะที่เปิดอยู่");
      if (await hasUnsyncedTakeawaySales()) {
        throw new Error("ยังมีรายการขายในเครื่องที่ส่งไม่สำเร็จ กรุณาส่งรายการค้างก่อนปิดกะ");
      }
      return takeawayApi.closeShift(activeShift.id, { counted_cash: countedCash || "0", note: note || undefined });
    },
    onSuccess: async (_, action) => {
      await queryClient.invalidateQueries({ queryKey: ["takeaway", "shifts"] });
      toast({ title: action === "open" ? "เปิดกะแล้ว" : "ปิดกะแล้ว" });
    },
    onError: (error) => toast({
      title: "ทำรายการกะไม่สำเร็จ",
      description: error instanceof Error ? error.message : "ตรวจเงินสดและสถานะกะ",
      variant: "destructive",
    }),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.22em] text-emerald-700">Store workspace</p>
          <h1 className="mt-1 text-2xl font-black">กะขายหน้าร้าน</h1>
          <p className="mt-1 text-sm text-slate-500">เปิดกะ ตรวจเงินสด และเก็บประวัติแยกรอบขาย</p>
        </div>
        <button onClick={() => void shiftsQuery.refetch()} className="flex items-center gap-2 rounded-xl border bg-white px-4 py-2 text-sm font-bold">
          <RefreshCw className="h-4 w-4" /> รีเฟรช
        </button>
      </div>

      <section className="grid gap-4 lg:grid-cols-[360px_1fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-3">
            <span className={`rounded-xl p-3 ${activeShift ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}><Clock3 className="h-6 w-6" /></span>
            <div><p className="text-sm text-slate-500">สถานะปัจจุบัน</p><p className="font-black">{activeShift ? `กะ ${String(activeShift.round_no ?? "-")}` : "ยังไม่เปิดกะ"}</p></div>
          </div>
          {activeShift ? (
            <div className="mt-5 space-y-3">
              {summaryQuery.data ? <div className="grid grid-cols-2 gap-2 rounded-xl bg-slate-50 p-3 text-sm"><div><p className="text-xs text-slate-500">ขายสุทธิ</p><p className="font-black">฿{amount(summaryQuery.data.paid.amount)}</p></div><div><p className="text-xs text-slate-500">เงินสดที่ควรมี</p><p className="font-black text-emerald-700">฿{amount(summaryQuery.data.expected_cash)}</p></div><div><p className="text-xs text-slate-500">จำนวนบิล</p><p className="font-black">{summaryQuery.data.paid.order_count}</p></div><div><p className="text-xs text-slate-500">คืนเงิน</p><p className="font-black text-rose-700">฿{amount(summaryQuery.data.refunded.amount)}</p></div></div> : null}
              <label className="block text-xs font-bold text-slate-600">เงินสดที่นับได้<input value={countedCash} onChange={(event) => setCountedCash(event.target.value)} inputMode="decimal" className="mt-1 w-full rounded-xl border px-3 py-2 text-sm" /></label>
              {summaryQuery.data ? <div className={`flex items-center gap-2 rounded-xl p-3 text-sm font-bold ${Number(countedCash || 0) - Number(summaryQuery.data.expected_cash) === 0 ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-900"}`}><AlertTriangle className="h-4 w-4" />ผลต่างเงินสด ฿{amount(Number(countedCash || 0) - Number(summaryQuery.data.expected_cash))}</div> : null}
              <label className="block text-xs font-bold text-slate-600">หมายเหตุ<input value={note} onChange={(event) => setNote(event.target.value)} className="mt-1 w-full rounded-xl border px-3 py-2 text-sm" /></label>
              <button disabled={!writesEnabled || mutation.isPending} onClick={() => mutation.mutate("close")} className="flex w-full items-center justify-center gap-2 rounded-xl bg-slate-950 px-4 py-3 font-bold text-white disabled:opacity-50">
                {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <LockKeyhole className="h-4 w-4" />} ปิดกะ
              </button>
            </div>
          ) : (
            <div className="mt-5 space-y-3">
              <label className="block text-xs font-bold text-slate-600">เงินทอนเปิดกะ<input disabled={!writesEnabled} value={openingCash} onChange={(event) => setOpeningCash(event.target.value)} inputMode="decimal" className="mt-1 w-full rounded-xl border px-3 py-2 text-sm disabled:bg-slate-100" /></label>
              <button disabled={!writesEnabled || mutation.isPending} onClick={() => mutation.mutate("open")} className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-3 font-black text-slate-950 disabled:opacity-50">
                {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} {writesEnabled ? "เปิดกะวันนี้" : "รอเปิด Transaction Gate"}
              </button>
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="flex items-center gap-2 font-black"><Banknote className="h-5 w-5 text-emerald-600" /> ประวัติกะ</h2>
          {shiftsQuery.isLoading ? <div className="flex justify-center p-10"><Loader2 className="h-7 w-7 animate-spin text-emerald-600" /></div> : rows.length ? (
            <div className="mt-4 space-y-2">{rows.map((row) => (
              <article key={row.id} className="grid gap-2 rounded-xl border border-slate-200 p-3 text-sm sm:grid-cols-[1fr_auto_auto] sm:items-center">
                <div><p className="font-bold">{String(row.business_date ?? "-")} · รอบ {String(row.round_no ?? "-")}</p><p className="text-xs text-slate-500">{String(row.status ?? "-")}</p></div>
                <p className="text-slate-600">เปิด ฿{amount(row.opening_cash)}</p>
                <div className="text-right"><p className="font-bold">นับ ฿{amount(row.counted_cash)}</p>{row.expected_cash != null ? <p className="text-xs text-slate-500">ควรมี ฿{amount(row.expected_cash)} · ต่าง ฿{amount(Number(row.counted_cash ?? 0) - Number(row.expected_cash ?? 0))}</p> : null}</div>
              </article>
            ))}</div>
          ) : <p className="mt-5 rounded-xl border border-dashed p-8 text-center text-slate-500">ยังไม่มีประวัติกะ</p>}
        </div>
      </section>
    </div>
  );
}
