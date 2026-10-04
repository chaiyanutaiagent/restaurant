import axios from "axios";
import { CheckCircle2, Loader2 } from "lucide-react";
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { membershipApi } from "@/lib/api";

export default function VerifyEmailPage(): JSX.Element {
  const location = useLocation();
  const token = new URLSearchParams(location.hash.replace(/^#/, "")).get("token") ?? "";
  const businessSlug = window.localStorage.getItem("last_business_slug");
  const [loading, setLoading] = useState(false);
  const [companyId, setCompanyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function verify(): Promise<void> {
    setLoading(true); setError(null);
    try { const response = await membershipApi.verifyEmail(token); setCompanyId(response.data.data.membership?.company_id ?? null); }
    catch (caught) { setError(axios.isAxiosError(caught) ? String(caught.response?.data?.detail ?? "ยืนยันไม่สำเร็จ") : "ยืนยันไม่สำเร็จ"); }
    finally { setLoading(false); }
  }
  const loginPath = businessSlug ? `/${businessSlug}/login` : `/login?company_id=${companyId ?? ""}`;
  return <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4"><Card className="w-full max-w-md"><CardHeader><CardTitle>ยืนยันอีเมล</CardTitle></CardHeader><CardContent className="space-y-4 text-center">{companyId ? <><CheckCircle2 className="mx-auto h-12 w-12 text-emerald-600" /><p>ยืนยันสำเร็จและเริ่มช่วงทดลองใช้แล้ว</p><Button asChild><Link to={loginPath}>เข้าสู่ระบบ</Link></Button></> : <><p className="text-sm text-slate-600">กดยืนยันเพื่อเปิดช่วงทดลองใช้ 14 วัน</p>{error ? <p className="text-sm text-red-600">{error}</p> : null}<Button disabled={!token || loading} onClick={() => void verify()}>{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}ยืนยันอีเมล</Button></>}</CardContent></Card></div>;
}
