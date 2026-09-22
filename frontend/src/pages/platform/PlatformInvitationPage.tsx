import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, ShieldCheck } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { platformApi, platformErrorMessage } from "@/lib/platformApi";

export default function PlatformInvitationPage(): JSX.Element {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const accept = useMutation({ mutationFn: () => platformApi.acceptTeamInvitation(token, password) });
  const submit = (event: FormEvent) => { event.preventDefault(); if (password === confirmation) accept.mutate(); };
  return <div className="flex min-h-screen items-center justify-center bg-slate-950 px-5 py-10 text-slate-100"><div className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-8">
    <div className="mb-7 flex items-center gap-3"><span className="rounded-xl bg-emerald-400 p-3 text-slate-950"><ShieldCheck className="h-7 w-7" /></span><div><p className="text-xs font-semibold uppercase tracking-wider text-emerald-300">Platform Team</p><h1 className="text-2xl font-bold">รับคำเชิญ</h1></div></div>
    {accept.isSuccess ? <div className="rounded-xl border border-emerald-800 bg-emerald-950/30 p-5"><CheckCircle2 className="h-8 w-8 text-emerald-300" /><h2 className="mt-3 font-semibold">สร้างบัญชีเรียบร้อย</h2><p className="mt-1 text-sm text-slate-400">เข้าสู่ระบบด้วย username ในคำเชิญและรหัสผ่านที่เพิ่งกำหนด</p><Button asChild className="mt-5 w-full"><Link to="/platform/login">ไปหน้าเข้าสู่ระบบ</Link></Button></div> : <form className="space-y-5" onSubmit={submit}>
      {!token ? <p className="rounded-lg border border-red-800 bg-red-950/40 p-3 text-sm text-red-200">ลิงก์คำเชิญไม่สมบูรณ์</p> : null}
      <div className="space-y-2"><Label htmlFor="invite-password">รหัสผ่านใหม่อย่างน้อย 12 ตัว</Label><Input id="invite-password" type="password" minLength={12} value={password} onChange={(event) => setPassword(event.target.value)} required /></div>
      <div className="space-y-2"><Label htmlFor="invite-confirmation">ยืนยันรหัสผ่าน</Label><Input id="invite-confirmation" type="password" minLength={12} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required /></div>
      {confirmation && password !== confirmation ? <p className="text-sm text-amber-300">รหัสผ่านไม่ตรงกัน</p> : null}
      {accept.error ? <p className="rounded-lg border border-red-800 bg-red-950/40 p-3 text-sm text-red-200">{platformErrorMessage(accept.error)}</p> : null}
      <Button className="w-full bg-emerald-400 text-slate-950 hover:bg-emerald-300" disabled={!token || password.length < 12 || password !== confirmation || accept.isPending}>สร้างบัญชี Platform</Button>
    </form>}
  </div></div>;
}
