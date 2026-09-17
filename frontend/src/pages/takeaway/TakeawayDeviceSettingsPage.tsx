import { useMutation, useQuery } from "@tanstack/react-query";
import { Bluetooth, CheckCircle2, Download, Loader2, Printer, RefreshCw, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useToast } from "@/components/ui/use-toast";
import { loadTakeawayRelease } from "@/lib/takeawayAppUpdate";
import {
  isNativeTakeawayPrinterAvailable,
  pairedTakeawayPrinters,
  printTakeawayRaw,
  saveTakeawayPrinter,
  savedTakeawayPrinter,
  type TakeawayPrinterDevice,
} from "@/lib/takeawayPrinter";

export default function TakeawayDeviceSettingsPage(): JSX.Element {
  const { toast } = useToast();
  const [devices, setDevices] = useState<TakeawayPrinterDevice[]>([]);
  const [selected, setSelected] = useState<TakeawayPrinterDevice | null>(() => savedTakeawayPrinter());
  const scanMutation = useMutation({
    mutationFn: pairedTakeawayPrinters,
    onSuccess: setDevices,
    onError: (error) => toast({ title: "อ่านเครื่องพิมพ์ไม่สำเร็จ", description: error instanceof Error ? error.message : "ตรวจ Bluetooth", variant: "destructive" }),
  });
  const testMutation = useMutation({
    mutationFn: async () => {
      if (!selected) throw new Error("กรุณาเลือกเครื่องพิมพ์");
      saveTakeawayPrinter(selected);
      await printTakeawayRaw(selected.address, "FOODCHAINSERVICE TAKEAWAY\nPRINTER TEST OK\n\n\n");
    },
    onSuccess: () => toast({ title: "ส่งใบพิมพ์ทดสอบแล้ว" }),
    onError: (error) => toast({ title: "ทดสอบพิมพ์ไม่สำเร็จ", description: error instanceof Error ? error.message : "ตรวจการจับคู่เครื่องพิมพ์", variant: "destructive" }),
  });
  const releaseQuery = useQuery({
    queryKey: ["takeaway", "signed-release"],
    queryFn: loadTakeawayRelease,
    retry: false,
  });
  const native = isNativeTakeawayPrinterAvailable();

  return <div className="space-y-5">
    <div><p className="text-xs font-bold uppercase tracking-[0.22em] text-emerald-700">device workspace</p><h1 className="mt-1 text-2xl font-black">อุปกรณ์ Takeaway</h1><p className="mt-1 text-sm text-slate-500">ตั้งค่าเครื่องพิมพ์ Bluetooth และตรวจเวอร์ชันแอปที่ลงลายเซ็น</p></div>
    <div className="grid gap-4 xl:grid-cols-2">
      <section className="rounded-2xl border bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between gap-3"><h2 className="flex items-center gap-2 font-black"><Bluetooth className="h-5 w-5 text-blue-600" /> เครื่องพิมพ์ Bluetooth</h2><button disabled={!native || scanMutation.isPending} onClick={() => scanMutation.mutate()} className="flex items-center gap-2 rounded-xl border px-3 py-2 text-sm font-bold disabled:opacity-40">{scanMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} อ่านอุปกรณ์ที่จับคู่</button></div>
        {!native ? <p className="mt-4 rounded-xl bg-amber-50 p-4 text-sm text-amber-900">การพิมพ์ Bluetooth ใช้ได้ในแอป Android เท่านั้น บนเว็บจะใช้หน้าต่างพิมพ์ของเบราว์เซอร์</p> : null}
        <div className="mt-4 space-y-2">{devices.map((device) => <button key={device.address} onClick={() => { setSelected(device); saveTakeawayPrinter(device); }} className={`flex w-full items-center justify-between rounded-xl border p-4 text-left ${selected?.address === device.address ? "border-emerald-500 bg-emerald-50" : "border-slate-200"}`}><span><strong className="block">{device.name}</strong><span className="text-xs text-slate-500">{device.address}</span></span>{selected?.address === device.address ? <CheckCircle2 className="h-5 w-5 text-emerald-600" /> : null}</button>)}</div>
        {selected ? <div className="mt-4 rounded-xl bg-slate-50 p-4 text-sm"><p className="font-bold">เครื่องที่เลือก: {selected.name}</p><button disabled={!native || testMutation.isPending} onClick={() => testMutation.mutate()} className="mt-3 flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-2 font-bold text-white disabled:opacity-40"><Printer className="h-4 w-4" /> ทดสอบพิมพ์และตัดกระดาษ</button></div> : null}
      </section>
      <section className="rounded-2xl border bg-white p-5 shadow-sm">
        <h2 className="flex items-center gap-2 font-black"><ShieldCheck className="h-5 w-5 text-emerald-600" /> Signed app update</h2>
        {releaseQuery.isLoading ? <div className="mt-6 flex justify-center"><Loader2 className="h-6 w-6 animate-spin" /></div> : releaseQuery.data?.verified ? <div className="mt-4 space-y-3"><div className="rounded-xl bg-emerald-50 p-4 text-emerald-900"><p className="font-black">ลายเซ็น release ถูกต้อง</p><p className="mt-1 text-sm">เวอร์ชัน {releaseQuery.data.manifest.version_name} ({releaseQuery.data.manifest.version_code})</p><p className="mt-1 break-all text-xs">SHA-256: {releaseQuery.data.manifest.apk_sha256}</p></div><a href={releaseQuery.data.manifest.apk_url} target="_blank" rel="noreferrer" className="flex items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-3 font-black"><Download className="h-5 w-5" /> ดาวน์โหลด APK ที่ตรวจลายเซ็นแล้ว</a>{releaseQuery.data.manifest.rollback_version_code ? <p className="text-xs text-slate-500">Rollback version: {releaseQuery.data.manifest.rollback_version_code}</p> : null}</div> : <div className="mt-4 rounded-xl bg-amber-50 p-4 text-sm text-amber-900"><p className="font-black">ยังไม่มี release ที่ยืนยันได้</p><p className="mt-1">UAT/Production ต้องตั้ง public key และ manifest URL ก่อนแจก APK ระบบจะไม่เสนอไฟล์ที่ตรวจลายเซ็นไม่ผ่าน</p></div>}
      </section>
    </div>
  </div>;
}
