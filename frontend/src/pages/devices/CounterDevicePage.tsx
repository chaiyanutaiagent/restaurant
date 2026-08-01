import { useQuery } from "@tanstack/react-query";
import { BadgeCheck, Loader2, LogIn, MonitorSmartphone, ShieldCheck, Unplug } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { deviceApi, deviceErrorMessage } from "@/lib/deviceApi";
import { useAuthStore } from "@/stores/auth.store";
import { useDeviceStore } from "@/stores/device.store";
import type { ApiResponse } from "@/types/api";
import type { DeviceWorkspaceBootstrap } from "@/types/device";

export default function CounterDevicePage(): JSX.Element {
  const user = useAuthStore((state) => state.user);
  const userBranchId = useAuthStore((state) => state.branchId);
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const clearDevice = useDeviceStore((state) => state.clearSession);
  const bootstrapQuery = useQuery({
    queryKey: ["device-workspace", "counter"],
    queryFn: async () => (await deviceApi.get<ApiResponse<DeviceWorkspaceBootstrap>>("/device-workspaces/counter/bootstrap")).data.data,
    retry: false,
  });
  const bootstrap = bootstrapQuery.data;
  const staffIdentifier = user?.employee_code?.trim() || user?.username || "-";
  const staffReady = Boolean(
    user
    && bootstrap
    && userBranchId === bootstrap.branch.id
    && hasPermission("fb.order.create"),
  );

  if (bootstrapQuery.isLoading) {
    return <div className="flex min-h-[100dvh] items-center justify-center bg-slate-950 text-white"><Loader2 className="h-10 w-10 animate-spin text-emerald-400" /></div>;
  }

  return (
    <div className="min-h-[100dvh] bg-slate-950 px-5 py-8 text-white sm:px-8">
      <div className="mx-auto flex min-h-[calc(100dvh-4rem)] max-w-5xl flex-col">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-5">
          <div className="flex items-center gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-500 text-slate-950"><MonitorSmartphone className="h-7 w-7" /></div>
            <div><p className="text-sm font-semibold uppercase tracking-[0.3em] text-emerald-400">Counter Workspace</p><h1 className="text-2xl font-black">{bootstrap?.branch.name ?? "Counter unavailable"}</h1></div>
          </div>
          {bootstrap ? <span className="rounded-full bg-slate-900 px-4 py-2 font-mono text-sm text-slate-300">{bootstrap.device.device_code}</span> : null}
        </header>

        {bootstrapQuery.isError || !bootstrap ? (
          <div className="my-auto rounded-3xl border border-rose-500 bg-rose-950/50 p-8 text-center"><p className="text-2xl font-black">เปิด Counter ไม่สำเร็จ</p><p className="mt-2 text-rose-200">{deviceErrorMessage(bootstrapQuery.error)}</p></div>
        ) : (
          <main className="my-auto grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
            <section className="rounded-[2rem] border border-emerald-500/40 bg-emerald-950/30 p-8 sm:p-10">
              <BadgeCheck className="h-14 w-14 text-emerald-400" />
              <h2 className="mt-6 text-4xl font-black">เครื่องพร้อมขาย</h2>
              <p className="mt-3 text-lg text-slate-300">อุปกรณ์นี้ถูกล็อกไว้กับ {bootstrap.branch.code} · {bootstrap.branch.name}</p>
              <div className="mt-8 flex items-center gap-3 rounded-2xl bg-slate-900/80 px-5 py-4"><ShieldCheck className="h-6 w-6 text-emerald-400" /><div><p className="font-bold">Device gate ผ่านแล้ว</p><p className="text-sm text-slate-400">ยังต้องลงชื่อพนักงาน เพื่อบันทึกผู้ขายและกะเงินสดให้ถูกต้อง</p></div></div>
            </section>
            <section className="flex flex-col justify-center rounded-[2rem] border border-slate-700 bg-slate-900 p-8">
              <p className="text-sm font-semibold uppercase tracking-[0.25em] text-slate-400">Staff session</p>
              <p className="mt-3 text-2xl font-black">{staffReady ? `พร้อมใช้งานโดย ${user?.display_name ?? user?.username}` : user ? "Branch ของพนักงานไม่ตรงกับเครื่อง" : "กรุณาลงชื่อพนักงาน"}</p>
              {staffReady ? <p className="mt-2 font-mono text-sm font-semibold text-emerald-300">Employee ID: {staffIdentifier}</p> : null}
              <p className="mt-2 text-sm text-slate-400">ยอดขายจะใช้สิทธิ์และ Branch จากพนักงาน และต้องตรงกับ Branch ที่จับคู่เครื่องนี้</p>
              {staffReady ? (
                <Button asChild className="mt-7 h-14 bg-emerald-500 text-lg font-black text-slate-950 hover:bg-emerald-400"><Link to="/counter/orders"><LogIn className="h-5 w-5" />เปิดหน้าขาย</Link></Button>
              ) : (
                <Button asChild className="mt-7 h-14 bg-white text-lg font-black text-slate-950 hover:bg-slate-200"><Link to="/login?next=/counter"><LogIn className="h-5 w-5" />ลงชื่อพนักงาน</Link></Button>
              )}
            </section>
          </main>
        )}
        <footer className="flex justify-center pt-5"><button type="button" onClick={() => { clearDevice(); window.location.href = "/device/pair"; }} className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-rose-300"><Unplug className="h-4 w-4" />ยกเลิกการจับคู่เครื่องนี้</button></footer>
      </div>
    </div>
  );
}
