import { useMutation } from "@tanstack/react-query";
import axios from "axios";
import { LockKeyhole, ShieldCheck } from "lucide-react";
import { type FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { platformApi, platformErrorMessage } from "@/lib/platformApi";
import { usePlatformAuthStore } from "@/stores/platform-auth.store";
import { PLATFORM_BRAND } from "@/config/platformBrand";

export default function PlatformLoginPage(): JSX.Element {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [mfaRequired, setMfaRequired] = useState(false);
  const setSession = usePlatformAuthStore((state) => state.setSession);
  const navigate = useNavigate();
  const location = useLocation();
  const requested = new URLSearchParams(location.search).get("next");
  const next = requested?.startsWith("/platform/") ? requested : "/platform/dashboard";
  const login = useMutation({
    mutationFn: () => platformApi.login(username, password, mfaCode),
    onSuccess: (response) => {
      setSession(response.data.data);
      navigate(next, { replace: true });
    },
    onError: (error) => {
      if (axios.isAxiosError(error) && error.response?.status === 428) setMfaRequired(true);
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate();
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-5 py-10 text-slate-100">
      <div className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-8 shadow-2xl shadow-emerald-950/30">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-400 text-slate-950">
            <ShieldCheck className="h-9 w-9" />
          </div>
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-emerald-300">
            {PLATFORM_BRAND.platformName}
          </p>
          <h1 className="mt-2 text-3xl font-bold">Platform Owner</h1>
          <p className="mt-2 text-sm text-slate-400">
            บัญชีนี้แยกจาก Company Owner และพนักงานร้านโดยสมบูรณ์
          </p>
        </div>
        <form className="space-y-5" onSubmit={submit}>
          <div className="space-y-2">
            <Label htmlFor="platform-username" className="text-slate-200">ชื่อผู้ใช้</Label>
            <Input
              id="platform-username"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </div>
          {mfaRequired ? (
            <div className="space-y-2">
              <Label htmlFor="platform-mfa-code" className="text-slate-200">MFA หรือ recovery code</Label>
              <Input
                id="platform-mfa-code"
                autoComplete="one-time-code"
                value={mfaCode}
                onChange={(event) => setMfaCode(event.target.value)}
                required
                autoFocus
              />
            </div>
          ) : null}
          <div className="space-y-2">
            <Label htmlFor="platform-password" className="text-slate-200">รหัสผ่าน</Label>
            <Input
              id="platform-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </div>
          {login.error ? (
            <p className="rounded-lg border border-red-800 bg-red-950/60 px-3 py-2 text-sm text-red-200">
              {platformErrorMessage(login.error)}
            </p>
          ) : null}
          <Button className="h-12 w-full bg-emerald-400 text-slate-950 hover:bg-emerald-300" disabled={login.isPending}>
            <LockKeyhole className="h-5 w-5" />
            {login.isPending ? "กำลังตรวจสอบ..." : "เข้าสู่ Platform Console"}
          </Button>
        </form>
      </div>
    </div>
  );
}
