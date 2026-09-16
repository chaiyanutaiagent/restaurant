import { Navigate } from "react-router-dom";
import { firstAccessibleTakeawayRoute } from "@/config/takeawayWorkspace";
import { useAuthStore } from "@/stores/auth.store";
import TakeawayDashboardPage from "@/pages/takeaway/TakeawayDashboardPage";

export default function TakeawayWorkspaceIndexPage(): JSX.Element {
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const scopeTypes = useAuthStore((state) => state.scopeTypes ?? []);

  if (hasPermission("takeaway.catalog.view")) {
    return <TakeawayDashboardPage />;
  }

  const fallback = firstAccessibleTakeawayRoute(scopeTypes, hasPermission);
  return <Navigate to={fallback && fallback !== "/takeaway" ? fallback : "/403"} replace />;
}
