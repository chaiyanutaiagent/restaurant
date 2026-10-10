import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import {
  Boxes,
  ClipboardCheck,
  ClipboardList,
  CreditCard,
  LogOut,
  Menu,
  PackageSearch,
  Printer,
  Store,
  Warehouse,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import TakeawayCounterPage from "@/pages/takeaway/TakeawayCounterPage";
import TakeawayCatalogPage from "@/pages/takeaway/TakeawayCatalogPage";
import TakeawayShiftPage from "@/pages/takeaway/TakeawayShiftPage";
import TakeawayStoreStockPage from "@/pages/takeaway/TakeawayStoreStockPage";
import TakeawayStoreCentralOrdersPage from "@/pages/takeaway/TakeawayStoreCentralOrdersPage";
import TakeawayDeviceSettingsPage from "@/pages/takeaway/TakeawayDeviceSettingsPage";
import { Toaster } from "@/components/ui/toaster";
import { STORE_ROUTES, allowedStoreRoute } from "./routes";
import { clearSession, restoreSession, useAuthStore } from "./session";
import { cleanupStoreData } from "./db";
import { onboardingApi } from "./api";
import Onboarding from "./Onboarding";
import { StoreCreditPage, StoreTransfersPage } from "./StoreSupportPages";
import UpdateGate from "./UpdateGate";
import "../index.css";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const StoreSalesPage = () => <TakeawayCounterPage mode="sales" />;
const StoreOrdersPage = () => <TakeawayCounterPage mode="orders" />;
const pages: Record<string, React.ComponentType> = {
  "/takeaway/store/sales": StoreSalesPage,
  "/takeaway/store/orders": StoreOrdersPage,
  "/takeaway/store/catalog": TakeawayCatalogPage,
  "/takeaway/store/stock": TakeawayStoreStockPage,
  "/takeaway/store/shifts": TakeawayShiftPage,
  "/takeaway/store/central-orders": TakeawayStoreCentralOrdersPage,
  "/takeaway/store/credits": StoreCreditPage,
  "/takeaway/store/transfers": StoreTransfersPage,
  "/takeaway/store/device": TakeawayDeviceSettingsPage,
};

const routeIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  "/takeaway/store/sales": Store,
  "/takeaway/store/orders": ClipboardList,
  "/takeaway/store/catalog": PackageSearch,
  "/takeaway/store/stock": Warehouse,
  "/takeaway/store/shifts": ClipboardCheck,
  "/takeaway/store/central-orders": Boxes,
  "/takeaway/store/credits": CreditCard,
  "/takeaway/store/transfers": Store,
  "/takeaway/store/device": Printer,
};

function displayBrand(value: string | null): string {
  return (value || "STORE").replace(/-/g, " ").toUpperCase();
}

function StoreApp(): JSX.Element {
  const session = useAuthStore();
  const location = useLocation();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [leaving, setLeaving] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => { void restoreSession().then(() => setReady(true)).catch(() => setError("เปิดที่เก็บข้อมูลปลอดภัยไม่ได้ กรุณาปิดและเปิดแอปอีกครั้ง")); }, []);
  useEffect(() => { queryClient.clear(); }, [session.companyId, session.branchId, session.user?.id]);
  useEffect(() => { setMenuOpen(false); }, [location.pathname]);
  useEffect(() => {
    const updateNetwork = (): void => setOnline(navigator.onLine);
    window.addEventListener("online", updateNetwork);
    window.addEventListener("offline", updateNetwork);
    return () => {
      window.removeEventListener("online", updateNetwork);
      window.removeEventListener("offline", updateNetwork);
    };
  }, []);
  if (!ready) return <p className="p-8" role="status">{error || "กำลังเปิดแอป…"}</p>;
  const forbidden = location.pathname !== "/" && location.pathname !== "/login"
    && !STORE_ROUTES.some((route) => route.path === location.pathname);
  if (forbidden) return <div className="p-8"><h1>ไม่อนุญาตให้เข้าหน้านี้</h1><Link to="/">กลับหน้าร้าน</Link></div>;
  if (!session.accessToken) return <Onboarding />;
  const visible = STORE_ROUTES.filter((route) => session.hasPermission(route.permission));
  const landingPath = visible.find((route) => route.path === "/takeaway/store/sales")?.path
    ?? visible.find((route) => route.path === "/takeaway/store/stock")?.path
    ?? visible[0]?.path
    ?? "/login";
  const primary = visible.filter((route) => route.primary);
  const currentRoute = visible.find((route) => route.path === location.pathname) ?? visible[0];
  async function logout() {
    setLeaving(true); setError("");
    try {
      if (queryClient.isMutating()) throw new Error("กำลังบันทึกรายการ กรุณารอให้เสร็จก่อนออกจากระบบ");
      await queryClient.cancelQueries();
      await cleanupStoreData();
      await onboardingApi.post("/auth/logout", { refresh_token: session.refreshToken });
      await clearSession(); queryClient.clear();
    } catch (failure) { setError(failure instanceof Error ? failure.message : "ออกจากระบบไม่ได้ กรุณาเชื่อมต่อและซิงก์ก่อน"); }
    finally { setLeaving(false); }
  }
  return <div className="takeaway-app-shell min-h-screen bg-slate-50">
    <header className="native-safe-top sticky top-0 z-40 border-b border-slate-200 bg-white" role="banner">
      <nav aria-label="เมนูหลักหน้าร้าน" className="mx-auto flex max-w-5xl flex-wrap items-center gap-2 px-3 py-3">
        <span className="mr-1 break-words px-1 text-sm font-black tracking-wide text-slate-500 sm:mr-3">{session.companyName || displayBrand(session.businessSlug)}</span>
        {primary.map((route) => <Link
          aria-current={location.pathname === route.path ? "page" : undefined}
          className={`flex min-h-12 items-center rounded-xl px-4 py-2 text-base font-bold transition ${location.pathname === route.path ? "bg-slate-950 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100"}`}
          key={route.path}
          to={route.path}
        >{route.navLabel}</Link>)}
      </nav>
    </header>

    <div className="relative mx-auto max-w-5xl px-3 pt-3">
      <section className="flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
        <div className="flex min-w-0 items-center gap-3">
          <button
            aria-controls="chambo-store-menu"
            aria-expanded={menuOpen}
            aria-label={menuOpen ? "ปิดเมนูหน้าร้าน" : "เปิดเมนูหน้าร้าน"}
            className="grid h-12 w-12 shrink-0 place-items-center rounded-xl border border-slate-200 bg-white text-slate-950"
            onClick={() => setMenuOpen((value) => !value)}
          >{menuOpen ? <X className="h-6 w-6" /> : <Menu className="h-7 w-7" />}</button>
          <div className="min-w-0">
            <p className="text-sm font-black leading-tight text-slate-950 sm:text-base">{currentRoute?.sectionLabel ?? "เมนูหน้าร้าน"} · {session.branchName || displayBrand(session.businessSlug)}</p>
            <p className="truncate text-sm text-slate-500">พนักงาน: {session.user?.display_name || session.user?.username} · {session.stationKey}</p>
          </div>
        </div>
        <span className={`flex shrink-0 items-center gap-2 rounded-full px-3 py-2 text-sm font-bold ${online ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-800"}`}>
          {online ? <Wifi className="h-4 w-4" /> : <WifiOff className="h-4 w-4" />}{online ? "ออนไลน์" : "ออฟไลน์"}
        </span>
      </section>

      {menuOpen ? <>
        <button aria-label="ปิดเมนูหน้าร้าน" className="fixed inset-0 z-40 cursor-default bg-transparent" onClick={() => setMenuOpen(false)} />
        <aside id="chambo-store-menu" aria-label="เมนูหน้าร้าน" className="absolute left-3 top-full z-50 mt-2 w-[min(24rem,calc(100vw-1.5rem))] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
          <nav className="divide-y divide-slate-100" aria-label="เมนูงานหน้าร้าน">
            {visible.map((route) => {
              const Icon = routeIcons[route.path] ?? Store;
              return <Link
                aria-current={location.pathname === route.path ? "page" : undefined}
                className={`flex min-h-14 items-center gap-3 px-5 py-3 text-base font-semibold ${location.pathname === route.path ? "bg-slate-100 text-slate-950" : "text-slate-700 hover:bg-slate-50"}`}
                key={route.path}
                to={route.path}
              ><Icon className="h-5 w-5 shrink-0" />{route.menuLabel}</Link>;
            })}
          </nav>
          <div className="border-t border-slate-200 p-2">
            <button
              className="flex min-h-14 w-full items-center gap-3 rounded-xl px-3 py-3 text-left font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              disabled={leaving}
              onClick={() => { if (confirm("ออกจากระบบและล้างข้อมูลหน้าร้านที่ซิงก์แล้ว เพื่อเปลี่ยนผู้ใช้หรือบริษัท?")) void logout(); }}
            ><LogOut className="h-5 w-5" />{leaving ? "กำลังออกจากระบบ…" : "ออกจากระบบ / เปลี่ยนบริษัท"}</button>
          </div>
        </aside>
      </> : null}
    </div>

    {error && <p role="alert" className="mx-auto mt-3 max-w-5xl bg-red-50 p-4 text-red-800">{error}</p>}<main className="mx-auto max-w-5xl p-3 pb-[max(1.25rem,env(safe-area-inset-bottom))] md:p-5">
    <Routes><Route path="/" element={<Navigate to={landingPath} replace />} /><Route path="/login" element={<Navigate to={landingPath} replace />} />
      {STORE_ROUTES.map((route) => { const Page = pages[route.path]; return <Route key={route.path} path={route.path} element={allowedStoreRoute(route.path, session.permissions) ? <Page /> : <p role="alert">ไม่มีสิทธิ์ใช้งานหน้านี้</p>} />; })}
    </Routes></main></div>;
}
document.title = "Foodchainservice Takeaway Store UAT";
document.documentElement.classList.add("native-app", "native-android");
ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><QueryClientProvider client={queryClient}><BrowserRouter><StoreApp /><UpdateGate /><Toaster /></BrowserRouter></QueryClientProvider></React.StrictMode>);
