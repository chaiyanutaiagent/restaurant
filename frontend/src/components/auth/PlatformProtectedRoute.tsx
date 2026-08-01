import { Navigate, Outlet, useLocation } from "react-router-dom";
import { usePlatformAuthStore } from "@/stores/platform-auth.store";

export default function PlatformProtectedRoute(): JSX.Element {
  const location = useLocation();
  const isAuthenticated = usePlatformAuthStore((state) => state.isAuthenticated);
  if (!isAuthenticated()) {
    const next = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to={`/platform/login?next=${encodeURIComponent(next)}`} replace />;
  }
  return <Outlet />;
}
