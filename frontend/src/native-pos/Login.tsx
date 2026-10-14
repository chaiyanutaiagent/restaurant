import { useState } from "react";
import { authApi, membershipApi } from "@/lib/api";
import { useAuthStore, flushNativeSession } from "./session";
import { nativeTitle } from "./config";

export default function Login() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return <main className="native-safe-screen grid min-h-[100dvh] place-items-center bg-slate-100 p-5">
    <form className="w-full max-w-md space-y-5 rounded-2xl bg-white p-6 shadow" onSubmit={async event => {
      event.preventDefault(); setBusy(true); setError("");
      const form = event.currentTarget;
      const data = new FormData(form);
      try {
        const businessCode = String(data.get("business")).trim().toLowerCase();
        if (!/^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$/.test(businessCode)) throw new Error("กรอกรหัสธุรกิจ ไม่ใช่ที่อยู่เว็บไซต์");
        const company = (await membershipApi.business(businessCode)).data.data;
        const tokens = (await authApi.login({ username: String(data.get("username")).trim(), password: String(data.get("password")), company_id: company.company_id }, company.company_id)).data.data;
        useAuthStore.getState().setSession(tokens, company.company_id);
        await flushNativeSession();
        form.reset();
      } catch (failure) { setError(failure instanceof Error && !('isAxiosError' in failure) ? failure.message : "เข้าสู่ระบบไม่ได้ ตรวจรหัสธุรกิจ บัญชี และการเชื่อมต่อ"); }
      finally { setBusy(false); }
    }}>
      <h1 className="text-2xl font-bold">{nativeTitle}</h1>
      <p className="text-sm text-amber-800">UAT · ออนไลน์เท่านั้น · ใช้บัญชีพนักงานของบริษัท</p>
      {[['business','รหัสธุรกิจ','text'],['username','ชื่อผู้ใช้','text'],['password','รหัสผ่าน','password']].map(([name,label,type]) => <label key={name} className="block">{label}<input name={name} type={type} required autoCapitalize="none" autoComplete={name === 'password' ? 'current-password' : name === 'username' ? 'username' : 'off'} className="mt-1 min-h-12 w-full rounded-lg border px-3 text-base" disabled={busy}/></label>)}
      {error && <p role="alert" className="text-red-700">{error}</p>}
      <button disabled={busy} className="min-h-12 w-full rounded-lg bg-blue-700 p-3 font-bold text-white disabled:opacity-50">{busy ? 'กำลังตรวจสิทธิ์…' : 'เข้าสู่ระบบ'}</button>
    </form>
  </main>;
}
