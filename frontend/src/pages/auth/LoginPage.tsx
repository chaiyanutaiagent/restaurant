import { zodResolver } from "@hookform/resolvers/zod";
import { Capacitor } from "@capacitor/core";
import { Eye, EyeOff, Loader2, LockKeyhole, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useLogin } from "@/hooks/useAuth";

const loginSchema = z.object({
  company_id: z.string().uuid("กรุณากรอก Company ID ให้ถูกต้อง"),
  username: z.string().min(1, "กรุณากรอกชื่อผู้ใช้"),
  password: z.string().min(1, "กรุณากรอกรหัสผ่าน")
});

type LoginFormValues = z.infer<typeof loginSchema>;

export default function LoginPage(): JSX.Element {
  const { login, isLoading, error } = useLogin();
  const [showPassword, setShowPassword] = useState(false);
  const isNativeApp = Capacitor.isNativePlatform();
  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      company_id: import.meta.env.VITE_COMPANY_ID ?? window.localStorage.getItem("last_company_id") ?? "1b8a1818-44d6-4d5f-9d22-e5e17b23c081",
      username: isNativeApp ? "" : "admin",
      password: ""
    }
  });

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
          <CardTitle className="text-2xl">เข้าสู่ระบบ</CardTitle>
          <CardDescription>{isNativeApp ? "RESTAURANT POS · เข้าสู่ระบบพนักงาน" : "Restaurant POS System"}</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-5" onSubmit={form.handleSubmit(onSubmit)}>
            <div className={isNativeApp ? "hidden" : "space-y-2"}>
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

            <Button className="w-full" disabled={isLoading} type="submit">
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
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
