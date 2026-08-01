import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Cpu, Loader2, QrCode, RefreshCw, RotateCcwKey, TabletSmartphone, Unplug } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { branchApi } from "@/lib/adminApi";
import api from "@/lib/api";
import { deviceErrorMessage } from "@/lib/deviceApi";
import { useAuthStore } from "@/stores/auth.store";
import type { ApiResponse } from "@/types/api";
import type { BranchSettings } from "@/types/admin";
import type { DeviceProvisioning, DeviceRead, DeviceStatus, DeviceType } from "@/types/device";

const TYPE_LABEL: Record<DeviceType, string> = { counter: "Counter", kitchen: "Kitchen", pickup: "Pickup" };
const STATUS_LABEL: Record<DeviceStatus, string> = {
  pending_pairing: "รอจับคู่",
  pairing_expired: "PIN หมดอายุ",
  paired: "ใช้งานอยู่",
  revoked: "ยกเลิกแล้ว",
};

function dateTime(value: string | null): string {
  return value ? new Date(value).toLocaleString("th-TH") : "-";
}

function webPairingUrl(payload: string): string {
  try {
    const parsed = new URL(payload);
    return `${window.location.origin}/device/pair?${parsed.searchParams.toString()}`;
  } catch {
    return payload;
  }
}

function ProvisioningPanel({ provisioning }: { provisioning: DeviceProvisioning }): JSX.Element {
  const [qrUrl, setQrUrl] = useState("");
  useEffect(() => {
    let active = true;
    void QRCode.toDataURL(webPairingUrl(provisioning.pairing_qr_payload), { width: 280, margin: 2 }).then((url) => {
      if (active) setQrUrl(url);
    });
    return () => { active = false; };
  }, [provisioning]);

  return (
    <Card className="border-emerald-300 bg-emerald-50">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-emerald-950"><QrCode className="h-5 w-5" />ข้อมูลจับคู่ครั้งเดียว</CardTitle>
        <CardDescription>PIN จะแสดงในหน้านี้ครั้งเดียวและหมดอายุ {dateTime(provisioning.pairing_expires_at)}</CardDescription>
      </CardHeader>
      <CardContent className="grid items-center gap-6 md:grid-cols-[1fr_auto]">
        <div className="space-y-4">
          <div><p className="text-xs font-semibold uppercase tracking-wider text-emerald-800">Device Code</p><p className="mt-1 font-mono text-2xl font-black text-emerald-950">{provisioning.device.device_code}</p></div>
          <div><p className="text-xs font-semibold uppercase tracking-wider text-emerald-800">Pairing PIN</p><p className="mt-1 font-mono text-5xl font-black tracking-[0.25em] text-emerald-950">{provisioning.pairing_pin}</p></div>
          <Button type="button" variant="outline" onClick={() => void navigator.clipboard.writeText(webPairingUrl(provisioning.pairing_qr_payload))}>คัดลอกลิงก์จับคู่</Button>
        </div>
        {qrUrl ? <img src={qrUrl} alt="QR สำหรับจับคู่อุปกรณ์" className="mx-auto w-56 rounded-2xl border-8 border-white" /> : <Loader2 className="h-8 w-8 animate-spin" />}
      </CardContent>
    </Card>
  );
}

export default function DevicesPage(): JSX.Element {
  const queryClient = useQueryClient();
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const currentBranchId = useAuthStore((state) => state.branchId);
  const canManage = hasPermission("system.device.manage");
  const [name, setName] = useState("");
  const [deviceType, setDeviceType] = useState<DeviceType>("counter");
  const [branchId, setBranchId] = useState(currentBranchId ?? "");
  const [stationKey, setStationKey] = useState("");
  const [reason, setReason] = useState("ติดตั้งอุปกรณ์ประจำสาขา");
  const [provisioning, setProvisioning] = useState<DeviceProvisioning | null>(null);

  const branchesQuery = useQuery({
    queryKey: ["device-branches"],
    queryFn: async () => (await branchApi.list()).data.data.filter((branch) => branch.business_type === "restaurant" && branch.target_database === "restaurant"),
  });
  const branches = branchesQuery.data ?? [];
  useEffect(() => {
    if (!branchId && branches.length > 0) setBranchId(branches[0].id);
  }, [branchId, branches]);

  const settingsQuery = useQuery({
    queryKey: ["device-branch-settings", branchId],
    queryFn: async () => (await branchApi.getSettings(branchId)).data.data as BranchSettings,
    enabled: Boolean(branchId),
  });
  const branchName = useMemo(() => Object.fromEntries(branches.map((branch) => [branch.id, `${branch.code} · ${branch.name}`])), [branches]);
  const devicesQuery = useQuery({
    queryKey: ["system-devices"],
    queryFn: async () => (await api.get<ApiResponse<DeviceRead[]>>("/system/devices")).data.data,
  });

  const createMutation = useMutation({
    mutationFn: async () => (await api.post<ApiResponse<DeviceProvisioning>>("/system/devices", {
      name: name.trim(),
      device_type: deviceType,
      branch_id: branchId,
      station_key: deviceType === "kitchen" ? stationKey : null,
      reason: reason.trim(),
    })).data.data,
    onSuccess: (result) => {
      setProvisioning(result);
      setName("");
      void queryClient.invalidateQueries({ queryKey: ["system-devices"] });
    },
  });
  const rotateMutation = useMutation({
    mutationFn: async ({ id, reason: actionReason }: { id: string; reason: string }) => (await api.post<ApiResponse<DeviceProvisioning>>(`/system/devices/${id}/pairing-code`, { reason: actionReason })).data.data,
    onSuccess: (result) => {
      setProvisioning(result);
      void queryClient.invalidateQueries({ queryKey: ["system-devices"] });
    },
  });
  const revokeMutation = useMutation({
    mutationFn: async ({ id, reason: actionReason }: { id: string; reason: string }) => api.post(`/system/devices/${id}/revoke`, { reason: actionReason }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["system-devices"] }),
  });
  const actionError = createMutation.error ?? rotateMutation.error ?? revokeMutation.error;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><p className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-600">Phase 3</p><h1 className="text-3xl font-bold text-gray-950">อุปกรณ์ประจำร้าน</h1><p className="mt-1 text-gray-500">ลงทะเบียน จับคู่ เปลี่ยน PIN และยกเลิก Counter, Kitchen, Pickup ตาม Branch/Station</p></div>
        <Button type="button" variant="outline" onClick={() => void devicesQuery.refetch()}><RefreshCw className={`h-4 w-4 ${devicesQuery.isFetching ? "animate-spin" : ""}`} />รีเฟรช</Button>
      </div>

      {provisioning ? <ProvisioningPanel provisioning={provisioning} /> : null}

      {canManage ? (
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><TabletSmartphone className="h-5 w-5" />ลงทะเบียนเครื่องใหม่</CardTitle><CardDescription>Branch และ Kitchen Station จะถูกบันทึกฝั่ง server และเปลี่ยนจากหน้าเครื่องไม่ได้</CardDescription></CardHeader>
          <CardContent>
            <form className="grid gap-4 md:grid-cols-2 xl:grid-cols-5" onSubmit={(event) => { event.preventDefault(); setProvisioning(null); createMutation.mutate(); }}>
              <div className="space-y-2 xl:col-span-2"><Label htmlFor="device-name">ชื่อเครื่อง</Label><Input id="device-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="เช่น ครัวหลัก Tablet 1" required /></div>
              <div className="space-y-2"><Label htmlFor="device-type">ประเภท</Label><select id="device-type" value={deviceType} onChange={(event) => { setDeviceType(event.target.value as DeviceType); setStationKey(""); }} className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"><option value="counter">Counter</option><option value="kitchen">Kitchen</option><option value="pickup">Pickup</option></select></div>
              <div className="space-y-2"><Label htmlFor="device-branch">สาขา</Label><select id="device-branch" value={branchId} onChange={(event) => { setBranchId(event.target.value); setStationKey(""); }} className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" required>{branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.code} · {branch.name}</option>)}</select></div>
              {deviceType === "kitchen" ? <div className="space-y-2"><Label htmlFor="device-station">Kitchen Station</Label><select id="device-station" value={stationKey} onChange={(event) => setStationKey(event.target.value)} className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" required><option value="">เลือก Station</option>{(settingsQuery.data?.fb_kitchen_stations ?? []).map((station) => <option key={station} value={station}>{station}</option>)}</select></div> : <div className="space-y-2"><Label htmlFor="device-reason">เหตุผล</Label><Input id="device-reason" value={reason} onChange={(event) => setReason(event.target.value)} required /></div>}
              {deviceType === "kitchen" ? <div className="space-y-2 md:col-span-2 xl:col-span-4"><Label htmlFor="device-reason-kitchen">เหตุผล</Label><Input id="device-reason-kitchen" value={reason} onChange={(event) => setReason(event.target.value)} required /></div> : null}
              <div className="flex items-end"><Button className="w-full" disabled={createMutation.isPending || !branchId || (deviceType === "kitchen" && !stationKey)} type="submit">{createMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Cpu className="h-4 w-4" />}สร้าง Device และ PIN</Button></div>
            </form>
            {actionError ? <p className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{deviceErrorMessage(actionError)}</p> : null}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader><CardTitle>อุปกรณ์ทั้งหมดใน Scope</CardTitle><CardDescription>{devicesQuery.data?.length ?? 0} เครื่อง</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          {devicesQuery.isLoading ? <div className="flex justify-center py-12"><Loader2 className="h-7 w-7 animate-spin" /></div> : null}
          {(devicesQuery.data ?? []).map((device) => (
            <div key={device.id} className="flex flex-wrap items-center gap-4 rounded-xl border p-4">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-100"><TabletSmartphone className="h-5 w-5" /></div>
              <div className="min-w-48 flex-1"><div className="flex flex-wrap items-center gap-2"><p className="font-bold">{device.name}</p><Badge variant={device.status === "revoked" ? "destructive" : "secondary"}>{STATUS_LABEL[device.status]}</Badge><Badge variant="outline">{TYPE_LABEL[device.device_type]}</Badge></div><p className="mt-1 font-mono text-xs text-gray-500">{device.device_code} · {branchName[device.branch_id] ?? device.branch_id}{device.station_key ? ` · ${device.station_key}` : ""}</p></div>
              <div className="text-right text-xs text-gray-500"><p>จับคู่ {dateTime(device.paired_at)}</p><p>ล่าสุด {dateTime(device.last_seen_at)}</p></div>
              {canManage && device.status !== "revoked" ? <div className="flex gap-2"><Button type="button" size="sm" variant="outline" disabled={rotateMutation.isPending} onClick={() => { const actionReason = window.prompt("เหตุผลที่ออก Pairing PIN ใหม่", "ติดตั้งหรือจับคู่เครื่องใหม่"); if (actionReason?.trim()) rotateMutation.mutate({ id: device.id, reason: actionReason.trim() }); }}><RotateCcwKey className="h-4 w-4" />PIN ใหม่</Button><Button type="button" size="sm" variant="destructive" disabled={revokeMutation.isPending} onClick={() => { const actionReason = window.prompt("เหตุผลที่ยกเลิกอุปกรณ์ (มีผลทันที)"); if (actionReason?.trim() && window.confirm(`ยืนยันยกเลิก ${device.name}?`)) revokeMutation.mutate({ id: device.id, reason: actionReason.trim() }); }}><Unplug className="h-4 w-4" />ยกเลิก</Button></div> : null}
            </div>
          ))}
          {!devicesQuery.isLoading && (devicesQuery.data?.length ?? 0) === 0 ? <p className="py-12 text-center text-gray-500">ยังไม่มีอุปกรณ์ใน Scope นี้</p> : null}
        </CardContent>
      </Card>
    </div>
  );
}
