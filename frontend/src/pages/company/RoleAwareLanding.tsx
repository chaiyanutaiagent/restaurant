import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { Navigate } from "react-router-dom";
import { companyFoundationApi } from "@/lib/api";

export default function RoleAwareLanding(): JSX.Element {
  const access = useQuery({
    queryKey: ["company-foundation", "access"],
    queryFn: async () => (await companyFoundationApi.access()).data.data,
    retry: false,
  });

  if (access.isLoading) {
    return (
      <div className="flex min-h-48 items-center justify-center text-slate-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> กำลังเลือกพื้นที่ทำงานตามสิทธิ์
      </div>
    );
  }
  return <Navigate to={access.data?.default_route ?? "/company"} replace />;
}
