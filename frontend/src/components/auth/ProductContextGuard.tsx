import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Building2, Loader2 } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  businessTypeWorkspace,
  PRODUCT_ENTRY_PATH,
  workspaceFromHostname,
  type ProductBusinessType,
} from "@/config/productRouting";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth.store";
import type { UserBranch } from "@/types/user";

type ProductContextGuardProps = {
  businessType: ProductBusinessType;
};

const PRODUCT_LABEL: Record<ProductBusinessType, string> = {
  restaurant: "Restaurant POS",
  retail_pos: "Retail POS",
  takeaway: "Takeaway POS",
};

export default function ProductContextGuard({ businessType }: ProductContextGuardProps): JSX.Element {
  const location = useLocation();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((state) => state.companyId);
  const currentBusinessType = useAuthStore((state) => state.businessType);
  const targetDatabase = useAuthStore((state) => state.targetDatabase);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const setSession = useAuthStore((state) => state.setSession);
  const autoSwitchAttempted = useRef(false);
  const expectedWorkspace = businessTypeWorkspace(businessType);
  const hostWorkspace = workspaceFromHostname(window.location.hostname);
  const contextMatches = currentBusinessType === businessType && targetDatabase === businessType;

  const branches = useQuery({
    queryKey: ["product-context", "branches", companyId, businessType],
    queryFn: async () => (await authApi.myBranches()).data.data,
    enabled: isAuthenticated() && !contextMatches && Boolean(companyId),
    retry: false,
  });
  const candidates = useMemo(
    () => (branches.data ?? []).filter((branch) => (
      branch.business_type === businessType && branch.target_database === businessType
    )),
    [branches.data, businessType],
  );
  const switchContext = useMutation({
    mutationFn: async (branch: UserBranch) => {
      if (!companyId) throw new Error("Company context is unavailable");
      const response = await authApi.switchBranch(branch.branch_id, branch.station_key);
      return { companyId, session: response.data.data };
    },
    onSuccess: ({ companyId: activeCompanyId, session }) => {
      setSession(session, activeCompanyId);
      queryClient.clear();
    },
  });

  useEffect(() => {
    if (
      !contextMatches
      && candidates.length === 1
      && !switchContext.isPending
      && !autoSwitchAttempted.current
    ) {
      autoSwitchAttempted.current = true;
      switchContext.mutate(candidates[0]);
    }
  }, [candidates, contextMatches, switchContext]);

  if (hostWorkspace && hostWorkspace !== "company" && hostWorkspace !== expectedWorkspace) {
    return <Navigate to={PRODUCT_ENTRY_PATH[hostWorkspace]} replace />;
  }

  if (!isAuthenticated()) {
    const next = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }

  if (contextMatches) return <Outlet />;

  if (branches.isLoading || switchContext.isPending || (candidates.length === 1 && !switchContext.isError)) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-100 p-5">
        <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-lg">
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-blue-600" />
          <h1 className="mt-4 text-xl font-black text-slate-950">กำลังเปิด {PRODUCT_LABEL[businessType]}</h1>
          <p className="mt-2 text-sm text-slate-600">ระบบกำลังเลือก Company / Brand / Branch ที่ได้รับอนุญาต</p>
        </div>
      </main>
    );
  }

  if (branches.isError || switchContext.isError || candidates.length === 0) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-100 p-5">
        <div className="w-full max-w-md rounded-2xl border border-red-200 bg-white p-8 text-center shadow-lg">
          <AlertTriangle className="mx-auto h-9 w-9 text-red-600" />
          <h1 className="mt-4 text-xl font-black text-slate-950">ไม่สามารถเปิด {PRODUCT_LABEL[businessType]}</h1>
          <p className="mt-2 text-sm text-slate-600">บัญชีนี้ไม่มีสาขาของระบบดังกล่าว หรือสิทธิ์บริบทไม่ถูกต้อง</p>
          <Button
            className="mt-5"
            variant="outline"
            onClick={() => {
              autoSwitchAttempted.current = false;
              switchContext.reset();
              void branches.refetch();
            }}
          >
            ตรวจสิทธิ์อีกครั้ง
          </Button>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 p-5">
      <section className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white p-6 shadow-lg">
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-blue-600 text-white"><Building2 className="h-5 w-5" /></span>
          <div><h1 className="text-xl font-black text-slate-950">เลือกสาขา {PRODUCT_LABEL[businessType]}</h1><p className="text-sm text-slate-600">แสดงเฉพาะสาขาที่บัญชีนี้ได้รับอนุญาต</p></div>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          {candidates.map((branch) => (
            <Button key={`${branch.branch_id}:${branch.station_key ?? "branch"}`} variant="outline" className="h-auto min-h-16 justify-start px-4 py-3 text-left" onClick={() => switchContext.mutate(branch)}>
              <span><span className="block font-bold">{branch.branch_name}</span><span className="block text-xs font-normal text-slate-500">{branch.branch_code} · {branch.role_name}</span></span>
            </Button>
          ))}
        </div>
      </section>
    </main>
  );
}
