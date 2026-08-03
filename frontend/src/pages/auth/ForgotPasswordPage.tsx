import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { membershipApi } from "@/lib/api";

export default function ForgotPasswordPage(): JSX.Element {
  const [email, setEmail] = useState(""); const [sent, setSent] = useState(false); const [loading, setLoading] = useState(false);
  async function submit(event: React.FormEvent): Promise<void> { event.preventDefault(); setLoading(true); try { await membershipApi.requestPasswordReset(email); setSent(true); } finally { setLoading(false); } }
  return <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4"><Card className="w-full max-w-md"><CardHeader><CardTitle>ลืมรหัสผ่าน</CardTitle></CardHeader><CardContent>{sent ? <div className="space-y-4 text-center"><p>หากอีเมลนี้มีสิทธิ์ ระบบจะส่งลิงก์ตั้งรหัสผ่านให้</p><Link className="text-blue-600" to="/login">กลับหน้าเข้าสู่ระบบ</Link></div> : <form className="space-y-4" onSubmit={submit}><div className="space-y-2"><Label htmlFor="email">อีเมลเจ้าของบัญชี</Label><Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></div><Button className="w-full" disabled={loading} type="submit">ขอลิงก์ตั้งรหัสผ่าน</Button></form>}</CardContent></Card></div>;
}
