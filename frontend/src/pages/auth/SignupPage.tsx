import axios from "axios";
import { ArrowLeft, Loader2, Store } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { membershipApi } from "@/lib/api";

function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) return String(error.response?.data?.detail ?? "สมัครใช้งานไม่สำเร็จ");
  return "สมัครใช้งานไม่สำเร็จ";
}

export default function SignupPage(): JSX.Element {
  const [form, setForm] = useState({ company_name: "", business_slug: "", owner_display_name: "", owner_email: "", username: "", password: "", phone: "" });
  const [accepted, setAccepted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [companyId, setCompanyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await membershipApi.signup({
        ...form,
        phone: form.phone || null,
        terms_accepted: accepted,
        privacy_accepted: accepted
      });
      setCompanyId(response.data.data.company_id);
      window.localStorage.setItem("last_company_id", response.data.data.company_id);
      window.localStorage.setItem("last_business_slug", response.data.data.business_slug);
      setForm((current) => ({ ...current, business_slug: response.data.data.business_slug }));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <Card className="w-full max-w-xl shadow-lg">
        <CardHeader className="text-center"><Link className="mb-2 inline-flex items-center justify-center gap-1 text-sm text-slate-500 hover:text-blue-700" to="/signup"><ArrowLeft className="h-4 w-4" />เลือกประเภทระบบอีกครั้ง</Link><Store className="mx-auto h-10 w-10 text-blue-600" /><CardTitle>เริ่มทดลอง Restaurant SaaS</CardTitle><CardDescription>สร้าง Company Owner สำหรับระบบร้านอาหารและคาเฟ่</CardDescription></CardHeader>
        <CardContent>
          {companyId ? (
            <div className="space-y-4 text-center"><p className="text-lg font-semibold text-emerald-700">สร้างบัญชีแล้ว กรุณาตรวจอีเมลเพื่อยืนยัน</p><div className="rounded-lg bg-slate-100 p-4"><p className="text-xs text-slate-500">URL ธุรกิจ</p><p className="mt-1 break-all font-mono text-sm">/{form.business_slug}</p></div><Button asChild><Link to={`/${form.business_slug}/login`}>ไปหน้าเข้าสู่ระบบของธุรกิจ</Link></Button></div>
          ) : (
            <form className="space-y-4" onSubmit={submit}>
              <div className="grid gap-4 sm:grid-cols-2"><div className="space-y-2"><Label htmlFor="company_name">ชื่อร้าน/บริษัท</Label><Input id="company_name" required value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })} /></div><div className="space-y-2"><Label htmlFor="owner_display_name">ชื่อเจ้าของ</Label><Input id="owner_display_name" required value={form.owner_display_name} onChange={(e) => setForm({ ...form, owner_display_name: e.target.value })} /></div></div>
              <div className="space-y-2"><Label htmlFor="business_slug">URL ธุรกิจ *</Label><div className="flex items-center gap-2"><span className="text-sm text-slate-500">/</span><Input id="business_slug" required minLength={3} maxLength={63} pattern="[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])" placeholder="coffee-house" value={form.business_slug} onChange={(e) => setForm({ ...form, business_slug: e.target.value.toLowerCase() })} /></div><p className="text-xs text-slate-500">ใช้ตัวอักษรอังกฤษพิมพ์เล็ก ตัวเลข และขีดกลาง เช่น coffee-house</p></div>
              <div className="space-y-2"><Label htmlFor="owner_email">อีเมลเจ้าของ</Label><Input id="owner_email" type="email" required value={form.owner_email} onChange={(e) => setForm({ ...form, owner_email: e.target.value })} /></div>
              <div className="grid gap-4 sm:grid-cols-2"><div className="space-y-2"><Label htmlFor="username">Username</Label><Input id="username" minLength={3} required value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></div><div className="space-y-2"><Label htmlFor="phone">เบอร์โทร (ถ้ามี)</Label><Input id="phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></div></div>
              <div className="space-y-2"><Label htmlFor="password">รหัสผ่านอย่างน้อย 12 ตัว</Label><Input id="password" type="password" minLength={12} required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div>
              <label className="flex items-start gap-3 rounded-lg border p-3 text-sm"><input className="mt-1" type="checkbox" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} /><span>ฉันยอมรับเงื่อนไขการใช้งานและนโยบายความเป็นส่วนตัวฉบับปัจจุบัน</span></label>
              {error ? <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
              <Button className="w-full" disabled={submitting || !accepted} type="submit">{submitting ? <><Loader2 className="h-4 w-4 animate-spin" />กำลังสร้างบัญชี</> : "เริ่มทดลองใช้"}</Button>
              <p className="text-center text-sm text-slate-500">มีบัญชีแล้ว? <Link className="text-blue-600" to="/login">เข้าสู่ระบบ</Link></p>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
