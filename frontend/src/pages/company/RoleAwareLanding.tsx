import { useQuery } from "@tanstack/react-query";
import { Navigate } from "react-router-dom";
import CompanyStatePanel from "@/components/company/CompanyStatePanel";
import { companyFoundationApi } from "@/lib/api";
import { companyRequestState } from "@/lib/companyPresentation";

export default function RoleAwareLanding(): JSX.Element {
  const access = useQuery({
    queryKey: ["company-foundation", "access"],
    queryFn: async () => (await companyFoundationApi.access()).data.data,
    retry: false,
  });

  if (access.isLoading) {
    return <CompanyStatePanel kind="loading" title="กำลังเลือกพื้นที่ทำงานตามสิทธิ์" />;
  }
  if (access.error || !access.data) {
    const state = companyRequestState(access.error);
    return (
      <CompanyStatePanel
        kind={state}
        title={state === "permission_denied" ? "ไม่มีพื้นที่ทำงานที่ได้รับอนุญาต" : undefined}
        description={state === "permission_denied" ? "บัญชีนี้ยังไม่มีบทบาทหรือขอบเขตบริษัทที่ Server อนุญาต" : undefined}
        onRetry={() => void access.refetch()}
      />
    );
  }
  return <Navigate to={access.data.default_route || "/403"} replace />;
}
