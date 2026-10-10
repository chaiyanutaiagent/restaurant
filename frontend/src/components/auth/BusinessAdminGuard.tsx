import { useQuery } from "@tanstack/react-query";
import { Navigate, Outlet, useLocation, useParams } from "react-router-dom";
import { membershipApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth.store";


export default function BusinessAdminGuard(): JSX.Element {
  const { businessSlug = "" } = useParams();
  const location = useLocation();
  const companyId = useAuthStore((state) => state.companyId);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const business = useQuery({
    queryKey: ["public-business", businessSlug],
    queryFn: async () => (await membershipApi.business(businessSlug)).data.data,
    enabled: Boolean(businessSlug),
    retry: false,
  });

  if (business.isLoading) {
    return <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-300">กำลังตรวจสอบธุรกิจ...</div>;
  }
  if (business.isError || !business.data || business.data.business_slug !== businessSlug.toLowerCase()) {
    return <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-300">ไม่พบธุรกิจนี้</div>;
  }
  if (!isAuthenticated() || companyId !== business.data.company_id) {
    const next = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to={`/${business.data.business_slug}/login?next=${encodeURIComponent(next)}`} replace />;
  }
  return <Outlet />;
}
