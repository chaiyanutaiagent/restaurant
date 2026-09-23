import { Navigate, useLocation } from "react-router-dom";
import {
  PRODUCT_ENTRY_PATH,
  PRODUCT_POS_PATH,
  workspaceFromHostname,
} from "@/config/productRouting";
import { useAuthStore } from "@/stores/auth.store";

export function HostEntryRedirect({ fallback }: { fallback: JSX.Element }): JSX.Element {
  const workspace = workspaceFromHostname(window.location.hostname);
  return workspace ? <Navigate to={PRODUCT_ENTRY_PATH[workspace]} replace /> : fallback;
}

export function LegacyPosRedirect({ offline = false }: { offline?: boolean }): JSX.Element {
  const location = useLocation();
  const businessType = useAuthStore((state) => state.businessType);
  const path = businessType === "retail_pos"
    ? `/retail/${offline ? "offline-sync" : "pos"}`
    : businessType === "takeaway"
      ? PRODUCT_POS_PATH.takeaway
      : `/restaurant/${offline ? "offline-sync" : "pos"}`;
  return <Navigate to={`${path}${offline ? "" : location.search}`} replace />;
}
