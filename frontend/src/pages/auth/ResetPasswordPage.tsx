import axios from "axios";
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { membershipApi } from "@/lib/api";

export default function ResetPasswordPage(): JSX.Element {
  const location = useLocation(); const token = new URLSearchParams(location.hash.replace(/^#/, "")).get("token") ?? ""; const [password, setPassword] = useState(""); const [done, setDone] = useState(false); const [error, setError] = useState<string | null>(null);
  async function submit(event: React.FormEvent): Promise<void> { event.preventDefault(); setError(null); try { await membershipApi.resetPassword(token, password); setDone(true); } catch (caught) { setError(axios.isAxiosError(caught) ? String(caught.response?.data?.detail ?? "ตั้งรหัสผ่านไม่สำเร็จ") : "ตั้งรหัสผ่านไม่สำเร็จ"); } }
  return <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4"><Card className="w-full max-w-md"><CardHeader><CardTitle>ตั้งรหัสผ่านใหม่</CardTitle></CardHeader><CardContent>{done ? <div className="space-y-4 text-center"><p className="text-emerald-700">เปลี่ยนรหัสผ่านแล้ว และ session เดิมถูกเพิกถอน</p><Link className="text-blue-600" to="/login">เข้าสู่ระบบ</Link></div> : <form className="space-y-4" onSubmit={submit}><div className="space-y-2"><Label htmlFor="new-password">รหัสผ่านใหม่อย่างน้อย 12 ตัว</Label><Input id="new-password" type="password" minLength={12} required value={password} onChange={(e) => setPassword(e.target.value)} /></div>{error ? <p className="text-sm text-red-600">{error}</p> : null}<Button className="w-full" disabled={!token} type="submit">บันทึกรหัสผ่านใหม่</Button></form>}</CardContent></Card></div>;
}
