import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock, Loader2, RefreshCw, Volume2, VolumeX } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { authApi } from "@/lib/api";
import { deviceApi } from "@/lib/deviceApi";
import { fbApi } from "@/lib/fbApi";
import { useAuthStore } from "@/stores/auth.store";
import { useDeviceStore } from "@/stores/device.store";
import type { ApiResponse } from "@/types/api";
import type { DeviceWorkspaceBootstrap } from "@/types/device";

type PickupQueue = {
  session_id: string;
  queue_number: number;
  customer_name: string | null;
  ticket_count: number;
  item_count: number;
  ready_at: string | null;
};

function formatQueue(prefix: string, queueNumber: number): string {
  return `${prefix}${String(queueNumber).padStart(3, "0")}`;
}

function readyAgo(readyAt: string | null): string {
  if (!readyAt) return "-";
  const diff = Math.max(Math.floor((Date.now() - new Date(readyAt).getTime()) / 60_000), 0);
  if (diff <= 0) return "พร้อมเมื่อสักครู่";
  return `พร้อมแล้ว ${diff} นาที`;
}

function readyMinutes(readyAt: string | null): number {
  if (!readyAt) return 0;
  return Math.max(Math.floor((Date.now() - new Date(readyAt).getTime()) / 60_000), 0);
}

export default function PickupDisplayPage(): JSX.Element {
  const queryClient = useQueryClient();
  const location = useLocation();
  const userBranchId = useAuthStore((s) => s.branchId);
  const device = useDeviceStore((s) => s.device);
  const prevQueueRef = useRef<number[]>([]);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const isRestaurantPickup = location.pathname.startsWith("/restaurant/");
  const isDeviceWorkspace = location.pathname === "/pickup";
  const branchId = isDeviceWorkspace ? device?.branch_id : userBranchId;

  const bootstrapQuery = useQuery({
    queryKey: ["device-workspace", "pickup"],
    queryFn: async () => (await deviceApi.get<ApiResponse<DeviceWorkspaceBootstrap>>("/device-workspaces/pickup/bootstrap")).data.data,
    enabled: isDeviceWorkspace,
    retry: false,
  });

  const settingsQuery = useQuery({
    queryKey: ["branch-settings", branchId],
    queryFn: async () => isDeviceWorkspace
      ? (await deviceApi.get<ApiResponse<DeviceWorkspaceBootstrap>>("/device-workspaces/pickup/bootstrap")).data.data
      : (await fbApi.settings()).data.data,
    enabled: Boolean(branchId),
  });

  const queueQuery = useQuery({
    queryKey: ["pickup-queue", branchId],
    queryFn: async () =>
      isDeviceWorkspace
        ? (await deviceApi.get("/device-workspaces/pickup/queue")).data.data as PickupQueue[]
        : (await authApi.get("/restaurant/pickup-queue")).data.data as PickupQueue[],
    refetchInterval: 5_000,
    enabled: Boolean(branchId),
  });

  const readyQueue = queueQuery.data ?? [];
  const prefix = isDeviceWorkspace
    ? (settingsQuery.data as DeviceWorkspaceBootstrap | undefined)?.queue_prefix ?? ""
    : (settingsQuery.data as { fb_queue_prefix?: string } | undefined)?.fb_queue_prefix ?? "";
  const primaryQueue = readyQueue[0];
  const secondaryQueues = readyQueue.slice(1);
  const servedMutation = useMutation({
    mutationFn: async (sessionId: string) =>
      isDeviceWorkspace
        ? deviceApi.post(`/device-workspaces/pickup/queue/${sessionId}/served`)
        : authApi.post(`/restaurant/pickup-queue/${sessionId}/served`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pickup-queue"] });
      void queryClient.invalidateQueries({ queryKey: ["kitchen-tickets"] });
    },
  });
  const lastUpdatedLabel = useMemo(
    () => new Date().toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    [queueQuery.dataUpdatedAt]
  );

  function playPickupChime(force = false): void {
    if (!force && !soundEnabled) return;
    try {
      if (!audioCtxRef.current) audioCtxRef.current = new AudioContext();
      const ctx = audioCtxRef.current;
      if (ctx.state === "suspended") void ctx.resume();
      [0, 0.3, 0.6].forEach((offset) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain); gain.connect(ctx.destination);
        osc.frequency.value = offset === 0 ? 660 : offset === 0.3 ? 880 : 1100;
        gain.gain.setValueAtTime(0.4, ctx.currentTime + offset);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + offset + 0.4);
        osc.start(ctx.currentTime + offset);
        osc.stop(ctx.currentTime + offset + 0.4);
      });
    } catch {
      setSoundEnabled(false);
    }
  }

  // เล่นเสียงเมื่อมีคิวใหม่
  useEffect(() => {
    const prev = prevQueueRef.current;
    const queueNumbers = readyQueue.map((queue) => queue.queue_number);
    const newQueues = queueNumbers.filter((q) => !prev.includes(q));
    if (newQueues.length > 0) playPickupChime();
    prevQueueRef.current = queueNumbers;
  }, [readyQueue, soundEnabled]);

  return (
    <div className="flex min-h-screen flex-col bg-slate-950 px-5 py-6 text-white sm:px-8 sm:py-8">
      {/* Header */}
      <div className="text-center">
        <p className="text-lg font-semibold uppercase tracking-[0.4em] text-emerald-400">รับอาหาร</p>
        <p className="mt-2 text-4xl font-black sm:text-5xl">พร้อมรับแล้ว</p>
        <p className="mt-3 text-sm text-slate-400">โปรดตรวจเลขคิว แล้วติดต่อพนักงานที่เคาน์เตอร์</p>
        {isDeviceWorkspace ? <p className="mt-2 text-sm font-semibold text-emerald-300">{bootstrapQuery.data?.branch.name ?? "กำลังตรวจอุปกรณ์"} · {device?.device_code}</p> : null}
        <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-xs text-slate-400">
          <span className="inline-flex items-center gap-1 rounded-full bg-slate-900 px-3 py-1.5">
            <RefreshCw className={`h-3.5 w-3.5 ${queueQuery.isFetching ? "animate-spin" : ""}`} />
            อัปเดตทุก 5 วินาที
          </span>
          <span className="rounded-full bg-slate-900 px-3 py-1.5">ล่าสุด {lastUpdatedLabel}</span>
          <span className="rounded-full bg-slate-900 px-3 py-1.5">คิวพร้อมรับ {readyQueue.length}</span>
          <button
            type="button"
            onClick={() => {
              const next = !soundEnabled;
              setSoundEnabled(next);
              if (next) setTimeout(() => playPickupChime(true), 0);
            }}
            className={`inline-flex items-center gap-1 rounded-full px-3 py-1.5 font-semibold ${
              soundEnabled ? "bg-emerald-500 text-emerald-950" : "bg-slate-900 text-slate-400"
            }`}
          >
            {soundEnabled ? <Volume2 className="h-3.5 w-3.5" /> : <VolumeX className="h-3.5 w-3.5" />}
            เสียง
          </button>
        </div>
      </div>

      {/* Queue Numbers */}
      {queueQuery.isError ? (
        <div className="flex flex-1 items-center justify-center text-center">
          <div className="rounded-[2rem] border border-rose-500 bg-rose-950/50 px-8 py-10">
            <p className="text-3xl font-black text-rose-100">โหลดคิวไม่สำเร็จ</p>
            <p className="mt-3 text-sm text-rose-200">ตรวจการเชื่อมต่อหรือ branch context ของเครื่องนี้</p>
          </div>
        </div>
      ) : readyQueue.length === 0 ? (
        <div className="flex flex-1 items-center justify-center text-center">
          <div>
            <p className="text-7xl">...</p>
            <p className="mt-4 text-2xl font-medium text-slate-400">ยังไม่มีออเดอร์พร้อม</p>
          </div>
        </div>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center gap-8">
          {primaryQueue ? (
            <div className={`flex w-full max-w-xl flex-col items-center rounded-[2rem] border-4 px-8 py-10 shadow-2xl shadow-emerald-950/60 sm:px-14 ${
              readyMinutes(primaryQueue.ready_at) >= 10
                ? "border-amber-200 bg-amber-400"
                : "border-emerald-300 bg-emerald-500"
            }`}>
              <span className="text-xl font-bold uppercase tracking-widest text-emerald-950">{prefix || "คิว"}</span>
              <span className="mt-2 text-8xl font-black leading-none text-white sm:text-9xl">
                {formatQueue(prefix, primaryQueue.queue_number)}
              </span>
              <div className="mt-5 flex flex-wrap justify-center gap-2 text-sm font-semibold text-emerald-950">
                {primaryQueue.customer_name ? <span className="rounded-full bg-white/40 px-3 py-1">{primaryQueue.customer_name}</span> : null}
                <span className="rounded-full bg-white/40 px-3 py-1">{primaryQueue.item_count} รายการ</span>
                <span className="inline-flex items-center gap-1 rounded-full bg-white/40 px-3 py-1">
                  <Clock className="h-4 w-4" />
                  {readyAgo(primaryQueue.ready_at)}
                </span>
                {readyMinutes(primaryQueue.ready_at) >= 10 ? <span className="rounded-full bg-white/50 px-3 py-1">รอนาน</span> : null}
              </div>
              {(isRestaurantPickup || isDeviceWorkspace) ? (
                <button
                  type="button"
                  disabled={servedMutation.isPending}
                  onClick={() => servedMutation.mutate(primaryQueue.session_id)}
                  className="mt-6 inline-flex h-14 min-w-56 items-center justify-center gap-2 rounded-2xl bg-slate-950 px-6 text-lg font-black text-white shadow-lg hover:bg-slate-800 disabled:opacity-60"
                >
                  {servedMutation.isPending ? <Loader2 className="h-5 w-5 animate-spin" /> : <CheckCircle2 className="h-5 w-5" />}
                  รับสินค้าแล้ว
                </button>
              ) : null}
            </div>
          ) : null}
          {secondaryQueues.length > 0 ? (
            <div className="flex flex-wrap justify-center gap-4">
              {secondaryQueues.map((queue) => (
                <div
                  key={queue.session_id}
                  className={`rounded-3xl border px-7 py-5 text-center ${
                    readyMinutes(queue.ready_at) >= 10
                      ? "border-amber-300 bg-amber-400 text-slate-950"
                      : "border-slate-700 bg-slate-900 text-white"
                  }`}
                >
                  <span className={`block text-xs font-semibold uppercase tracking-widest ${readyMinutes(queue.ready_at) >= 10 ? "text-slate-700" : "text-slate-400"}`}>{prefix || "คิว"}</span>
                  <span className="mt-1 block text-5xl font-black leading-none">{formatQueue(prefix, queue.queue_number)}</span>
                  <span className="mt-2 block text-xs opacity-75">{queue.item_count} รายการ · {readyAgo(queue.ready_at)}</span>
                  {(isRestaurantPickup || isDeviceWorkspace) ? (
                    <button
                      type="button"
                      disabled={servedMutation.isPending}
                      onClick={() => servedMutation.mutate(queue.session_id)}
                      className={`mt-4 inline-flex h-10 items-center justify-center gap-1.5 rounded-xl px-4 text-sm font-black disabled:opacity-60 ${
                        readyMinutes(queue.ready_at) >= 10
                          ? "bg-slate-950 text-white"
                          : "bg-emerald-500 text-emerald-950"
                      }`}
                    >
                      {servedMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                      รับแล้ว
                    </button>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}

      {/* Footer */}
      <div className="text-center text-slate-500">
        <p className="mt-1 text-xs">Kitchen Display &gt; เสร็จแล้ว &gt; แสดงที่นี่</p>
      </div>
    </div>
  );
}
