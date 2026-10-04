import { zodResolver } from "@hookform/resolvers/zod";
import { Capacitor } from "@capacitor/core";
import { Eye, EyeOff, Loader2, LockKeyhole, ShieldCheck, ShoppingBag } from "lucide-react";
import { useRef, useState } from "react";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useLogin, useUatAutoLogin } from "@/hooks/useAuth";
import QaAccessPanel from "@/components/auth/QaAccessPanel";
import { membershipApi } from "@/lib/api";
import { PLATFORM_BRAND } from "@/config/platformBrand";

const loginSchema = z.object({
  company_id: z.string().optional(),
  business_code: z.string().optional(),
  username: z.string().min(1, "กรุณากรอกชื่อผู้ใช้"),
  password: z.string().min(1, "กรุณากรอกรหัสผ่าน")
});

type LoginFormValues = z.infer<typeof loginSchema>;

export default function LoginPage(): JSX.Element {
  const { businessSlug } = useParams();
  const canonicalSlug = businessSlug?.toLowerCase();
  const isNativeApp = Capacitor.isNativePlatform();
  const business = useQuery({
    queryKey: ["public-business", canonicalSlug],
    queryFn: async () => (await membershipApi.business(canonicalSlug ?? "")).data.data,
    enabled: Boolean(canonicalSlug),
    retry: false,
  });
  const defaultDestination = isNativeApp ? "/takeaway" : canonicalSlug ? `/${canonicalSlug}/admin` : "/admin";
  const { login, isLoading, error } = useLogin(defaultDestination);
  const { startAutoLogin, isLoading: isAutoLoginLoading } = useUatAutoLogin(defaultDestination);
  const autoLoginRequested = useRef(false);
  const [showPassword, setShowPassword] = useState(false);
  const isUatPublicHost = !isNativeApp && (
    window.location.hostname.startsWith("uat-")
    || ["localhost", "127.0.0.1"].includes(window.location.hostname)
  );
  const isUatAutoLogin = isUatPublicHost
    || (isNativeApp && import.meta.env.VITE_UAT_AUTO_LOGIN === "true");
  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      company_id: canonicalSlug ? "" : new URLSearchParams(window.location.search).get("company_id") ?? import.meta.env.VITE_COMPANY_ID ?? window.localStorage.getItem("last_company_id") ?? "",
      business_code: isNativeApp
        ? window.localStorage.getItem("last_business_slug") ?? import.meta.env.VITE_BUSINESS_SLUG ?? ""
        : canonicalSlug ?? "",
      username: isNativeApp ? "" : "admin",
      password: ""
    }
  });

  useEffect(() => {
    if (business.data) {
      form.setValue("company_id", business.data.company_id, { shouldValidate: true });
    }
  }, [business.data, form]);

  useEffect(() => {
    if (isUatAutoLogin && !autoLoginRequested.current) {
      autoLoginRequested.current = true;
      startAutoLogin();
    }
  }, [isUatAutoLogin, startAutoLogin]);

  async function onSubmit(values: LoginFormValues): Promise<void> {
    let companyId = values.company_id?.trim() ?? "";
    if (isNativeApp) {
      const businessCode = values.business_code?.trim().toLowerCase() ?? "";
      if (!businessCode) {
        form.setError("business_code", { message: "กรุณากรอกรหัสบริษัท" });
        return;
      }
      try {
        const response = await membershipApi.business(businessCode);
        companyId = response.data.data.company_id;
        window.localStorage.setItem("last_business_slug", response.data.data.business_slug);
        form.setValue("company_id", companyId);
      } catch {
        form.setError("business_code", { message: "ไม่พบรหัสบริษัท หรือบริษัทยังไม่เปิดใช้งาน" });
        return;
      }
    }
    if (!z.string().uuid().safeParse(companyId).success) {
      form.setError("company_id", { message: "กรุณากรอก Company ID ให้ถูกต้อง" });
      return;
    }
    await login({ company_id: companyId, username: values.username, password: values.password });
  }

  return (
    <div className={isNativeApp
      ? "native-safe-screen flex min-h-screen items-center justify-center bg-[linear-gradient(180deg,#ecfdf5_0%,#f8fafc_45%,#eef2f7_100%)] px-4 py-10"
      : "flex min-h-screen items-center justify-center bg-gray-50 px-4 py-10"}
    >
      <Card className="w-full max-w-md rounded-xl shadow-lg">
        <CardHeader className="items-center text-center">
          <div className={isNativeApp
            ? "mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-500 text-slate-950 shadow-sm"
            : "mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-600 text-white shadow-sm"}
          >
            {isNativeApp ? <ShoppingBag className="h-8 w-8" /> : <ShieldCheck className="h-8 w-8" />}
          </div>
          <CardTitle className="text-2xl">{isNativeApp ? "เข้าสู่ระบบ Takeaway" : "เข้าสู่ระบบ"}{business.data ? ` · ${business.data.name}` : ""}</CardTitle>
          <CardDescription>
            {isNativeApp
              ? "Foodchainservice Takeaway · สำหรับพนักงานร้าน"
              : canonicalSlug
                ? `${PLATFORM_BRAND.productName} · พื้นที่ธุรกิจ /${canonicalSlug}`
                : PLATFORM_BRAND.companyAdminName}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isAutoLoginLoading ? (
            <div className="mb-5 rounded-xl border border-amber-300 bg-amber-50 p-4 text-center text-sm font-semibold text-amber-950">
              กำลังเข้าสู่ระบบทดสอบอัตโนมัติ...
            </div>
          ) : null}
          {isUatPublicHost ? <QaAccessPanel defaultDestination={defaultDestination} /> : null}
          <form className="space-y-5" onSubmit={form.handleSubmit(onSubmit)}>
            {isNativeApp ? (
              <div className="space-y-2">
                <Label htmlFor="business_code">รหัสบริษัท</Label>
                <Input
                  autoCapitalize="none"
                  id="business_code"
                  placeholder="เช่น sketch-biz"
                  {...form.register("business_code")}
                />
                {form.formState.errors.business_code ? (
                  <p className="text-sm text-red-600">{form.formState.errors.business_code.message}</p>
                ) : (
                  <p className="text-xs text-slate-500">ใช้แอปเดียวได้ทุกบริษัท โดยกรอกรหัสเฉพาะครั้งแรก</p>
                )}
              </div>
            ) : null}
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
