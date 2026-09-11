import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, LayoutDashboard, UserRoundCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { authApi } from "@/lib/api";
import { useOnlineStatus } from "@/lib/syncService";
import { useAuthStore } from "@/stores/auth.store";

type PosWorkspaceHeaderProps = {
  title: string;
};

export default function PosWorkspaceHeader({ title }: PosWorkspaceHeaderProps): JSX.Element {
  const navigate = useNavigate();
  const branchId = useAuthStore((state) => state.branchId);
  const stationKey = useAuthStore((state) => state.stationKey);
  const user = useAuthStore((state) => state.user);
  const isOnline = useOnlineStatus();
  const branchesQuery = useQuery({
    queryKey: ["system", "my-branches"],
    queryFn: async () => (await authApi.myBranches()).data.data,
  });
  const branchName = branchesQuery.data?.find((branch) => branch.branch_id === branchId)?.branch_name ?? "สาขาหลัก";
  const staffIdentifier = user?.employee_code?.trim() || user?.username || "-";

  return (
    <header className="shrink-0 border-b border-slate-200/80 bg-white/90 px-4 py-2.5 backdrop-blur">
      <div className="flex flex-wrap items-center gap-2 lg:flex-nowrap">
        <span className="whitespace-nowrap text-base font-bold text-slate-900">Restaurant POS</span>
        <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto text-xs">
          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 font-medium text-slate-700">{branchName}</span>
          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 font-medium text-slate-600">{stationKey || "จุดขายหลัก"}</span>
          <span className="hidden items-center gap-1 rounded-full bg-blue-50 px-2.5 py-0.5 font-medium text-blue-700 md:inline-flex">
            <UserRoundCheck className="h-3.5 w-3.5" /> ID {staffIdentifier}
          </span>
          <span className={`rounded-full px-2.5 py-0.5 font-medium ${isOnline ? "bg-blue-50 text-blue-700" : "bg-red-100 text-red-700"}`}>
            {isOnline ? "● ONLINE" : "○ OFFLINE"}
          </span>
          <span className="hidden truncate rounded-full bg-emerald-50 px-2.5 py-0.5 font-semibold text-emerald-700 xl:inline">
            {title}
          </span>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          <Button size="sm" variant="outline" onClick={() => navigate("/pos")}>
            <ArrowLeft className="mr-1 h-4 w-4" /> หน้าขาย
          </Button>
          <Button size="sm" variant="outline" aria-label="กลับหน้าผู้ดูแล" onClick={() => navigate("/admin")}>
            <LayoutDashboard className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </header>
  );
}
