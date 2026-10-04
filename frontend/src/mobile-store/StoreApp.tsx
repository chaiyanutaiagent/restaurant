import { useEffect, useState, type ComponentType, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import TakeawayCounterPage from "@/pages/takeaway/TakeawayCounterPage";
import TakeawayCatalogPage from "@/pages/takeaway/TakeawayCatalogPage";
import TakeawayShiftPage from "@/pages/takeaway/TakeawayShiftPage";
import TakeawayStoreStockPage from "@/pages/takeaway/TakeawayStoreStockPage";
import TakeawayStoreCentralOrdersPage from "@/pages/takeaway/TakeawayStoreCentralOrdersPage";
import { STORE_ROUTES, allowedStoreRoute } from "./routes";
import { clearSession, restoreSession, useAuthStore } from "./session";
import { cleanupStoreData } from "./db";
import { onboardingApi } from "./api";
import Onboarding from "./Onboarding";
import { StoreCreditPage, StoreTransfersPage } from "./StoreSupportPages";
import { assertNoNativeDraft } from "@/lib/nativePosWorkGuard";
const pages = [TakeawayCounterPage, TakeawayCatalogPage, TakeawayShiftPage, TakeawayStoreStockPage,
  TakeawayStoreCentralOrdersPage, StoreTransfersPage, StoreCreditPage];

export default function StoreApp({ welcome, appName = "Foodchainservice Takeaway Store", DevicePage }: {
  welcome?: ReactNode; appName?: string; DevicePage: ComponentType;
}): JSX.Element {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const session = useAuthStore();
  const location = useLocation();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [leaving, setLeaving] = useState(false);
  useEffect(() => { void restoreSession().then(() => setReady(true)).catch(() => setError("เปิดที่เก็บข้อมูลปลอดภัยไม่ได้ กรุณาปิดและเปิดแอปอีกครั้ง")); }, []);
  useEffect(() => { queryClient.clear(); }, [session.companyId, session.branchId, session.user?.id]);
  if (!ready) return <p className="p-8" role="status">{error || "กำลังเปิดแอป…"}</p>;
  const forbidden = location.pathname !== "/" && location.pathname !== "/login"
    && !STORE_ROUTES.some((route) => route.path === location.pathname);
  if (forbidden) return <div className="p-8"><h1>ไม่อนุญาตให้เข้าหน้านี้</h1><Link to="/">กลับหน้าร้าน</Link></div>;
  if (!session.accessToken) return welcome && location.pathname === "/"
    ? <>{welcome}</> : <Onboarding appName={appName} />;
  const visible = STORE_ROUTES.filter((route) => session.hasPermission(route.permission));
  const landingPath = visible.find((route) => route.path === "/takeaway/store/orders")?.path
    ?? visible.find((route) => route.path === "/takeaway/store/stock")?.path
    ?? visible[0]?.path
    ?? "/login";
  async function logout() {
    setLeaving(true); setError("");
    try {
      assertNoNativeDraft();
      if (queryClient.isMutating()) throw new Error("กำลังบันทึกรายการ กรุณารอให้เสร็จก่อนออกจากระบบ");
      await queryClient.cancelQueries();
      await cleanupStoreData();
      await onboardingApi.post("/auth/logout", { refresh_token: session.refreshToken });
      await clearSession(); queryClient.clear(); navigate("/", { replace: true });
    } catch (failure) { setError(failure instanceof Error ? failure.message : "ออกจากระบบไม่ได้ กรุณาเชื่อมต่อและซิงก์ก่อน"); }
    finally { setLeaving(false); }
  }
  return <><header className="sticky top-0 z-30 space-y-3 bg-slate-950 p-4 text-white">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><strong>{appName}</strong><p className="text-sm">{session.businessSlug} · {session.user?.display_name || session.user?.username} · {session.stationKey} · UAT</p></div><button disabled={leaving} className="rounded border px-3 py-2" onClick={() => { if (confirm("ออกจากระบบและล้างข้อมูลหน้าร้านที่ซิงก์แล้ว เพื่อเปลี่ยนผู้ใช้หรือบริษัท?")) void logout(); }}>ออกจากระบบ / เปลี่ยนบริษัท</button></div>
    <nav className="flex gap-2 overflow-x-auto">{visible.map((route) => <Link className="whitespace-nowrap rounded bg-emerald-800 px-3 py-3" key={route.path} to={route.path} onClick={(event) => { if (location.pathname !== route.path) { try { assertNoNativeDraft(); } catch (failure) { event.preventDefault(); setError(failure instanceof Error ? failure.message : "กรุณาทำรายการให้เสร็จก่อน"); } } }}>{route.label}</Link>)}</nav>
  </header>{error && <p role="alert" className="bg-red-50 p-4 text-red-800">{error}</p>}<main className="p-3 md:p-5">
    <Routes><Route path="/" element={<Navigate to={landingPath} replace />} /><Route path="/login" element={<Navigate to={landingPath} replace />} />
      {STORE_ROUTES.map((route, index) => { const Page = route.path === "/takeaway/store/device" ? DevicePage : pages[index]; return <Route key={route.path} path={route.path} element={allowedStoreRoute(route.path, session.permissions) ? <Page /> : <p role="alert">ไม่มีสิทธิ์ใช้งานหน้านี้</p>} />; })}
    </Routes></main></>;
}
