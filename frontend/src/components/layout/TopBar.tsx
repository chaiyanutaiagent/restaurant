import { useQuery } from "@tanstack/react-query";
import { Building2, ChevronDown, KeyRound, LogOut, Menu, UserCircle2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { authApi } from "@/lib/api";
import { useLogout } from "@/hooks/useAuth";
import { useAuthStore } from "@/stores/auth.store";
import { cn, getDisplayName } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";
import { useToast } from "@/components/ui/use-toast";
import ManagerPinDialog from "@/components/approval/ManagerPinDialog";
import { PLATFORM_BRAND } from "@/config/platformBrand";

type TopBarProps = {
  title: string;
  onMenuClick: () => void;
  workspace?: "admin" | "restaurant";
};

export default function TopBar({ title, onMenuClick, workspace = "admin" }: TopBarProps): JSX.Element {
  const logout = useLogout();
  const { toast } = useToast();
  const user = useAuthStore((state) => state.user);
  const branchId = useAuthStore((state) => state.branchId);
  const stationKey = useAuthStore((state) => state.stationKey);
  const companyId = useAuthStore((state) => state.companyId);
  const setSession = useAuthStore((state) => state.setSession);
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const [managerPinOpen, setManagerPinOpen] = useState(false);
  const canApproveOperations = [
    "pos.discount.override",
    "pos.sale.void",
    "pos.refund.create",
    "inventory.stock.adjust"
  ].some((permission) => hasPermission(permission));

  const branchesQuery = useQuery({
    queryKey: ["system", "my-branches"],
    queryFn: async () => {
      const response = await authApi.myBranches();
      return response.data.data;
    }
  });

  const defaultBranch = useMemo(
    () => branchesQuery.data?.find((branch) => branch.is_default) ?? branchesQuery.data?.[0] ?? null,
    [branchesQuery.data]
  );
  const currentBranch =
    branchesQuery.data?.find(
      (branch) => branch.branch_id === branchId && branch.station_key === stationKey
    ) ?? defaultBranch;

  const handleSwitchBranch = useCallback(async (
    nextBranchId: string,
    nextStationKey: string | null = null,
    notify = true
  ): Promise<void> => {
    if (!companyId) {
      return;
    }

    const response = await authApi.switchBranch(nextBranchId, nextStationKey);
    setSession(response.data.data, companyId);
    if (notify) {
      toast({
        title: "เปลี่ยนสาขาแล้ว",
        description: "ระบบได้อัปเดตสิทธิ์และบริบทสาขาให้เรียบร้อย"
      });
    }
  }, [companyId, setSession, toast]);

  useEffect(() => {
    if (!branchId && defaultBranch) {
      void handleSwitchBranch(defaultBranch.branch_id, defaultBranch.station_key, false);
    }
  }, [branchId, defaultBranch, handleSwitchBranch]);

  return (
    <header className="flex min-h-16 shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white/95 px-3 shadow-sm backdrop-blur md:px-5 xl:px-7">
      <div className="flex min-w-0 items-center gap-3">
        <Button variant="ghost" size="icon" className="shrink-0 xl:hidden" onClick={onMenuClick}>
          <Menu className="h-5 w-5" />
        </Button>
        <div className="min-w-0">
          <p className={cn("truncate text-base font-black md:text-lg", workspace === "restaurant" ? "text-orange-600" : "text-blue-600")}>
            {workspace === "restaurant" ? "Restaurant" : PLATFORM_BRAND.productName}
          </p>
          <p className="truncate text-xs text-slate-500 md:text-sm">
            {title}
          </p>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-1.5 md:gap-3">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" className="max-w-[11rem] justify-between gap-2 md:max-w-[15rem]">
              <span className="flex items-center gap-2 truncate">
                <Building2 className="h-4 w-4 text-blue-600" />
                <span className="hidden truncate sm:inline">{currentBranch?.branch_name ?? "เลือกสาขา"}</span>
              </span>
              <ChevronDown className="h-4 w-4 text-gray-400" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>สาขาที่ใช้งาน</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {branchesQuery.data?.map((branch) => (
              <DropdownMenuItem
                key={`${branch.branch_id}:${branch.station_key ?? "branch"}`}
                onClick={() => {
                  void handleSwitchBranch(branch.branch_id, branch.station_key);
                }}
              >
                <div className="flex flex-col">
                  <span>
                    {branch.branch_name}
                    {branch.station_key ? ` / ${branch.station_key}` : ""}
                  </span>
                  <span className="text-xs text-gray-500">{branch.role_name}</span>
                </div>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="gap-2 px-1.5 md:px-2">
              <Avatar className="h-9 w-9">
                <AvatarFallback>
                  {user?.username.slice(0, 2).toUpperCase() ?? "AD"}
                </AvatarFallback>
              </Avatar>
              <div className="hidden text-left xl:block">
                <p className="text-sm font-medium text-gray-900">
                  {getDisplayName(user?.display_name ?? null, user?.username ?? "guest")}
                </p>
                <p className="text-xs text-gray-500">@{user?.username ?? "guest"}</p>
              </div>
              <ChevronDown className="h-4 w-4 text-gray-400" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>บัญชีผู้ใช้</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem>
              <UserCircle2 className="mr-2 h-4 w-4" />
              {getDisplayName(user?.display_name ?? null, user?.username ?? "guest")}
            </DropdownMenuItem>
            {canApproveOperations ? (
              <DropdownMenuItem onClick={() => setManagerPinOpen(true)}>
                <KeyRound className="mr-2 h-4 w-4" />
                ตั้งค่า Manager PIN
              </DropdownMenuItem>
            ) : null}
            <DropdownMenuItem onClick={logout}>
              <LogOut className="mr-2 h-4 w-4" />
              ออกจากระบบ
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <ManagerPinDialog open={managerPinOpen} onOpenChange={setManagerPinOpen} />
      </div>
    </header>
  );
}
