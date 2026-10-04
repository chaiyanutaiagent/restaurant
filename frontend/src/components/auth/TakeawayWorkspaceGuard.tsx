import { Navigate, Outlet } from "react-router-dom";
import { canAccessTakeawayArea, type TakeawayWorkspaceArea } from "@/config/takeawayWorkspace";
import { useAuthStore } from "@/stores/auth.store";

export default function TakeawayWorkspaceGuard({ area }: { area: TakeawayWorkspaceArea }): JSX.Element {
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const scopeTypes = useAuthStore((state) => state.scopeTypes ?? []);

  if (!canAccessTakeawayArea(area, scopeTypes, hasPermission)) {
    return <Navigate to="/403" replace />;
  }

  return <Outlet />;
}
