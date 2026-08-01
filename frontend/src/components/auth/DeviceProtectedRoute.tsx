import { Navigate, Outlet, useLocation } from "react-router-dom";
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
  const isAuthenticated = useDeviceStore((state) => state.isAuthenticated);

  if (!isAuthenticated() || !device) {
    const next = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to={`/device/pair?next=${encodeURIComponent(next)}`} replace />;
  }
  if (device.device_type !== type) {
    return <Navigate to={WORKSPACE_PATH[device.device_type]} replace />;
  }
  return <Outlet />;
}
