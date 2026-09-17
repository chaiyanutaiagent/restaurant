import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ClipboardCheck, History, Loader2, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useToast } from "@/components/ui/use-toast";
import { takeawayApi, type TakeawayRecord } from "@/lib/takeawayApi";

function display(value: unknown): string {
  if (value === undefined || value === null || value === "") return "-";
  return String(value);
}

export default function TakeawayCutoverPage(): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [packageText, setPackageText] = useState('{\n  "manifest": {},\n  "mapping": {},\n  "records": []\n}');
  const [preview, setPreview] = useState<TakeawayRecord | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [evidence, setEvidence] = useState({ approval_reference: "", backup_reference: "", rollback_reference: "" });
  const history = useQuery({ queryKey: ["takeaway", "cutover-runs"], queryFn: async () => (await takeawayApi.cutoverRuns()).data.data });
  const previewMutation = useMutation({
    mutationFn: async () => takeawayApi.previewCutover(JSON.parse(packageText) as Record<string, unknown>),
    onSuccess: (response) => { setPreview(response.data.data); setConfirmed(false); toast({ title: response.data.data.ready ? "แพ็กเกจพร้อมเข้าสู่ approval gate" : "พบรายการที่ต้องแก้ก่อน", variant: response.data.data.ready ? "default" : "destructive" }); },
    onError: (error) => toast({ title: "ตรวจแพ็กเกจไม่สำเร็จ", description: error instanceof Error ? error.message : "JSON หรือสิทธิ์ไม่ถูกต้อง", variant: "destructive" }),
  });
  const executeMutation = useMutation({
    mutationFn: async () => {
      const bundle = JSON.parse(packageText) as Record<string, unknown>;
      return takeawayApi.executeCutover({
        ...bundle,
        preview_digest: preview?.preview_digest,
        execution_key: `takeaway-cutover-${crypto.randomUUID()}`,
        ...evidence,
        confirmation: "EXECUTE_APPROVED_TAKEAWAY_CUTOVER",
      });
    },
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["takeaway", "cutover-runs"] }); setConfirmed(false); toast({ title: "บันทึก cutover และ reconciliation แล้ว" }); },
    onError: (error) => toast({ title: "Cutover ไม่สำเร็จ", description: error instanceof Error ? error.message : "ตรวจ blocker และหลักฐานอนุมัติ", variant: "destructive" }),
  });
  const canExecute = preview?.ready === true && confirmed && Object.values(evidence).every((value) => value.trim().length >= 3);
  const blockers = Array.isArray(preview?.blockers) ? preview.blockers as TakeawayRecord[] : [];

  return <div className="space-y-5">
    <div><p className="text-xs font-black uppercase tracking-[0.22em] text-emerald-700">WP21 · migration control</p><h1 className="mt-1 text-2xl font-black">Takeaway Cutover</h1><p className="mt-1 text-sm text-slate-500">ตรวจลายเซ็น แฮช ยอดควบคุม และหลักฐาน rollback ก่อนนำเข้า โดยไม่มีคำสั่ง execute เป็นค่าเริ่มต้น</p></div>
    <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
      <section className="rounded-2xl bg-white p-5 shadow-sm"><label className="text-sm font-black">Signed bundle payload</label><textarea value={packageText} onChange={(event) => { setPackageText(event.target.value); setPreview(null); setConfirmed(false); }} className="mt-3 h-[430px] w-full rounded-xl bg-slate-950 p-4 font-mono text-xs text-slate-100" /><button disabled={previewMutation.isPending} onClick={() => previewMutation.mutate()} className="mt-3 flex items-center gap-2 rounded-xl bg-emerald-500 px-5 py-3 font-black disabled:opacity-50">{previewMutation.isPending ? <Loader2 className="h-5 w-5 animate-spin" /> : <ClipboardCheck className="h-5 w-5" />} Preview เท่านั้น</button></section>
      <section className="space-y-4">
        <div className={`rounded-2xl border p-5 ${preview?.ready ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>{preview?.ready ? <CheckCircle2 className="h-7 w-7 text-emerald-700" /> : <AlertTriangle className="h-7 w-7 text-amber-700" />}<h2 className="mt-3 font-black">{preview?.ready ? "พร้อมขออนุมัติ" : "ยังไม่พร้อม Execute"}</h2><p className="mt-2 break-all text-xs">Preview digest: {display(preview?.preview_digest)}</p><p className="mt-1 text-sm">ข้อมูล {display(preview?.total_records)} รายการ · Seal {display(preview?.seal_status)}</p>{blockers.length ? <ul className="mt-3 space-y-1 text-xs">{blockers.slice(0, 12).map((row, index) => <li key={`${row.code}-${index}`}>• {display(row.code)} — {display(row.path)}</li>)}</ul> : null}</div>
        <div className="rounded-2xl border bg-white p-5"><h2 className="flex items-center gap-2 font-black"><ShieldCheck className="h-5 w-5" /> Approval evidence</h2>{(["approval_reference", "backup_reference", "rollback_reference"] as const).map((key) => <label key={key} className="mt-3 block text-xs font-bold text-slate-600">{key}<input value={evidence[key]} onChange={(event) => setEvidence({ ...evidence, [key]: event.target.value })} className="mt-1 w-full rounded-xl border px-3 py-2 text-sm" /></label>)}<label className="mt-4 flex gap-3 rounded-xl bg-rose-50 p-3 text-sm text-rose-900"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /><span>ยืนยันว่า snapshot, owner approval, final backup และ rollback plan ได้รับอนุมัติจริงแล้ว</span></label><button disabled={!canExecute || executeMutation.isPending} onClick={() => executeMutation.mutate()} className="mt-4 w-full rounded-xl bg-rose-600 px-4 py-3 font-black text-white disabled:opacity-30">Execute approved cutover</button></div>
      </section>
    </div>
    <section className="rounded-2xl bg-white p-5 shadow-sm"><h2 className="flex items-center gap-2 font-black"><History className="h-5 w-5" /> ประวัติแบบ immutable</h2><div className="mt-3 space-y-2">{(history.data ?? []).map((run) => <div key={run.id} className="grid gap-2 rounded-xl border p-4 text-sm md:grid-cols-4"><strong>{display(run.status)}</strong><span>{display(run.source_snapshot)}</span><span className="truncate">{display(run.approval_reference)}</span><span>{display(run.executed_at)}</span></div>)}{history.data?.length === 0 ? <p className="text-sm text-slate-500">ยังไม่มี cutover run</p> : null}</div></section>
  </div>;
}
