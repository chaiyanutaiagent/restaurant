import { useQuery } from "@tanstack/react-query";
import { Building2, ChevronDown, LogOut, Menu, UserCircle2 } from "lucide-react";
import { useCallback, useEffect, useMemo } from "react";
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
  const companyId = useAuthStore((state) => state.companyId);
  const setSession = useAuthStore((state) => state.setSession);

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
    branchesQuery.data?.find((branch) => branch.branch_id === branchId) ?? defaultBranch;

  const handleSwitchBranch = useCallback(async (nextBranchId: string, notify = true): Promise<void> => {
    if (!companyId) {
      return;
    }

    const response = await authApi.switchBranch(nextBranchId);
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
      void handleSwitchBranch(defaultBranch.branch_id, false);
    }
  }, [branchId, defaultBranch, handleSwitchBranch]);

  return (
    <header className="flex h-16 items-center justify-between border-b border-gray-200 bg-white px-4 shadow-sm md:px-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" className="md:hidden" onClick={onMenuClick}>
          <Menu className="h-5 w-5" />
        </Button>
        <div>
          <p className={cn("text-lg font-bold", workspace === "restaurant" ? "text-orange-600" : "text-blue-600")}>
            {workspace === "restaurant" ? "Restaurant" : "Restaurant POS"}
          </p>
          <p className="hidden text-sm text-gray-500 md:block">
            {workspace === "restaurant" ? "F&B Workspace" : title}
          </p>
        </div>
      </div>

      <div className="hidden text-lg font-semibold text-gray-900 md:block">{title}</div>

      <div className="flex items-center gap-2 md:gap-3">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" className="max-w-[200px] justify-between gap-2">
              <span className="flex items-center gap-2 truncate">
                <Building2 className="h-4 w-4 text-blue-600" />
                <span className="truncate">{currentBranch?.branch_name ?? "เลือกสาขา"}</span>
              </span>
              <ChevronDown className="h-4 w-4 text-gray-400" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>สาขาที่ใช้งาน</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {branchesQuery.data?.map((branch) => (
              <DropdownMenuItem
                key={branch.branch_id}
                onClick={() => {
                  void handleSwitchBranch(branch.branch_id);
                }}
              >
                <div className="flex flex-col">
                  <span>{branch.branch_name}</span>
                  <span className="text-xs text-gray-500">{branch.role_name}</span>
                </div>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="gap-2 px-2">
              <Avatar className="h-9 w-9">
                <AvatarFallback>
                  {user?.username.slice(0, 2).toUpperCase() ?? "AD"}
                </AvatarFallback>
              </Avatar>
              <div className="hidden text-left md:block">
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
            <DropdownMenuItem onClick={logout}>
              <LogOut className="mr-2 h-4 w-4" />
              ออกจากระบบ
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
