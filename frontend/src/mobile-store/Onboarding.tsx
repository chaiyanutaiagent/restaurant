import { useEffect, useRef, useState } from "react";
import { BrowserQRCodeReader, type IScannerControls } from "@zxing/browser";
import type { ApiResponse } from "@/types/api";
import type { TokenResponse } from "@/types/auth";
import { onboardingApi } from "./api";
import { businessCodeFromQr } from "./routes";
import { installationId, saveSession } from "./session";

export default function Onboarding(): JSX.Element {
  const [code, setCode] = useState("");
  const [business, setBusiness] = useState<{ business_code: string; name: string } | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [station, setStation] = useState("counter-1");
  const [branches, setBranches] = useState<Array<{ id: string; code: string; name: string }>>([]);
  const [branch, setBranch] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [scanning, setScanning] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    if (!scanning || !video.current) return;
    let controls: IScannerControls | undefined;
    let disposed = false;
    void new BrowserQRCodeReader().decodeFromVideoDevice(undefined, video.current, (result) => {
      if (result && !disposed) {
        try { setCode(businessCodeFromQr(result.getText())); setScanning(false); }
        catch (failure) { setError(String(failure)); }
      }
    }).then((value) => { controls = value; if (disposed) value.stop(); })
      .catch(() => { setError("เปิดกล้องไม่ได้ กรุณากรอก Business Code"); setScanning(false); });
    return () => { disposed = true; controls?.stop(); };
  }, [scanning]);
  async function submit() {
    setBusy(true); setError("");
    try {
      if (!business) {
        const resolved = await onboardingApi.get<ApiResponse<{ business_code: string; name: string }>>(`/mobile-store/businesses/${businessCodeFromQr(code)}`);
        setBusiness(resolved.data.data);
        return;
      }
      const payload = { business_code: business.business_code, username, password,
        station_key: station, device_id: await installationId() };
      if (!branches.length) {
        const result = await onboardingApi.post<ApiResponse<Array<{ id: string; code: string; name: string }>>>("/mobile-store/branches", payload);
        setBranches(result.data.data); setBranch(result.data.data[0]?.id ?? "");
        return;
      }
      const result = await onboardingApi.post<ApiResponse<TokenResponse>>("/mobile-store/login", { ...payload, branch_id: branch });
      await saveSession({ tokens: result.data.data, companyId: result.data.data.user.company_id, deviceId: payload.device_id });
      setPassword("");
    } catch {
      setError("เข้าสู่ระบบไม่สำเร็จ ตรวจรหัสบริษัท บัญชี สิทธิ์สาขา และการเชื่อมต่อ");
    } finally { setBusy(false); }
  }
  return <div className="mx-auto my-8 max-w-md space-y-5 rounded-2xl bg-white p-6 shadow">
    <h1 className="text-2xl font-bold">Foodchainservice Takeaway Store</h1>
    <p>UAT · พนักงานหน้าร้าน</p>
    <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
      {!business ? <>
        <label className="block">Business Code<input className="mt-1 w-full rounded border p-3" aria-label="Business Code" value={code} onChange={(event) => setCode(event.target.value)} required /></label>
        <button type="button" className="rounded border p-3" onClick={() => setScanning(!scanning)}>{scanning ? "ปิดกล้อง" : "สแกน QR บริษัท"}</button>
        {scanning && <video ref={video} autoPlay playsInline muted className="w-full" />}
      </> : <>
        <p className="rounded bg-emerald-50 p-3">{business.name} · {business.business_code}</p>
        <label className="block">ชื่อผู้ใช้<input aria-label="ชื่อผู้ใช้" className="mt-1 w-full rounded border p-3" value={username} onChange={(event) => { setUsername(event.target.value); setBranches([]); }} required autoComplete="username" /></label>
        <label className="block">รหัสผ่าน<input aria-label="รหัสผ่าน" type="password" className="mt-1 w-full rounded border p-3" value={password} onChange={(event) => { setPassword(event.target.value); setBranches([]); }} required autoComplete="current-password" /></label>
        <label className="block">จุดขาย<input aria-label="จุดขาย" className="mt-1 w-full rounded border p-3" value={station} pattern="[a-zA-Z0-9_-]+" onChange={(event) => { setStation(event.target.value); setBranches([]); }} required /></label>
        {branches.length > 0 && <label className="block">สาขา<select aria-label="สาขา" className="mt-1 w-full rounded border p-3" value={branch} onChange={(event) => setBranch(event.target.value)}>{branches.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></label>}
        <button type="button" className="underline" onClick={() => { setBusiness(null); setBranches([]); setUsername(""); setPassword(""); }}>เปลี่ยนบริษัท</button>
      </>}
      {error && <p role="alert" className="text-red-700">{error}</p>}
      <button disabled={busy} className="w-full rounded-xl bg-emerald-700 p-3 font-bold text-white">{busy ? "กำลังตรวจสอบ…" : !business ? "ตรวจสอบบริษัท" : !branches.length ? "ตรวจสอบบัญชีและสาขา" : "เข้าใช้งานสาขานี้"}</button>
    </form>
  </div>;
}
