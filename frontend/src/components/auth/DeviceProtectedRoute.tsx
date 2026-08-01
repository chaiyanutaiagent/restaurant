import axios from "axios";
import { Loader2, RefreshCw, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { renewDeviceSession } from "@/lib/deviceApi";
import { useDeviceStore } from "@/stores/device.store";
import type { DeviceType } from "@/types/device";

const WORKSPACE_PATH: Record<DeviceType, string> = {
  counter: "/counter",
  kitchen: "/kitchen",
  pickup: "/pickup",
};

export default function DeviceProtectedRoute({ type }: { type: DeviceType }): JSX.Element {
  const location = useLocation();
  const device = useDeviceStore((state) => state.device);
  const hydrated = useDeviceStore((state) => state.hydrated);
  const refreshToken = useDeviceStore((state) => state.refreshToken);
  const expiresAt = useDeviceStore((state) => state.expiresAt);
  const hydrate = useDeviceStore((state) => state.hydrate);
  const isAuthenticated = useDeviceStore((state) => state.isAuthenticated);
  const [checking, setChecking] = useState(true);
  const [networkBlocked, setNetworkBlocked] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await hydrate();
      const state = useDeviceStore.getState();
      if (state.refreshToken) {
        if (state.isAuthenticated()) {
          if (!cancelled) setChecking(false);
          void renewDeviceSession().catch(() => undefined);
          return;
        }
        try {
          await renewDeviceSession();
        } catch (error) {
          const permanentFailure = axios.isAxiosError(error) && error.response?.status === 401;
          if (!permanentFailure && !state.isAuthenticated() && !cancelled) {
            setNetworkBlocked(true);
          }
        }
      }
      if (!cancelled) setChecking(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [hydrate]);

  if (checking || !hydrated) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-slate-950 text-slate-200">
        <div className="flex items-center gap-3 text-lg font-semibold"><Loader2 className="h-6 w-6 animate-spin" />กำลังเปิดเครื่องประจำร้าน</div>
      </div>
    );
  }

  if (networkBlocked && refreshToken && (!expiresAt || expiresAt <= Date.now())) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-slate-950 p-6 text-white">
        <div className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-6 text-center shadow-2xl">
          <ShieldCheck className="mx-auto h-12 w-12 text-emerald-400" />
          <h1 className="mt-4 text-xl font-bold">เครื่องยังจับคู่อยู่</h1>
          <p className="mt-2 text-sm text-slate-300">เชื่อมต่อระบบเพื่อออก access token ใหม่ ไม่ต้อง Pair เครื่องซ้ำ</p>
          <Button className="mt-6 w-full" onClick={() => window.location.reload()}><RefreshCw className="h-4 w-4" />ลองเชื่อมต่ออีกครั้ง</Button>
        </div>
      </div>
    );
  }

  if (!isAuthenticated() || !device) {
    const next = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to={`/device/pair?next=${encodeURIComponent(next)}`} replace />;
  }
  if (device.device_type !== type) {
    return <Navigate to={WORKSPACE_PATH[device.device_type]} replace />;
  }
  return <Outlet />;
}
