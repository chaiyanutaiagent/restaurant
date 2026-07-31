import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChefHat, Clock, Flame, Loader2, RefreshCw, Timer } from "lucide-react";
import { useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth.store";

type Ticket = {
  id: string; session_id: string; product_name: string; qty: number;
  special_request: string | null; station: string | null;
  queue_number: number | null; table_name: string | null;
  source_type?: "dine_in" | "quick_service";
  status: string; created_at: string; done_at: string | null;
};

const STATUSES = ["pending", "cooking", "done"] as const;
const STATUS_CONFIG = {
  pending: { label: "รอทำ", bg: "bg-amber-50", badge: "bg-amber-400" },
  cooking: { label: "กำลังทำ", bg: "bg-blue-50", badge: "bg-blue-500" },
  done: { label: "เสร็จแล้ว", bg: "bg-emerald-50", badge: "bg-emerald-500" },
};
const NEXT_STATUS: Record<string, string> = { pending: "cooking", cooking: "done", done: "served" };
const NEXT_LABEL: Record<string, string> = { pending: "เริ่มทำ", cooking: "เสร็จแล้ว", done: "เสิร์ฟแล้ว" };
const SOURCE_LABEL: Record<string, string> = { dine_in: "โต๊ะ", quick_service: "รับเอง" };

function elapsedSeconds(createdAt: string): number {
  const diff = Math.floor((Date.now() - new Date(createdAt).getTime()) / 1000);
  return Math.max(diff, 0);
}

function elapsed(createdAt: string): string {
  const diff = elapsedSeconds(createdAt);
  if (diff < 60) return `${diff}s`;
  return `${Math.floor(diff / 60)}m ${diff % 60}s`;
}

export default function KitchenDisplayPage(): JSX.Element {
  const queryClient = useQueryClient();
  const location = useLocation();
  const branchId = useAuthStore((s) => s.branchId);
  const [station, setStation] = useState<string>("");
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const isRestaurantKitchen = location.pathname.startsWith("/restaurant/");

  const ticketsQuery = useQuery({
    queryKey: ["kitchen-tickets", branchId, station],
    queryFn: async () => {
      const params = station ? `?station=${encodeURIComponent(station)}` : "";
      return (await authApi.get(`/restaurant/kitchen${params}`)).data.data as Ticket[];
    },
    refetchInterval: 5_000,
  });

  const updateMutation = useMutation({
    mutationFn: async ({ ticket, status }: { ticket: Ticket; status: string }) => {
      await authApi.patch(`/restaurant/kitchen/${ticket.id}`, { status });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["kitchen-tickets"] });
      void queryClient.invalidateQueries({ queryKey: ["pickup-queue"] });
    },
  });

  const allTickets = ticketsQuery.data ?? [];
  const tickets = useMemo(() => {
    if (sourceFilter === "all") return allTickets;
    return allTickets.filter((ticket) => (ticket.source_type ?? (ticket.table_name ? "dine_in" : "quick_service")) === sourceFilter);
  }, [allTickets, sourceFilter]);
  const grouped = useMemo(() => {
    const result: Record<string, Ticket[]> = { pending: [], cooking: [], done: [] };
    tickets.forEach((ticket) => { if (ticket.status in result) result[ticket.status].push(ticket); });
    Object.entries(result).forEach(([status, items]) => items.sort((a, b) => {
      if (status === "done") {
        const aTime = new Date(a.done_at ?? a.created_at).getTime();
        const bTime = new Date(b.done_at ?? b.created_at).getTime();
        return bTime - aTime;
      }
      return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    }));
    return result;
  }, [tickets]);
  const oldestPending = grouped.pending[0];
  const urgentCount = tickets.filter((ticket) => ticket.status !== "done" && elapsedSeconds(ticket.created_at) >= 600).length;
  const summary = {
    active: tickets.filter((ticket) => ticket.status === "pending" || ticket.status === "cooking").length,
    pending: grouped.pending.length,
    cooking: grouped.cooking.length,
    done: grouped.done.length,
    dine_in: allTickets.filter((ticket) => (ticket.source_type ?? (ticket.table_name ? "dine_in" : "quick_service")) === "dine_in").length,
    quick_service: allTickets.filter((ticket) => (ticket.source_type ?? (ticket.table_name ? "dine_in" : "quick_service")) === "quick_service").length,
  };
  const errorMessage = updateMutation.error instanceof Error ? updateMutation.error.message : ticketsQuery.error instanceof Error ? ticketsQuery.error.message : null;

  // unique stations from tickets
  const allStations = [...new Set(allTickets.map((t) => t.station).filter(Boolean))] as string[];

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden bg-slate-900 text-white">
      <div className="shrink-0 border-b border-slate-700 px-3 py-2 sm:px-4 xl:px-6 xl:py-4">
        <div className="flex flex-wrap items-center justify-between gap-2 xl:gap-4">
          <div className="flex items-center gap-3">
            <ChefHat className="h-6 w-6 text-emerald-400 xl:h-7 xl:w-7" />
            <div>
              <h1 className="text-lg font-bold xl:text-xl">Kitchen Display</h1>
              <p className="hidden text-xs text-slate-400 sm:block xl:text-sm">
                {isRestaurantKitchen ? "กดเสร็จแล้วเพื่อส่งคิวไปจอรับอาหาร" : "รายการเก่าขึ้นก่อน แยกโต๊ะและรับเองได้"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-300 xl:gap-3 xl:text-sm">
            <span className="inline-flex h-8 items-center gap-1 rounded-full bg-slate-800 px-2 xl:px-3">
              งานค้าง {summary.active}
            </span>
            <span className="inline-flex h-8 items-center gap-1 rounded-full bg-slate-800 px-2 xl:px-3">
              <Clock className="h-4 w-4" /> รีเฟรช 5s
            </span>
            <span className={`inline-flex h-8 items-center gap-1 rounded-full px-2 xl:px-3 ${urgentCount > 0 ? "bg-rose-500 text-white" : "bg-slate-800"}`}>
              <Flame className="h-4 w-4" /> เกิน 10 นาที {urgentCount}
            </span>
            <button
              type="button"
              onClick={() => queryClient.invalidateQueries({ queryKey: ["kitchen-tickets"] })}
              className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-slate-800 text-slate-300 hover:bg-slate-700"
              aria-label="รีเฟรช"
            >
              <RefreshCw className={`h-4 w-4 ${ticketsQuery.isFetching ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-slate-800 pt-2 xl:mt-4 xl:pt-4">
          {[
            { key: "all", label: `ทุกช่องทาง ${allTickets.length}` },
            { key: "dine_in", label: `โต๊ะ ${summary.dine_in}` },
            { key: "quick_service", label: `รับเอง ${summary.quick_service}` },
          ].map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setSourceFilter(item.key)}
              className={`h-9 rounded-full px-3 text-xs font-semibold xl:h-10 xl:px-4 xl:text-sm ${sourceFilter === item.key ? "bg-emerald-500 text-white" : "border border-slate-600 text-slate-300"}`}
            >
              {item.label}
            </button>
          ))}
          <span className="mx-1 h-6 w-px bg-slate-700" aria-hidden="true" />
          <button
            type="button"
            onClick={() => setStation("")}
            className={`h-9 rounded-full px-3 text-xs font-semibold xl:h-10 xl:px-4 xl:text-sm ${!station ? "bg-slate-100 text-slate-950" : "border border-slate-600 text-slate-300"}`}
          >
            ทุกสถานี
          </button>
          {allStations.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setStation(s)}
              className={`h-9 rounded-full px-3 text-xs font-semibold xl:h-10 xl:px-4 xl:text-sm ${station === s ? "bg-slate-100 text-slate-950" : "border border-slate-600 text-slate-300"}`}
            >
              {s}
            </button>
          ))}
          {oldestPending ? (
            <span className="ml-auto inline-flex h-9 items-center gap-1 rounded-full bg-amber-400 px-3 text-xs font-semibold text-amber-950 xl:text-sm">
              <Timer className="h-4 w-4" /> รอนานสุด {elapsed(oldestPending.created_at)}
            </span>
          ) : null}
        </div>
        {errorMessage ? (
          <div className="mt-3 rounded-xl border border-rose-500 bg-rose-950/60 px-4 py-3 text-sm font-semibold text-rose-100">
            {errorMessage}
          </div>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-x-auto">
        <div className="grid h-full min-w-[780px] grid-cols-3 divide-x divide-slate-700">
          {STATUSES.map((statusKey) => {
            const cfg = STATUS_CONFIG[statusKey];
            return (
              <div key={statusKey} className="flex min-w-0 flex-col overflow-hidden">
                <div className={`flex items-center gap-2 border-b border-slate-700 px-3 py-2 ${cfg.bg} bg-opacity-10 xl:px-4 xl:py-3`}>
                  <span className={`h-3 w-3 rounded-full ${cfg.badge}`} />
                  <span className="font-semibold text-slate-200">{cfg.label}</span>
                  <span className="ml-auto rounded-full bg-slate-700 px-2 py-0.5 text-xs text-slate-300">{grouped[statusKey].length}</span>
                </div>
                <div className="flex-1 space-y-2 overflow-y-auto p-2 xl:space-y-3 xl:p-3">
                  {grouped[statusKey].map((ticket) => (
                    <div key={ticket.id} className={`rounded-xl border p-3 xl:rounded-2xl xl:p-4 ${elapsedSeconds(ticket.created_at) >= 600 && ticket.status !== "done" ? "border-rose-400 bg-rose-950/40" : "border-slate-700 bg-slate-800"}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded-full bg-slate-950 px-2 py-1 text-xs font-bold text-slate-200">
                            {SOURCE_LABEL[ticket.source_type ?? (ticket.table_name ? "dine_in" : "quick_service")]}
                          </span>
                          {ticket.queue_number ? (
                            <span className="rounded-full bg-emerald-500 px-2 py-1 text-xs font-bold text-white">คิว {String(ticket.queue_number).padStart(3, "0")}</span>
                          ) : null}
                          {ticket.table_name ? (
                            <span className="rounded-full bg-blue-500 px-2 py-1 text-xs font-bold text-white">โต๊ะ {ticket.table_name}</span>
                          ) : null}
                          {ticket.station ? <span className="text-xs text-slate-400">{ticket.station}</span> : null}
                        </div>
                        <p className="mt-1 text-sm font-bold text-white xl:text-base">{ticket.product_name}</p>
                        <p className="text-2xl font-bold text-emerald-400 xl:text-3xl">x{ticket.qty}</p>
                        {ticket.special_request && (
                          <p className="mt-2 rounded-xl bg-amber-300 px-3 py-2 text-sm font-semibold text-amber-950">
                            {ticket.special_request}
                          </p>
                        )}
                      </div>
                      <span className="flex-shrink-0 rounded-full bg-slate-900 px-2 py-1 text-xs text-slate-300">{elapsed(ticket.created_at)}</span>
                    </div>
                    {NEXT_STATUS[statusKey] && !(isRestaurantKitchen && statusKey === "done") && (
                      <button
                        type="button"
                        disabled={updateMutation.isPending}
                        onClick={() => updateMutation.mutate({ ticket, status: NEXT_STATUS[statusKey] })}
                        className="mt-2 flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-slate-100 text-sm font-bold text-slate-950 hover:bg-white disabled:opacity-60 xl:mt-3 xl:h-12 xl:text-base"
                      >
                        {updateMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                        {NEXT_LABEL[statusKey]}
                      </button>
                    )}
                    </div>
                  ))}
                  {grouped[statusKey].length === 0 && (
                    <p className="py-8 text-center text-sm text-slate-600">ว่าง</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
