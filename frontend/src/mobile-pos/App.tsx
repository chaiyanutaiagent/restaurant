import { lazy, Suspense, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { App as NativeApp } from "@capacitor/app";
import { Capacitor } from "@capacitor/core";
import { useAuthStore, restoreSession, type PosProduct } from "./session";
import { useLogout } from "./useAuth";
import Onboarding from "../mobile-store/Onboarding";
import StoreApp from "../mobile-store/StoreApp";
import Launcher from "./Launcher";
import DevicePage from "./DevicePage";
import { assertNoNativeDraft } from "../lib/nativePosWorkGuard";

const POSPage = lazy(() => import("../pages/pos/POSPage"));
const Tables = lazy(() => import("../pages/restaurant/TableMapPage"));
const Session = lazy(() => import("../pages/restaurant/SessionDetailPage"));
const Checkout = lazy(() => import("../pages/restaurant/SessionCheckoutPage"));
const Kitchen = lazy(() => import("../pages/restaurant/KitchenDisplayPage"));
const Orders = lazy(() => import("../pages/restaurant/FBOrdersPage"));
const Customers = lazy(() => import("../pages/crm/CRMPage"));
const QR = lazy(() => import("../pages/restaurant/QRManagerPage"));

export default function PosApp(): JSX.Element {
  const state = useAuthStore(), location = useLocation(), navigate = useNavigate(), client = useQueryClient();
  const [ready, setReady] = useState(false), [error, setError] = useState("");
  const logout = useLogout();
  const permitted = (permissions: string[], element: JSX.Element) => permissions.some(state.hasPermission) ? element : <p role="alert" className="p-6">ไม่มีสิทธิ์ใช้งานหน้านี้</p>;
  useEffect(() => { void restoreSession().then(() => setReady(true)).catch(() => setError("เปิดข้อมูลปลอดภัยไม่ได้ กรุณาปิดแล้วเปิดแอปใหม่")); }, []);
  useEffect(() => { client.clear(); }, [client, state.companyId, state.branchId, state.businessType, state.user?.id]);
  useEffect(() => {
    if (Capacitor.getPlatform() !== "android") return;
    const listener = NativeApp.addListener("backButton", () => {
      try { assertNoNativeDraft(); if (client.isMutating()) throw new Error("กำลังบันทึกข้อมูล"); navigate("/", { replace: true }); }
      catch (failure) { setError(failure instanceof Error ? failure.message : "กรุณาทำรายการให้เสร็จก่อน"); }
    });
    return () => { void listener.then((handle) => handle.remove()); };
  }, [navigate, client]);
  if (!ready) return <p role="status" className="p-8">{error || "กำลังเปิดแอป…"}</p>;
  const connect = location.pathname.match(/^\/connect\/(takeaway|restaurant|retail_pos)$/);
  if (!state.accessToken) {
    if (location.pathname === "/") return <Launcher />;
    if (connect) return <><Link className="m-4 inline-block p-3" to="/">กลับไปเลือกระบบ</Link><Onboarding key={connect[1]} appName={`Foodchainservice POS · ${connect[1]}`} product={connect[1]} /></>;
    return <Navigate to="/" replace />;
  }
  const product = state.businessType as PosProduct;
  const landing = product === "takeaway" ? "/takeaway/store/orders"
    : product === "retail_pos" ? (state.hasPermission("pos.sale.create") ? "/retail/pos" : "/device")
      : state.hasPermission("pos.sale.create") ? "/restaurant/pos"
        : state.hasPermission("fb.kitchen.manage") || state.hasPermission("fb.kitchen.ticket.manage") ? "/restaurant/kitchen"
          : state.hasPermission("fb.menu.view") ? "/restaurant/tables" : "/device";
  if (connect || location.pathname === "/login") return <Navigate to="/" replace />;
  if (product === "takeaway") return <>{error && <p className="bg-amber-100 p-4" role="alert">{error}</p>}<StoreApp appName="Foodchainservice POS UAT · Takeaway" DevicePage={DevicePage} /></>;
  const links = product === "restaurant" ? [
    ["ขาย", "/restaurant/pos", "pos.sale.create"], ["โต๊ะ + QR", "/restaurant/tables", "fb.menu.view"],
    ["ออร์เดอร์", "/restaurant/orders", "fb.menu.view"], ["ครัว", "/restaurant/kitchen", state.hasPermission("fb.kitchen.ticket.manage") ? "fb.kitchen.ticket.manage" : "fb.kitchen.manage"],
  ] : [["ขาย / คืนสินค้า / กะ", "/retail/pos", "pos.sale.create"]];
  function safeGo(path: string) {
    try { assertNoNativeDraft(); if (client.isMutating()) throw new Error("กำลังบันทึกข้อมูล"); setError(""); navigate(path); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "เปลี่ยนหน้าไม่ได้"); }
  }
  return <><header className="flex flex-wrap items-center gap-2 bg-slate-950 p-3 text-white">
    <strong className="mr-auto">Foodchainservice POS · {product === "retail_pos" ? "Retail" : "Restaurant"} · UAT</strong>
    {links.filter((link) => state.hasPermission(link[2])).map(([label, path]) => <button className="rounded border px-4 py-3" key={path} onClick={() => safeGo(path)}>{label}</button>)}
    <button className="rounded border px-4 py-3" onClick={() => safeGo("/device")}>เครื่องพิมพ์</button>
    <button className="rounded border px-4 py-3" onClick={logout}>ออกจากระบบ / เปลี่ยนร้าน</button>
  </header>{error && <p className="bg-amber-100 p-4" role="alert">{error}</p>}
    <Suspense fallback={<p className="p-8" role="status">กำลังโหลดหน้าร้าน…</p>}><Routes>
      <Route path="/" element={<Navigate to={landing} replace />} />
      <Route path="/pos" element={<Navigate to={landing} replace />} />
      <Route path="/device" element={<DevicePage />} />
      <Route path={product === "retail_pos" ? "/retail/pos" : "/restaurant/pos"} element={permitted(["pos.sale.create"], <POSPage />)} />
      <Route path="/crm" element={permitted(["pos.sale.view"], <Customers />)} />
      {product === "restaurant" && <>
        <Route path="/restaurant/tables" element={permitted(["fb.menu.view"], <Tables />)} />
        <Route path="/restaurant/orders" element={permitted(["fb.menu.view"], <Orders />)} />
        <Route path="/restaurant/qr" element={permitted(["fb.table.manage"], <QR />)} />
        <Route path="/restaurant/session/:sessionId" element={permitted(["fb.menu.view"], <Session />)} />
        <Route path="/restaurant/session/:sessionId/detail" element={permitted(["fb.menu.view"], <Session />)} />
        <Route path="/restaurant/session/:sessionId/checkout" element={permitted(["fb.order.create"], <Checkout />)} />
        <Route path="/restaurant/kitchen" element={permitted(["fb.kitchen.manage", "fb.kitchen.ticket.manage"], <Kitchen />)} />
      </>}
      <Route path="*" element={<div className="p-8"><h1>ไม่อนุญาตให้เข้าหน้านี้</h1><Link to="/">กลับหน้าร้าน</Link></div>} />
    </Routes></Suspense></>;
}
