import { Navigate } from "react-router-dom";
import { useAuthStore } from "@/stores/auth.store";

export type TakeawayLegacyRoute = "central-orders" | "stock" | "transfers" | "reports";

export default function TakeawayLegacyRedirect({ route }: { route: TakeawayLegacyRoute }): JSX.Element {
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const scopeTypes = useAuthStore((state) => state.scopeTypes ?? []);

  if (route === "central-orders") {
    return <Navigate to={hasPermission("takeaway.central_order.manage") ? "/takeaway/central/orders" : "/takeaway/store/central-orders"} replace />;
  }

  if (route === "stock") {
    return <Navigate to={hasPermission("takeaway.stock.manage") ? "/takeaway/central/stock" : "/takeaway/store/stock"} replace />;
  }

  const centralScope = hasPermission("*")
    || scopeTypes.includes("company")
    || scopeTypes.includes("brand");
  return <Navigate to={`/takeaway/${centralScope ? "central" : "store"}/${route}`} replace />;
}
