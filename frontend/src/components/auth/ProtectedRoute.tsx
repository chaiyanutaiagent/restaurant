import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuthStore } from "@/stores/auth.store";

type ProtectedRouteProps = {
  permission?: string;
  permissions?: string[];
};

export default function ProtectedRoute({ permission, permissions }: ProtectedRouteProps): JSX.Element {
  const location = useLocation();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const hasPermission = useAuthStore((state) => state.hasPermission);

  if (!isAuthenticated()) {
    const next = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }

  if (permission && !hasPermission(permission)) {
    return <Navigate to="/403" replace />;
  }

  if (permissions?.length && !permissions.some((code) => hasPermission(code))) {
    return <Navigate to="/403" replace />;
  }

  return <Outlet />;
}
