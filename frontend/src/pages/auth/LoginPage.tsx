import { zodResolver } from "@hookform/resolvers/zod";
import { Capacitor } from "@capacitor/core";
import { Eye, EyeOff, Loader2, LockKeyhole, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useLogin } from "@/hooks/useAuth";
import QaAccessPanel from "@/components/auth/QaAccessPanel";
import { membershipApi } from "@/lib/api";
import { PLATFORM_BRAND } from "@/config/platformBrand";

const loginSchema = z.object({
  company_id: z.string().uuid("กรุณากรอก Company ID ให้ถูกต้อง"),
  username: z.string().min(1, "กรุณากรอกชื่อผู้ใช้"),
  password: z.string().min(1, "กรุณากรอกรหัสผ่าน")
});

type LoginFormValues = z.infer<typeof loginSchema>;

export default function LoginPage(): JSX.Element {
  const { businessSlug } = useParams();
  const canonicalSlug = businessSlug?.toLowerCase();
  const business = useQuery({
    queryKey: ["public-business", canonicalSlug],
    queryFn: async () => (await membershipApi.business(canonicalSlug ?? "")).data.data,
    enabled: Boolean(canonicalSlug),
    retry: false,
  });
  const defaultDestination = canonicalSlug ? `/${canonicalSlug}/admin` : "/admin";
  const { login, isLoading, error } = useLogin(defaultDestination);
  const [showPassword, setShowPassword] = useState(false);
  const isNativeApp = Capacitor.isNativePlatform();
  const isUatPublicHost = !isNativeApp && (
    window.location.hostname.startsWith("uat-")
    || ["localhost", "127.0.0.1"].includes(window.location.hostname)
  );
  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      company_id: canonicalSlug ? "" : new URLSearchParams(window.location.search).get("company_id") ?? import.meta.env.VITE_COMPANY_ID ?? window.localStorage.getItem("last_company_id") ?? "1b8a1818-44d6-4d5f-9d22-e5e17b23c081",
      username: isNativeApp ? "" : "admin",
      password: ""
    }
  });

  useEffect(() => {
    if (business.data) {
      form.setValue("company_id", business.data.company_id, { shouldValidate: true });
    }
  }, [business.data, form]);

  async function onSubmit(values: LoginFormValues): Promise<void> {
    await login(values);
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-10">
      <Card className="w-full max-w-md rounded-xl shadow-lg">
        <CardHeader className="items-center text-center">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-600 text-white shadow-sm">
            <ShieldCheck className="h-8 w-8" />
          </div>
          <CardTitle className="text-2xl">เข้าสู่ระบบ{business.data ? ` · ${business.data.name}` : ""}</CardTitle>
          <CardDescription>
            {isNativeApp
              ? "RESTAURANT POS · เข้าสู่ระบบพนักงาน"
              : canonicalSlug
                ? `${PLATFORM_BRAND.productName} · พื้นที่ธุรกิจ /${canonicalSlug}`
                : PLATFORM_BRAND.companyAdminName}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isUatPublicHost ? <QaAccessPanel defaultDestination={defaultDestination} /> : null}
          <form className="space-y-5" onSubmit={form.handleSubmit(onSubmit)}>
            <div className={isNativeApp || canonicalSlug ? "hidden" : "space-y-2"}>
              <Label htmlFor="company_id">Company ID</Label>
              <Input
                id="company_id"
                placeholder="UUID ของบริษัท"
                {...form.register("company_id")}
              />
              {form.formState.errors.company_id ? (
                <p className="text-sm text-red-600">{form.formState.errors.company_id.message}</p>
              ) : null}
            </div>

            {canonicalSlug && business.isLoading ? <p className="rounded-lg bg-slate-100 p-3 text-sm text-slate-600">กำลังตรวจสอบ URL ธุรกิจ...</p> : null}
            {canonicalSlug && business.isError ? <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">ไม่พบธุรกิจนี้ หรือธุรกิจยังไม่เปิดใช้งาน</p> : null}

            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input id="username" placeholder="ชื่อผู้ใช้" {...form.register("username")} />
              {form.formState.errors.username ? (
                <p className="text-sm text-red-600">{form.formState.errors.username.message}</p>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  placeholder="กรอกรหัสผ่าน"
                  type={showPassword ? "text" : "password"}
                  {...form.register("password")}
                />
                <button
                  className="absolute inset-y-0 right-3 flex items-center text-gray-400"
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {form.formState.errors.password ? (
                <p className="text-sm text-red-600">{form.formState.errors.password.message}</p>
              ) : null}
            </div>

            {error ? (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            ) : null}

            <Button className="w-full" disabled={isLoading || Boolean(canonicalSlug && !business.data)} type="submit">
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  กำลังเข้าสู่ระบบ
                </>
              ) : (
                <>
                  <LockKeyhole className="h-4 w-4" />
                  เข้าสู่ระบบ
                </>
              )}
            </Button>
            {!isNativeApp ? <div className="flex justify-between text-sm"><Link className="text-blue-600" to="/signup">เริ่มทดลองใช้</Link><Link className="text-blue-600" to="/forgot-password">ลืมรหัสผ่าน</Link></div> : null}
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
