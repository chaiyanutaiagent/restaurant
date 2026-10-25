import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "@capacitor/app";
import { Capacitor, registerPlugin } from "@capacitor/core";
import ProductContextGuard from "@/components/auth/ProductContextGuard";
import { Toaster } from "@/components/ui/toaster";
import api from "@/lib/api";
import { nativeBusinessType, nativeHome, nativeTitle, nativeProduct } from "./config";
import { useAuthStore, restoreNativeSession, flushNativeSession } from "./session";
import { useLogout } from "@/hooks/useAuth";
import { useDeviceStore } from "@/stores/device.store";
import Login from "./Login";
import Device from "./Device";
import UpdateNotice from './UpdateNotice';
import { RetailWorkspaceFrame } from '@/components/pos/RetailWorkspaceNav';
import { usePendingPairing } from "./pairing";
import { hasNativePaymentPending, isPendingRestaurantBranchRestore } from "./paidOrderRecovery";
import { installNativeTransactionJournal, readNativeTransaction } from './transactionJournal';
import { nativeAssetUrls } from './assets';
// Vite replaces this entry with the selected product's routes, never the ERP App.
import { productRoutes } from "./RetailRoutes";
import "../index.css";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
api.defaults.timeout = 20_000;
if (Capacitor.isNativePlatform()) {
  const printer = registerPlugin<{ print(): Promise<void> }>('NativeDocumentPrinter');
  window.print = () => { void printer.print().catch(() => alert('เปิด Android Print Service ไม่ได้ กรุณาตรวจเครื่องพิมพ์ ไม่ต้องรับเงินซ้ำ')); };
}
installNativeTransactionJournal(api);
api.interceptors.response.use(response => { response.data = nativeAssetUrls(response.data); return response; });
const navigation = nativeProduct === 'retail' ? [
  ['/retail/pos','ขาย','pos.sale.create'], ['/retail/products/scan','เพิ่มสินค้า','inventory.product.create'],
  ['/retail/transfers','โอนสินค้า','inventory.transfer.view'], ['/retail/reports/skus','รายงาน SKU','pos.report.view'],
] : [
  ['/restaurant/pos','ขาย','pos.sale.create'], ['/restaurant/tables','โต๊ะ / QR','fb.table.manage'],
  ['/restaurant/orders','ออเดอร์','fb.order.create'], ['/restaurant/kitchen','ครัว','fb.kitchen.ticket.manage'],
  ['/restaurant/qr','QR รับกลับ','fb.settings.manage'],
];
api.interceptors.request.use(async config => {
  await flushNativeSession();
  const writes = !['get','head','options'].includes((config.method ?? 'get').toLowerCase());
  if (writes && !/^\/restaurant\/(wap\/orders|store\/[^/]+\/orders)$/.test(config.url ?? '')
      && !['/auth/refresh', '/auth/login', '/auth/logout'].includes(config.url ?? '') && await hasNativePaymentPending()) {
    if (config.url === '/auth/switch-branch' && await isPendingRestaurantBranchRestore(config.data?.branch_id)) return config;
    throw new Error('มีรายการรับเงินรอตรวจสอบ ต้องกู้คืนรายการเดิมก่อนทำรายการใหม่หรือเปลี่ยนสาขา');
  }
  return config;
});
function NativeApp() {
  const [ready, setReady] = useState(false);
  const [fatal, setFatal] = useState("");
  const session = useAuthStore();
  const logout = useLogout();
  const [pendingTransaction, setPendingTransaction] = useState(false);
  const pendingPair = usePendingPairing(state => state.pending);
  const pairingError = usePendingPairing(state => state.error);
  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;
    let active = true;
    const receive = (url: string) => { if (active) usePendingPairing.getState().receive(url); };
    const listener = App.addListener('appUrlOpen', event => receive(event.url));
    void App.getLaunchUrl().then(result => { if (result?.url) receive(result.url); }).catch(() => { if (active) usePendingPairing.setState({ error: "เปิดลิงก์ไม่สำเร็จ ให้สแกน QR หรือวางลิงก์ในแอป" }); });
    return () => { active = false; void listener.then(handle => handle.remove()); };
  }, []);
  useEffect(() => {
    const update = () => { void Promise.all([readNativeTransaction(), hasNativePaymentPending()]).then(([journal, wap]) => setPendingTransaction(Boolean(journal) || wap)).catch(() => setFatal('อ่านธุรกรรมค้างไม่ได้ กรุณาปิดและเปิดแอปใหม่')); };
    update(); window.addEventListener('native-pos-transaction', update);
    return () => window.removeEventListener('native-pos-transaction', update);
  }, []);
  useEffect(() => {
    const failure = () => setFatal("พื้นที่เก็บข้อมูลปลอดภัยไม่พร้อม กรุณาปิดและเปิดแอปใหม่ ยังไม่อนุญาตให้ทำรายการ");
    window.addEventListener('native-pos-storage-error', failure);
    void restoreNativeSession().then(() => useDeviceStore.getState().hydrate()).then(() => setReady(true)).catch(failure);
    // Do not navigate away from a live checkout when Android Back is pressed.
    const listener = Capacitor.isNativePlatform() ? App.addListener('backButton', () => {
      if (confirm('พักแอปไว้เบื้องหลัง? รายการที่กำลังทำจะไม่ถูกล้าง')) void App.minimizeApp();
    }) : null;
    return () => {window.removeEventListener('native-pos-storage-error', failure);void listener?.then(handle => handle.remove());};
  }, []);
  useEffect(() => {queryClient.clear();}, [session.companyId, session.brandId, session.branchId, session.user?.id]);
  if (fatal || !ready) return <main role="status" className="p-8">{fatal || 'กำลังเปิดแอป…'}</main>;
  if (!session.isAuthenticated()) return <><Login/><UpdateNotice/></>;
  const visible = navigation.filter(([, , permission]) => session.hasPermission(permission) || (permission === 'fb.kitchen.ticket.manage' && session.hasPermission('fb.kitchen.manage')));
  const landing = pendingPair ? '/native/device' : visible[0]?.[0] ?? '/native/device';
  return <div className="native-safe-screen bg-slate-50">
    <UpdateNotice />
    <header hidden={nativeProduct === 'retail'} className={nativeProduct === 'retail' ? 'hidden' : 'flex flex-wrap items-center gap-3 border-b bg-white p-3 text-sm'}>
      <strong>{nativeTitle} · UAT</strong>
      {visible.map(([path,label]) => <Link key={path} className="min-h-11 rounded border p-3" to={path} onClick={e => {if (!confirm('เปลี่ยนหน้างาน? กรุณาพักบิลก่อนหากมีสินค้าในตะกร้า')) e.preventDefault();}}>{label}</Link>)}
      <Link className="min-h-11 rounded border p-3" to="/native/device" onClick={e => {if (!confirm('เปิดตั้งค่าเครื่อง? กรุณาพักบิลก่อนหากมีสินค้าในตะกร้า')) e.preventDefault();}}>เครื่องขาย / พิมพ์</Link>
      <span>รุ่นออนไลน์ · {session.user?.display_name ?? session.user?.username}</span>
      <button className="min-h-11 rounded border p-3" onClick={() => {if(confirm('ออกจากระบบ? กรุณาพักบิลหรือทำรายการให้เสร็จก่อน')) logout();}}>ออกจากระบบ</button>
    </header>
    {pendingTransaction && <aside role="alert" className="bg-amber-100 p-3">มีธุรกรรมรอตรวจสอบ ห้ามรับเงินซ้ำ · <Link className="underline" to="/native/device">ตรวจรายการเดิม</Link></aside>}
    {pendingPair && <aside role="status" className="bg-blue-100 p-3">ได้รับ QR เครื่อง {pendingPair.deviceCode} · <Link className="underline" to="/native/device">ตรวจข้อมูลและยืนยันจับคู่</Link><button className="ml-4 underline" onClick={() => usePendingPairing.getState().clear()}>ยกเลิก</button></aside>}
    {pairingError && <aside role="alert" className="bg-red-100 p-3">{pairingError}</aside>}
    <Routes>
      <Route path="/" element={<Navigate to={landing} replace/>}/>
      <Route path="/login" element={<Navigate to={landing} replace/>}/>
      <Route path="/device/pair" element={<Navigate to="/native/device" replace/>}/>
      <Route path="/pos" element={<Navigate to={nativeHome} replace/>}/>
      <Route path="/admin" element={<Navigate to={landing} replace/>}/>
      <Route path="/branches/:id/settings" element={<main className="p-6">การตั้งค่าสาขาให้ผู้จัดการทำผ่านเว็บ · <a className="underline" href={`${import.meta.env.VITE_API_BASE_URL}/admin`} target="_blank" rel="noreferrer">เปิดหลังบ้าน UAT ในเบราว์เซอร์</a></main>}/>
      <Route element={<ProductContextGuard businessType={nativeBusinessType}/>}>{productRoutes}<Route path="/native/device" element={nativeProduct === 'retail' ? <RetailWorkspaceFrame section="settings"><Device/></RetailWorkspaceFrame> : <Device/>}/></Route>
      <Route path="*" element={<main className="p-6"><h1>หน้านี้ไม่เปิดในแอป หรือไม่มีสิทธิ์ใช้งาน</h1><Link to={nativeHome}>กลับหน้าขาย</Link></main>}/>
    </Routes><Toaster/>
  </div>;
}
document.title = `${nativeTitle} UAT`;
document.documentElement.classList.add('native-app', 'native-android');
ReactDOM.createRoot(document.getElementById('root')!).render(<QueryClientProvider client={queryClient}><BrowserRouter><NativeApp/></BrowserRouter></QueryClientProvider>);
