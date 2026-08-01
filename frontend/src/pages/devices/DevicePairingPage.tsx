import { useMutation } from "@tanstack/react-query";
import { Cpu, Loader2, LockKeyhole, Unplug } from "lucide-react";
import { useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { deviceApi, deviceErrorMessage } from "@/lib/deviceApi";
import { useDeviceStore } from "@/stores/device.store";
import type { ApiResponse } from "@/types/api";
import type { DevicePairResponse, DeviceType } from "@/types/device";

const WORKSPACE_PATH: Record<DeviceType, string> = {
  counter: "/counter",
  kitchen: "/kitchen",
  pickup: "/pickup",
};

export default function DevicePairingPage(): JSX.Element {
  const location = useLocation();
  const navigate = useNavigate();
  const setSession = useDeviceStore((state) => state.setSession);
  const clearSession = useDeviceStore((state) => state.clearSession);
  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const [companyId, setCompanyId] = useState(params.get("company_id") ?? import.meta.env.VITE_COMPANY_ID ?? localStorage.getItem("last_company_id") ?? "");
  const [deviceCode, setDeviceCode] = useState(params.get("device_code") ?? "");
  const [pin, setPin] = useState(params.get("pin") ?? "");

  const pairMutation = useMutation({
    mutationFn: async () => {
      const response = await deviceApi.post<ApiResponse<DevicePairResponse>>("/device-auth/pair", {
        company_id: companyId.trim(),
        device_code: deviceCode.trim().toUpperCase(),
        pairing_pin: pin.trim(),
      });
      return response.data.data;
    },
    onSuccess: (session) => {
      setSession(session);
      localStorage.setItem("last_company_id", session.device.company_id);
      navigate(WORKSPACE_PATH[session.device.device_type], { replace: true });
    },
  });

  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-slate-950 px-4 py-10 text-white">
      <Card className="w-full max-w-lg border-slate-700 bg-slate-900 text-white shadow-2xl">
        <CardHeader className="items-center text-center">
          <div className="mb-3 flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-500 text-slate-950">
            <Cpu className="h-8 w-8" />
          </div>
          <CardTitle className="text-2xl text-white">จับคู่อุปกรณ์ประจำร้าน</CardTitle>
          <CardDescription className="text-slate-300">
            สแกน QR หรือกรอก Device Code และ PIN ที่ผู้จัดการสร้างให้
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-5"
            onSubmit={(event) => {
              event.preventDefault();
              pairMutation.mutate();
            }}
          >
            <div className="space-y-2">
              <Label className="text-slate-200" htmlFor="device-company">Company ID</Label>
              <Input id="device-company" className="h-12 text-base" value={companyId} onChange={(event) => setCompanyId(event.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label className="text-slate-200" htmlFor="device-code">Device Code</Label>
              <Input id="device-code" className="h-12 font-mono text-base uppercase" value={deviceCode} onChange={(event) => setDeviceCode(event.target.value)} placeholder="K-XXXXXXXXXX" required />
            </div>
            <div className="space-y-2">
              <Label className="text-slate-200" htmlFor="device-pin">Pairing PIN</Label>
              <Input id="device-pin" className="h-12 text-center font-mono text-2xl tracking-[0.4em]" inputMode="numeric" maxLength={6} pattern="[0-9]{6}" value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="000000" required />
            </div>
            {pairMutation.isError ? (
              <div className="rounded-xl border border-rose-500/60 bg-rose-950/60 px-4 py-3 text-sm text-rose-100">
                {deviceErrorMessage(pairMutation.error)}
              </div>
            ) : null}
            <Button className="h-12 w-full bg-emerald-500 text-slate-950 hover:bg-emerald-400" disabled={pairMutation.isPending || pin.length !== 6} type="submit">
              {pairMutation.isPending ? <Loader2 className="h-5 w-5 animate-spin" /> : <LockKeyhole className="h-5 w-5" />}
              จับคู่และเปิด Workspace
            </Button>
            <button
              type="button"
              className="mx-auto flex min-h-11 items-center gap-2 px-3 text-sm text-slate-300 hover:text-white"
              onClick={() => {
                clearSession();
                setDeviceCode("");
                setPin("");
              }}
            >
              <Unplug className="h-4 w-4" /> ล้างข้อมูลเครื่องเดิม
            </button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
