import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Laptop, LogOut, RefreshCw, ShieldCheck, ShieldOff, Trash2 } from "lucide-react";
import QRCode from "qrcode";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { platformApi, platformErrorMessage } from "@/lib/platformApi";
import { usePlatformAuthStore } from "@/stores/platform-auth.store";
import type { PlatformMfaSetup } from "@/types/platform";

export default function PlatformSecurityPage(): JSX.Element {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const operator = usePlatformAuthStore((state) => state.operator);
  const setOperator = usePlatformAuthStore((state) => state.setOperator);
  const clearSession = usePlatformAuthStore((state) => state.clearSession);
  const [setup, setSetup] = useState<PlatformMfaSetup | null>(null);
  const [qrCode, setQrCode] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [password, setPassword] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");

  const sessions = useQuery({
    queryKey: ["platform", "security", "sessions"],
    queryFn: async () => (await platformApi.sessions()).data.data,
  });
  const setupMfa = useMutation({
    mutationFn: async () => (await platformApi.setupMfa()).data.data,
    onSuccess: async (result) => {
      setSetup(result);
      setQrCode(await QRCode.toDataURL(result.provisioning_uri, { width: 220, margin: 1 }));
      setRecoveryCodes([]);
    },
  });
  const confirmMfa = useMutation({
    mutationFn: async () => (await platformApi.confirmMfa(mfaCode)).data.data,
    onSuccess: (result) => {
      setOperator(result.operator);
      setRecoveryCodes(result.recovery_codes);
      setSetup(null);
      setQrCode(null);
      setMfaCode("");
      void queryClient.invalidateQueries({ queryKey: ["platform", "security", "sessions"] });
    },
  });
  const rotateRecovery = useMutation({
    mutationFn: async () => (await platformApi.regenerateRecoveryCodes(mfaCode)).data.data,
    onSuccess: (result) => {
      setRecoveryCodes(result.recovery_codes);
      setMfaCode("");
    },
  });
  const disableMfa = useMutation({
    mutationFn: async () => (await platformApi.disableMfa(password, mfaCode)).data.data,
    onSuccess: (result) => {
      setOperator(result);
      setPassword("");
      setMfaCode("");
      setRecoveryCodes([]);
    },
  });
  const revokeSession = useMutation({
    mutationFn: (sessionId: string) => platformApi.revokeSession(sessionId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["platform", "security", "sessions"] }),
  });
  const logoutAll = useMutation({
    mutationFn: () => platformApi.logoutAll(),
    onSuccess: () => {
      clearSession();
      navigate("/platform/login", { replace: true });
    },
  });
  const changePassword = useMutation({
    mutationFn: () => platformApi.changePassword(currentPassword, newPassword, mfaCode),
    onSuccess: () => {
      clearSession();
      navigate("/platform/login", { replace: true });
    },
  });
  const mutationError = setupMfa.error ?? confirmMfa.error ?? rotateRecovery.error
    ?? disableMfa.error ?? revokeSession.error ?? logoutAll.error ?? changePassword.error;

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm font-medium text-emerald-300">Platform authentication</p>
        <h2 className="mt-1 text-3xl font-bold">ความปลอดภัย</h2>
        <p className="mt-2 text-sm text-slate-400">MFA, recovery codes, password และ browser sessions ของ Platform Owner เท่านั้น</p>
      </header>

      {mutationError ? <p className="rounded-xl border border-red-900 bg-red-950/40 p-4 text-sm text-red-200">{platformErrorMessage(mutationError)}</p> : null}

      <section className="rounded-2xl border border-slate-700 bg-slate-900 p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex gap-3">
            {operator?.mfa_enabled ? <ShieldCheck className="h-6 w-6 text-emerald-300" /> : <ShieldOff className="h-6 w-6 text-amber-300" />}
            <div>
              <h3 className="text-xl font-semibold">Multi-factor authentication</h3>
              <p className="mt-1 text-sm text-slate-400">{operator?.mfa_enabled ? "เปิดใช้งานแล้ว ทุก login ต้องใช้ TOTP หรือ recovery code" : "ยังไม่เปิด แนะนำให้ตั้งค่าก่อนเปิด Beta"}</p>
            </div>
          </div>
          {!operator?.mfa_enabled && !setup ? <Button onClick={() => setupMfa.mutate()} disabled={setupMfa.isPending}>เริ่มตั้งค่า MFA</Button> : null}
        </div>

        {setup ? (
          <div className="mt-6 grid gap-6 rounded-xl bg-slate-950 p-5 md:grid-cols-[220px_1fr]">
            {qrCode ? <img src={qrCode} alt="Platform MFA QR code" className="rounded-lg bg-white" /> : <div className="h-[220px] animate-pulse rounded-lg bg-slate-800" />}
            <div>
              <p className="font-semibold">สแกนด้วย Authenticator แล้วกรอกรหัส 6 หลัก</p>
              <p className="mt-3 break-all rounded-lg bg-slate-900 px-3 py-2 font-mono text-xs text-slate-300">Secret: {setup.secret}</p>
              <div className="mt-4 max-w-sm space-y-2"><Label htmlFor="mfa-confirm-code">รหัสยืนยัน</Label><Input id="mfa-confirm-code" autoComplete="one-time-code" value={mfaCode} onChange={(event) => setMfaCode(event.target.value)} /></div>
              <Button className="mt-4 bg-emerald-400 text-slate-950 hover:bg-emerald-300" onClick={() => confirmMfa.mutate()} disabled={confirmMfa.isPending || !mfaCode.trim()}>ยืนยันและเปิด MFA</Button>
            </div>
          </div>
        ) : null}

        {operator?.mfa_enabled ? (
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <div className="space-y-2"><Label htmlFor="mfa-action-code">TOTP หรือ recovery code</Label><Input id="mfa-action-code" value={mfaCode} onChange={(event) => setMfaCode(event.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="mfa-password">รหัสผ่าน (ใช้เฉพาะตอนปิด MFA)</Label><Input id="mfa-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></div>
            <div className="flex flex-wrap gap-3 md:col-span-2">
              <Button variant="outline" onClick={() => rotateRecovery.mutate()} disabled={!mfaCode.trim() || rotateRecovery.isPending}><RefreshCw className="h-4 w-4" />สร้าง recovery codes ชุดใหม่</Button>
              <Button variant="destructive" onClick={() => disableMfa.mutate()} disabled={!mfaCode.trim() || !password || disableMfa.isPending}><ShieldOff className="h-4 w-4" />ปิด MFA</Button>
            </div>
          </div>
        ) : null}

        {recoveryCodes.length ? (
          <div className="mt-6 rounded-xl border border-amber-800 bg-amber-950/30 p-5">
            <p className="font-semibold text-amber-100">บันทึก recovery codes ตอนนี้ — ระบบจะแสดงครั้งเดียว</p>
            <div className="mt-3 grid gap-2 font-mono text-sm text-amber-200 sm:grid-cols-2">{recoveryCodes.map((code) => <span key={code}>{code}</span>)}</div>
          </div>
        ) : null}
      </section>

      <section className="rounded-2xl border border-slate-700 bg-slate-900 p-6">
        <div className="flex items-center gap-3"><Laptop className="h-6 w-6 text-sky-300" /><div><h3 className="text-xl font-semibold">Browser sessions</h3><p className="text-sm text-slate-400">เพิกถอนเครื่องที่ไม่รู้จักได้ทันที</p></div></div>
        {sessions.isLoading ? <p className="mt-5 text-sm text-slate-400">กำลังโหลด sessions...</p> : null}
        {sessions.error ? <p className="mt-5 text-sm text-red-300">{platformErrorMessage(sessions.error)}</p> : null}
        <div className="mt-5 space-y-3">
          {sessions.data?.map((session) => (
            <article key={session.id} className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-700 px-4 py-3">
              <div><p className="font-medium">{session.current ? "เครื่องนี้" : session.user_agent || "Unknown browser"}</p><p className="mt-1 text-xs text-slate-500">IP {session.ip_address || "unknown"} · ล่าสุด {new Date(session.last_seen_at).toLocaleString("th-TH")} · {session.revoked_at ? "REVOKED" : "ACTIVE"}</p></div>
              {!session.revoked_at ? <Button size="sm" variant="outline" onClick={() => revokeSession.mutate(session.id)}><Trash2 className="h-4 w-4" />เพิกถอน</Button> : null}
            </article>
          ))}
        </div>
        <Button className="mt-5" variant="destructive" onClick={() => logoutAll.mutate()}><LogOut className="h-4 w-4" />ออกจากระบบทุกเครื่อง</Button>
      </section>

      <section className="rounded-2xl border border-slate-700 bg-slate-900 p-6">
        <div className="flex items-center gap-3"><KeyRound className="h-6 w-6 text-violet-300" /><div><h3 className="text-xl font-semibold">เปลี่ยนรหัสผ่าน</h3><p className="text-sm text-slate-400">เมื่อเปลี่ยนสำเร็จทุก session จะถูกเพิกถอน</p></div></div>
        <div className="mt-5 grid gap-4 md:grid-cols-3">
          <div className="space-y-2"><Label htmlFor="current-password">รหัสผ่านปัจจุบัน</Label><Input id="current-password" type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} /></div>
          <div className="space-y-2"><Label htmlFor="new-password">รหัสผ่านใหม่อย่างน้อย 12 ตัว</Label><Input id="new-password" type="password" minLength={12} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /></div>
          <div className="space-y-2"><Label htmlFor="password-mfa">MFA (ถ้าเปิดใช้งาน)</Label><Input id="password-mfa" value={mfaCode} onChange={(event) => setMfaCode(event.target.value)} /></div>
        </div>
        <Button className="mt-5" onClick={() => changePassword.mutate()} disabled={!currentPassword || newPassword.length < 12 || changePassword.isPending}>เปลี่ยนรหัสผ่านและออกทุกเครื่อง</Button>
      </section>
    </div>
  );
}
