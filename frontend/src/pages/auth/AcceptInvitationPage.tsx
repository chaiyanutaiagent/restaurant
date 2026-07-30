import { useMutation } from "@tanstack/react-query";
import { Eye, EyeOff, KeyRound } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { invitationApi } from "@/lib/adminApi";

export default function AcceptInvitationPage(): JSX.Element {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [searchParams] = useSearchParams();
  const [showPassword, setShowPassword] = useState(false);
  const [form, setForm] = useState({
    company_id: searchParams.get("company_id") ?? "",
    invitation_id: searchParams.get("invitation_id") ?? "",
    otp_code: "",
    username: "",
    password: "",
    confirm_password: ""
  });

  const acceptMutation = useMutation({
    mutationFn: async () => {
      if (form.password !== form.confirm_password) {
        throw new Error("กรุณายืนยันรหัสผ่านให้ตรงกัน");
      }
      return invitationApi.accept(
        {
          invitation_id: form.invitation_id || undefined,
          otp_code: form.otp_code.toUpperCase(),
          username: form.username,
          password: form.password
        },
        form.company_id
      );
    },
    onSuccess: () => {
      toast({ title: "สร้างบัญชีสำเร็จ" });
      navigate("/login");
    },
    onError: (error: Error) => {
      toast({ title: "สร้างบัญชีไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-100 via-white to-emerald-50 px-4">
      <Card className="w-full max-w-md border-0 shadow-xl">
        <CardContent className="space-y-6 p-8">
          <div className="text-center">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
              <KeyRound className="h-7 w-7" />
            </div>
            <h1 className="text-2xl font-semibold text-gray-900">ยอมรับคำเชิญ</h1>
            <p className="mt-2 text-sm text-gray-500">สร้างบัญชีจากรหัส OTP ที่ได้รับจากผู้ดูแลระบบ</p>
          </div>

          <div className="grid gap-4">
            <Field label="Company ID">
              <Input
                value={form.company_id}
                onChange={(event) => setForm((prev) => ({ ...prev, company_id: event.target.value }))}
              />
            </Field>
            {form.invitation_id ? (
              <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
                คำเชิญ: {form.invitation_id}
              </p>
            ) : null}
            <Field label="รหัสคำเชิญ (OTP)">
              <Input
                maxLength={8}
                value={form.otp_code}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, otp_code: event.target.value.toUpperCase() }))
                }
              />
            </Field>
            <Field label="ชื่อผู้ใช้ *">
              <Input
                value={form.username}
                onChange={(event) => setForm((prev) => ({ ...prev, username: event.target.value }))}
              />
            </Field>
            <Field label="รหัสผ่าน *">
              <div className="relative">
                <Input
                  type={showPassword ? "text" : "password"}
                  value={form.password}
                  onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
                />
                <button
                  type="button"
                  className="absolute right-3 top-2.5 text-gray-500"
                  onClick={() => setShowPassword((value) => !value)}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </Field>
            <Field label="ยืนยันรหัสผ่าน *">
              <Input
                type={showPassword ? "text" : "password"}
                value={form.confirm_password}
                onChange={(event) => setForm((prev) => ({ ...prev, confirm_password: event.target.value }))}
              />
            </Field>
          </div>

          <Button className="w-full" onClick={() => acceptMutation.mutate()} disabled={acceptMutation.isPending}>
            สร้างบัญชี
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({
  label,
  children
}: {
  label: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <div className="grid gap-2">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
