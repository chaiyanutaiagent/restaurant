import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { takeawayCutterCapability, testTakeawayCutter, confirmTakeawayCutter } from "@/lib/takeawayPrinter";

export default function AutoCutterSettings({ address }: { address: string }): JSX.Element {
  const [testId, setTestId] = useState<string | null>(null);
  const status = useQuery({ queryKey: ["auto-cutter", address], queryFn: takeawayCutterCapability });
  const test = useMutation({ mutationFn: testTakeawayCutter, onSuccess: (id) => { setTestId(id); void status.refetch(); }, onError: () => { setTestId(null); void status.refetch(); } });
  const confirm = useMutation({ mutationFn: (full: boolean) => confirmTakeawayCutter(full, testId ?? undefined), onSuccess: () => { setTestId(null); void status.refetch(); } });
  return <section className="mt-4 space-y-3 rounded-xl border border-amber-300 bg-amber-50 p-4">
    <h3 className="font-black">Auto Cutter สำหรับชุด 2 ใบ</h3>
    <p>{status.data ? "ผู้ใช้ยืนยันแล้ว: ตัดขาดจริงหลังทั้งสองใบ" : "ยังไม่ยืนยัน / เครื่องอาจไม่รองรับตัดขาดจริง"}</p>
    <p className="text-sm">ชื่อ Bluetooth ไม่บอกความสามารถตัด ให้ทดสอบกับเครื่องจริงก่อน ระบบไม่ถือว่าการส่งข้อมูลสำเร็จคือกระดาษออกสำเร็จ</p>
    <button disabled={test.isPending || confirm.isPending} className="rounded-lg bg-slate-950 p-3 text-white" onClick={() => test.mutate()}>ทดสอบตัด 2 ใบ (ใช้กระดาษจริง)</button>
    {test.error || confirm.error ? <p role="alert">{String((test.error || confirm.error)?.message)}</p> : null}
    {testId ? <div className="space-y-2"><p>กระดาษแถบทดสอบ 2 ชิ้นตัดขาดเองหลังชิ้นที่ 1 และ 2 โดยไม่ต้องฉีกหรือไม่?</p><button disabled={confirm.isPending} className="mr-2 rounded-lg bg-emerald-700 p-3 text-white" onClick={() => confirm.mutate(true)}>ยืนยัน ตัดขาดครบ 2 ชิ้น</button><button disabled={confirm.isPending} className="rounded-lg border p-3" onClick={() => confirm.mutate(false)}>ไม่ตัด / ต้องฉีกเอง</button></div> : null}
    {status.data ? <button className="block text-sm underline" onClick={() => confirm.mutate(false)}>ยกเลิกการยืนยัน Auto Cutter</button> : null}
  </section>;
}
