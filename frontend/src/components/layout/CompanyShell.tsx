import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  AppWindow,
  Bell,
  Building2,
  Check,
  ChevronDown,
  Home,
  LogOut,
  Loader2,
  Menu,
  Settings,
  ShieldCheck,
  ClipboardList,
  Users,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import CompanyErrorBoundary from "@/components/company/CompanyErrorBoundary";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useToast } from "@/components/ui/use-toast";
import { PLATFORM_BRAND } from "@/config/platformBrand";
import { useLogout } from "@/hooks/useAuth";
import { authApi, companyFoundationApi } from "@/lib/api";
import { companyRequestState } from "@/lib/companyPresentation";
import { cn, getDisplayName } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth.store";

type CompanyNavItem = {
  label: string;
  to: string;
  icon: typeof Home;
  permission?: string;
  permissions?: string[];
  exact?: boolean;
};

const navigation: CompanyNavItem[] = [
  { label: "หน้าหลัก", to: "/company", icon: Home, exact: true },
  { label: "งานและการแจ้งเตือน", to: "/company/actions", icon: Bell },
  { label: "องค์กร", to: "/company/organization", icon: Building2, permission: "system.branch.view" },
  { label: "พนักงานและสิทธิ์", to: "/company/people", icon: Users, permissions: ["system.user.view", "system.role.view"] },
  { label: "ความปลอดภัย", to: "/company/security", icon: ShieldCheck, permission: "system.user.view" },
  { label: "ประวัติการเปลี่ยนแปลง", to: "/company/audit", icon: ClipboardList, permissions: ["system.company.view", "system.company.edit", "accounting.report.view"] },
  { label: "การตั้งค่า", to: "/company/settings", icon: Settings, permission: "system.company.edit" },
  { label: "แอปทั้งหมด", to: "/company/apps", icon: AppWindow },
];

function canShow(item: CompanyNavItem, hasPermission: (code: string) => boolean): boolean {
  if (item.permission && !hasPermission(item.permission)) return false;
  if (item.permissions?.length && !item.permissions.some(hasPermission)) return false;
  return true;
}

export default function CompanyShell(): JSX.Element {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [online, setOnline] = useState(() => navigator.onLine);
  const location = useLocation();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const logout = useLogout();
  const user = useAuthStore((state) => state.user);
  const companyId = useAuthStore((state) => state.companyId);
  const branchId = useAuthStore((state) => state.branchId);
  const stationKey = useAuthStore((state) => state.stationKey);
  const scopeTypes = useAuthStore((state) => state.scopeTypes);
  const setSession = useAuthStore((state) => state.setSession);
  const hasPermission = useAuthStore((state) => state.hasPermission);

  useEffect(() => {
    const update = (): void => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  useEffect(() => setSidebarOpen(false), [location.pathname]);

  const context = useQuery({
    queryKey: ["company-foundation", "context", branchId, stationKey],
    queryFn: async () => (await companyFoundationApi.context()).data.data,
    retry: false,
  });
  const branches = useQuery({
    queryKey: ["company-foundation", "branches", companyId],
    queryFn: async () => (await authApi.myBranches()).data.data,
    retry: false,
  });
  const actions = useQuery({
    queryKey: ["company-foundation", "action-center", branchId, stationKey],
    queryFn: async () => (await companyFoundationApi.actionCenter()).data.data,
    retry: false,
  });

  const selectedBranch = useMemo(
    () => branches.data?.find((branch) => (
      branch.branch_id === branchId && branch.station_key === stationKey
    )) ?? branches.data?.find((branch) => branch.branch_id === branchId) ?? null,
    [branchId, branches.data, stationKey],
  );

  const switchContext = useMutation({
    mutationFn: async (target: { branchId: string; stationKey: string | null }) => {
      if (!companyId) throw new Error("Company context is unavailable");
      await queryClient.cancelQueries();
      const response = await authApi.switchBranch(target.branchId, target.stationKey);
      return { companyId, session: response.data.data };
    },
    onSuccess: ({ companyId: currentCompanyId, session }) => {
      setSession(session, currentCompanyId);
      queryClient.clear();
      toast({
        title: "เปลี่ยนบริบทแล้ว",
        description: "สิทธิ์และข้อมูลเดิมถูกล้างก่อนโหลดสาขาใหม่",
      });
    },
    onError: () => {
      toast({
        title: "เปลี่ยนบริบทไม่สำเร็จ",
        description: "ระบบยังคงใช้บริบทเดิมและไม่ได้แสดงข้อมูลข้ามสาขา",
        variant: "destructive",
      });
    },
  });

  const currentContextLabel = context.data?.branch?.name
    ?? (scopeTypes.includes("company") ? "ทุกแบรนด์ · ทุกสาขา" : selectedBranch?.branch_name)
    ?? "กำลังตรวจบริบท";
  const visibleNavigation = navigation.filter((item) => canShow(item, hasPermission));
  const contextRequestState = context.error ? companyRequestState(context.error) : null;

  return (
    <div className="flex h-screen overflow-hidden bg-[#f3f6fb] text-slate-950" data-testid="company-shell">
      <a
        href="#company-main-content"
        className="sr-only fixed left-3 top-3 z-[70] rounded-xl bg-slate-950 px-4 py-3 font-bold text-white shadow-xl focus:not-sr-only"
      >
        ข้ามไปเนื้อหาหลัก
      </a>
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-[16.5rem] flex-col border-r border-slate-200 bg-white shadow-2xl transition-transform duration-200 xl:static xl:translate-x-0 xl:shadow-none",
          sidebarOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex min-h-16 items-center justify-between border-b border-slate-200 px-5">
          <Link to="/company" className="flex min-h-11 items-center gap-3 font-black text-slate-950">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-700 text-white shadow-sm">
              F
            </span>
            <span>{PLATFORM_BRAND.productName}</span>
          </Link>
          <Button className="min-w-11 xl:hidden" variant="ghost" size="icon" onClick={() => setSidebarOpen(false)} aria-label="ปิดเมนู">
            <X className="h-5 w-5" />
          </Button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-5" aria-label="เมนูบริษัทลูกค้า">
          {visibleNavigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.exact}
              className={({ isActive }) => cn(
                "flex min-h-11 items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-bold transition",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2",
                isActive
                  ? "bg-blue-50 text-blue-700 ring-1 ring-blue-100"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-950",
              )}
            >
              <item.icon className="h-5 w-5 shrink-0" />
              <span className="min-w-0 flex-1">{item.label}</span>
              {item.to === "/company/actions" && (actions.data?.unread ?? 0) > 0 ? (
                <Badge variant="destructive">{actions.data?.unread}</Badge>
              ) : null}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-slate-200 p-4">
          <Link to="/company/apps" className="flex min-h-11 items-center gap-3 rounded-xl bg-slate-950 px-3.5 text-sm font-bold text-white hover:bg-slate-800">
            <AppWindow className="h-5 w-5" />กลับไปแอปทั้งหมด
          </Link>
          <p className="mt-3 text-center text-[11px] text-slate-400">Customer Company Workspace</p>
        </div>
      </aside>

      {sidebarOpen ? (
        <button
          type="button"
          aria-label="ปิดเมนู"
          className="fixed inset-0 z-40 bg-slate-950/35 backdrop-blur-sm xl:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="z-30 flex min-h-16 shrink-0 items-center gap-2 border-b border-slate-200 bg-white/95 px-3 shadow-sm backdrop-blur md:px-5">
          <Button className="min-w-11 shrink-0 xl:hidden" variant="ghost" size="icon" onClick={() => setSidebarOpen(true)} aria-label="เปิดเมนู">
            <Menu className="h-5 w-5" />
          </Button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                className="min-w-0 max-w-[13rem] justify-between px-3 md:max-w-[25rem]"
                disabled={switchContext.isPending}
                data-testid="company-context-switcher"
              >
                <span className="flex min-w-0 items-center gap-2 truncate">
                  <Building2 className="h-4 w-4 shrink-0 text-blue-700" />
                  <span className="truncate">{context.data?.company.name ?? (context.isLoading ? "กำลังตรวจบริบท" : "ไม่พบบริบทบริษัท")}</span>
                  <span className="hidden text-slate-300 md:inline">/</span>
                  <span className="hidden truncate text-slate-500 md:inline">{currentContextLabel}</span>
                </span>
                <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-[min(92vw,24rem)]">
              <DropdownMenuLabel>
                <span className="block text-xs font-normal text-slate-500">บริษัท</span>
                <span>{context.data?.company.name ?? "กำลังโหลด"}</span>
              </DropdownMenuLabel>
              {context.data?.brand ? (
                <DropdownMenuLabel className="pt-0 text-xs font-normal text-slate-500">
                  แบรนด์ปัจจุบัน: {context.data.brand.name}
                </DropdownMenuLabel>
              ) : null}
              <DropdownMenuSeparator />
              {scopeTypes.includes("company") && !branchId ? (
                <DropdownMenuItem disabled className="gap-2 bg-blue-50 text-blue-800">
                  <Check className="h-4 w-4" />ทุกแบรนด์ · ทุกสาขา
                </DropdownMenuItem>
              ) : null}
              {branches.data?.map((branch) => {
                const active = branch.branch_id === branchId && branch.station_key === stationKey;
                return (
                  <DropdownMenuItem
                    key={`${branch.branch_id}:${branch.station_key ?? "branch"}`}
                    className="min-h-12 gap-2"
                    disabled={active || switchContext.isPending}
                    onClick={() => switchContext.mutate({ branchId: branch.branch_id, stationKey: branch.station_key })}
                  >
                    <Check className={cn("h-4 w-4", active ? "opacity-100" : "opacity-0")} />
                    <span className="min-w-0">
                      <span className="block truncate font-semibold">{branch.branch_name}</span>
                      <span className="block truncate text-xs text-slate-500">
                        {branch.business_type ?? "ไม่ระบุระบบ"} · {branch.role_name}
                      </span>
                    </span>
                  </DropdownMenuItem>
                );
              })}
              {branches.isLoading ? (
                <DropdownMenuItem disabled><Loader2 className="mr-2 h-4 w-4 animate-spin" />กำลังโหลดรายการสาขา</DropdownMenuItem>
              ) : null}
              {branches.error ? (
                <DropdownMenuItem disabled><AlertTriangle className="mr-2 h-4 w-4" />โหลดรายการสาขาไม่สำเร็จ</DropdownMenuItem>
              ) : null}
              {branches.data?.length === 0 ? (
                <DropdownMenuItem disabled>ไม่มีสาขาในสิทธิ์ปัจจุบัน</DropdownMenuItem>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>

          <div className="ml-auto flex shrink-0 items-center gap-1.5 md:gap-2">
            <Badge className={context.data?.environment === "production"
              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : context.data?.environment === "uat"
                ? "border-amber-200 bg-amber-50 text-amber-800"
                : "border-slate-200 bg-slate-100 text-slate-700"}
            >
              {context.data?.environment === "production" ? "PRODUCTION" : context.data?.environment === "uat" ? "UAT" : "กำลังตรวจสอบ"}
            </Badge>
            <Button asChild variant="ghost" size="icon" className="relative" aria-label="งานและการแจ้งเตือน">
              <Link to="/company/actions">
                <Bell className="h-5 w-5" />
                {(actions.data?.unread ?? 0) > 0 ? (
                  <span className="absolute right-0 top-0 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-black text-white">
                    {Math.min(actions.data?.unread ?? 0, 99)}
                  </span>
                ) : null}
              </Link>
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="gap-2 px-1.5 md:px-2">
                  <Avatar className="h-9 w-9">
                    <AvatarFallback>{user?.username.slice(0, 2).toUpperCase() ?? "AD"}</AvatarFallback>
                  </Avatar>
                  <span className="hidden max-w-36 truncate text-sm font-bold lg:inline">
                    {getDisplayName(user?.display_name ?? null, user?.username ?? "guest")}
                  </span>
                  <ChevronDown className="h-4 w-4 text-slate-400" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuLabel>
                  <span className="block">{getDisplayName(user?.display_name ?? null, user?.username ?? "guest")}</span>
                  <span className="block text-xs font-normal text-slate-500">@{user?.username ?? "guest"}</span>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={logout}><LogOut className="mr-2 h-4 w-4" />ออกจากระบบ</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        {context.isLoading ? (
          <div className="flex min-h-10 items-center justify-center gap-2 border-b border-blue-200 bg-blue-50 px-4 text-sm font-semibold text-blue-800" role="status" data-company-context-state="loading">
            <Loader2 className="h-4 w-4 animate-spin" />กำลังตรวจสอบ Company / Brand / Branch context จาก Server
          </div>
        ) : null}

        {contextRequestState ? (
          <div className={cn(
            "flex min-h-11 items-center justify-center gap-2 border-b px-4 text-center text-sm font-semibold",
            contextRequestState === "permission_denied" ? "border-slate-300 bg-slate-100 text-slate-800" : contextRequestState === "offline" ? "border-amber-300 bg-amber-50 text-amber-900" : "border-red-300 bg-red-50 text-red-900",
          )} role="alert" data-company-context-state={contextRequestState}>
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {contextRequestState === "permission_denied" ? "Server ไม่อนุญาตให้ดูบริบทบริษัทนี้" : contextRequestState === "offline" ? "ยังยืนยันบริบทกับ Server ไม่ได้ขณะออฟไลน์" : "โหลดบริบทบริษัทไม่สำเร็จ — action ที่อาศัย context จะถูกปิด"}
          </div>
        ) : null}

        {!online ? (
          <div className="flex min-h-11 items-center justify-center gap-2 border-b border-amber-300 bg-amber-50 px-4 text-sm font-semibold text-amber-900" role="alert" data-testid="company-offline-banner">
            <ShieldCheck className="h-4 w-4" />ออฟไลน์ — แสดงข้อมูลที่มีอยู่เท่านั้น และปิด action ที่ต้องเชื่อมต่อ Server
          </div>
        ) : null}

        <main id="company-main-content" tabIndex={-1} className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden p-3 sm:p-4 lg:p-5 2xl:p-6 focus:outline-none">
          <div className="mx-auto w-full max-w-[1680px]">
            <CompanyErrorBoundary resetKey={`${branchId ?? "company"}:${stationKey ?? "all"}:${location.pathname}`}><Outlet /></CompanyErrorBoundary>
          </div>
        </main>
      </div>
    </div>
  );
}
