import { useCallback, useEffect, useState } from "react";
import { Download, Loader2, RefreshCw, ShieldCheck } from "lucide-react";
import { Capacitor } from "@capacitor/core";
import { installTakeawayRelease, loadTakeawayRelease, type TakeawayStoreRelease } from "./appUpdate";

const CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;

export default function UpdateGate(): JSX.Element | null {
  const [release, setRelease] = useState<TakeawayStoreRelease | null>(null);
  const [installing, setInstalling] = useState(false);
  const [dismissedVersion, setDismissedVersion] = useState<number | null>(null);
  const [message, setMessage] = useState("");

  const check = useCallback(async () => {
    if (!Capacitor.isNativePlatform() || Capacitor.getPlatform() !== "android") return;
    try {
      const latest = await loadTakeawayRelease();
      setRelease(latest.updateAvailable ? latest : null);
      setMessage("");
    } catch {
      // Update checks must never prevent a store from opening while offline.
    }
  }, []);

  useEffect(() => {
    void check();
    const online = () => { void check(); };
    window.addEventListener("online", online);
    const timer = window.setInterval(() => { void check(); }, CHECK_INTERVAL_MS);
    return () => { window.removeEventListener("online", online); window.clearInterval(timer); };
  }, [check]);

  if (!release || (!release.updateRequired && dismissedVersion === release.manifest.version_code)) return null;

  async function install() {
    setInstalling(true); setMessage("");
    try {
      await installTakeawayRelease(release!);
      setMessage("ดาวน์โหลดเสร็จแล้ว กรุณากดยืนยันในหน้าติดตั้งของ Android");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "เปิดตัวติดตั้งไม่สำเร็จ");
    } finally {
      setInstalling(false);
    }
  }

  return <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/75 p-4" role="dialog" aria-modal="true" aria-labelledby="store-update-title">
    <div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl">
      <div className="flex items-start gap-3">
        <span className="rounded-2xl bg-emerald-100 p-3 text-emerald-700"><ShieldCheck className="h-7 w-7" /></span>
        <div><h2 id="store-update-title" className="text-xl font-black">มีแอปเวอร์ชันใหม่</h2><p className="mt-1 text-sm text-slate-600">{release.installed.versionName} → {release.manifest.version_name}</p></div>
      </div>
      <p className="mt-5 text-sm leading-6 text-slate-700">ระบบตรวจลายเซ็นและไฟล์ก่อนเปิดตัวติดตั้ง ข้อมูลบริษัท รายการ Offline และการตั้งค่าเครื่องพิมพ์จะยังอยู่</p>
      {release.updateRequired ? <p className="mt-3 rounded-xl bg-amber-50 p-3 text-sm font-bold text-amber-900">เวอร์ชันนี้จำเป็นต้องอัปเดตก่อนใช้งานต่อ</p> : null}
      {message ? <p className="mt-3 rounded-xl bg-slate-100 p-3 text-sm" role="status">{message}</p> : null}
      <button disabled={installing} onClick={() => { void install(); }} className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-3 font-black text-slate-950 disabled:opacity-50">
        {installing ? <Loader2 className="h-5 w-5 animate-spin" /> : <Download className="h-5 w-5" />} {installing ? "กำลังดาวน์โหลดและตรวจสอบ…" : "ดาวน์โหลดและติดตั้ง"}
      </button>
      <button disabled={installing} onClick={() => { void check(); }} className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl border px-4 py-3 text-sm font-bold disabled:opacity-50"><RefreshCw className="h-4 w-4" /> ตรวจอีกครั้ง</button>
      {!release.updateRequired ? <button disabled={installing} onClick={() => setDismissedVersion(release.manifest.version_code)} className="mt-2 w-full px-4 py-2 text-sm font-bold text-slate-500 disabled:opacity-50">ไว้ทีหลัง</button> : null}
    </div>
  </div>;
}
