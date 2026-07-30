import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  History,
  Loader2,
  RefreshCw,
  ShieldAlert,
  Warehouse,
} from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { wapApi } from "@/lib/wapApi";

function qty(value: number): string {
  return value.toLocaleString("th-TH", { maximumFractionDigits: 4 });
}

function money(value: number): string {
  return value.toLocaleString("th-TH", {
    style: "currency",
    currency: "THB",
    maximumFractionDigits: 2,
  });
}

function dateTime(value: string | null): string {
  if (!value) return "-";
  return new Date(value).toLocaleString("th-TH");
}

function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail.message === "string") return detail.message;
  }
  return error instanceof Error ? error.message : "ไม่สามารถทำรายการได้";
}

function roleLabel(role: string | null): string {
  const labels: Record<string, string> = {
    central_raw: "CENTRAL-RAW",
    central_ready: "CENTRAL-READY",
    store_local: "STORE-STOCK",
    not_stocked: "ไม่ตัด stock",
  };
  return role ? labels[role] ?? role : "ยังไม่กำหนด";
}

export default function RestaurantStockCutoverPage(): JSX.Element {
  const { brandSlug } = useParams<{ brandSlug?: string }>();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [confirmation, setConfirmation] = useState("");
  const [note, setNote] = useState("");

  const previewQuery = useQuery({
    queryKey: ["stock-cutover-preview", brandSlug],
    queryFn: async () => {
      if (!brandSlug) throw new Error("ไม่พบแบรนด์");
      return (await wapApi.stockCutoverPreview(brandSlug)).data.data;
    },
    enabled: Boolean(brandSlug),
    staleTime: 0,
  });

  const runsQuery = useQuery({
    queryKey: ["stock-cutover-runs", brandSlug],
    queryFn: async () => {
      if (!brandSlug) throw new Error("ไม่พบแบรนด์");
      return (await wapApi.stockCutoverRuns(brandSlug)).data.data;
    },
    enabled: Boolean(brandSlug),
  });

  const executeMutation = useMutation({
    mutationFn: async () => {
      if (!brandSlug || !previewQuery.data) throw new Error("กรุณาโหลด preview ใหม่");
      return (
        await wapApi.executeStockCutover(brandSlug, {
          preview_token: previewQuery.data.preview_token,
          confirmation_text: confirmation,
          note: note.trim() || null,
        })
      ).data.data;
    },
    onSuccess: async (run) => {
      setConfirmation("");
      setNote("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["stock-cutover-preview", brandSlug] }),
        queryClient.invalidateQueries({ queryKey: ["stock-cutover-runs", brandSlug] }),
        queryClient.invalidateQueries({ queryKey: ["brand-stock-dashboard", brandSlug] }),
        queryClient.invalidateQueries({ queryKey: ["restaurant-central-stock"] }),
      ]);
      toast({
        title: "Cutover สำเร็จ",
        description: `ย้าย ${run.item_count} รายการ รวม ${qty(run.total_qty)} หน่วย และบันทึก movement แล้ว`,
      });
    },
    onError: (error) =>
      toast({ title: "Cutover ไม่สำเร็จ", description: errorMessage(error), variant: "destructive" }),
  });

  const preview = previewQuery.data;
  const canExecute = Boolean(
    preview?.is_ready &&
      confirmation === preview.required_confirmation &&
      !executeMutation.isPending,
  );

  if (previewQuery.isLoading) {
    return (
      <div className="flex min-h-[24rem] items-center justify-center text-slate-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        กำลังตรวจ stock และงานค้าง
      </div>
    );
  }

  if (previewQuery.isError || !preview) {
    return (
      <div className="mx-auto max-w-5xl rounded-lg border border-rose-200 bg-rose-50 p-6 text-center text-rose-700">
        โหลด cutover preview ไม่สำเร็จ: {errorMessage(previewQuery.error)}
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 pb-10">
      <header className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-bold uppercase tracking-wide text-slate-500">{preview.brand_name}</p>
            <h1 className="text-xl font-black text-slate-950">Stock Separation Cutover</h1>
            <p className="mt-1 text-sm text-slate-600">
              Preview นี้อ่านอย่างเดียว จนกว่าจะกดยืนยันจึงย้ายสินค้าพร้อมส่งจาก RAW ไป READY ผ่าน stock movement
            </p>
          </div>
          <Button variant="outline" onClick={() => void previewQuery.refetch()} disabled={previewQuery.isFetching}>
            <RefreshCw className={`mr-2 h-4 w-4 ${previewQuery.isFetching ? "animate-spin" : ""}`} />
            ตรวจใหม่
          </Button>
        </div>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-bold uppercase text-slate-500">ต้นทาง</p>
          <p className="mt-2 font-black text-slate-950">{preview.raw_location?.name ?? "ยังไม่ตั้ง RAW"}</p>
          <p className="text-xs text-slate-500">{preview.raw_location?.code ?? "-"}</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-bold uppercase text-slate-500">ปลายทาง</p>
          <p className="mt-2 font-black text-slate-950">{preview.ready_location?.name ?? "ยังไม่ตั้ง READY"}</p>
          <p className="text-xs text-slate-500">{preview.ready_location?.code ?? "-"}</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-bold uppercase text-slate-500">รายการที่จะย้าย</p>
          <p className="mt-2 text-2xl font-black text-blue-700">{preview.candidate_count}</p>
          <p className="text-xs text-slate-500">{qty(preview.candidate_total_qty)} หน่วย</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-bold uppercase text-slate-500">มูลค่าตามต้นทุน</p>
          <p className="mt-2 text-xl font-black text-slate-950">{money(preview.candidate_total_value)}</p>
        </div>
      </section>

      <section className={`rounded-lg border p-4 ${preview.is_ready ? "border-emerald-200 bg-emerald-50" : "border-rose-200 bg-rose-50"}`}>
        <div className="flex items-start gap-3">
          {preview.is_ready ? (
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-700" />
          ) : (
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-rose-700" />
          )}
          <div className="min-w-0">
            <h2 className={`font-black ${preview.is_ready ? "text-emerald-900" : "text-rose-900"}`}>
              {preview.is_ready ? "พร้อมสำหรับ cutover" : `ยังห้าม cutover — ${preview.blockers.length} blocker`}
            </h2>
            {preview.blockers.length > 0 ? (
              <ul className="mt-2 space-y-1 text-sm text-rose-800">
                {preview.blockers.map((item, index) => (
                  <li key={`${item.code}-${index}`}>• {item.message} <span className="text-xs text-rose-600">({item.code})</span></li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-sm text-emerald-800">ไม่พบใบสั่ง ผลิต Transfer หรือข้อมูลคลังที่ขัดกับการย้าย</p>
            )}
          </div>
        </div>
      </section>

      {preview.warnings.length > 0 ? (
        <section className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <h2 className="flex items-center font-black text-amber-900">
            <AlertTriangle className="mr-2 h-5 w-5" /> คำเตือน
          </h2>
          <ul className="mt-2 space-y-1 text-sm text-amber-800">
            {preview.warnings.map((item, index) => <li key={`${item.code}-${index}`}>• {item.message}</li>)}
          </ul>
        </section>
      ) : null}

      <section className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <div className="border-b border-slate-200 p-4">
          <h2 className="font-black text-slate-950">คลังสาขาที่ตรวจพบ</h2>
          <p className="text-sm text-slate-500">STORE-STOCK ต้องแยกจากคลังกลางและผูกกับสาขาที่ถูกต้อง</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr><th className="px-4 py-3">สาขา</th><th className="px-4 py-3">ประเภท</th><th className="px-4 py-3">Location</th><th className="px-4 py-3">ผลตรวจ</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {preview.store_locations.map((item) => (
                <tr key={item.branch_id}>
                  <td className="px-4 py-3 font-bold text-slate-950">{item.branch_name} <span className="font-normal text-slate-500">({item.branch_code})</span></td>
                  <td className="px-4 py-3 text-slate-600">{item.branch_type}</td>
                  <td className="px-4 py-3 text-slate-600">{item.store_location_name ?? "ยังไม่ตั้ง"} {item.store_location_code ? `(${item.store_location_code})` : ""}</td>
                  <td className={`px-4 py-3 font-bold ${item.is_valid ? "text-emerald-700" : "text-rose-700"}`}>{item.is_valid ? "ผ่าน" : "ต้องแก้"}</td>
                </tr>
              ))}
              {preview.store_locations.length === 0 ? <tr><td colSpan={4} className="px-4 py-8 text-center text-slate-500">ยังไม่มีสาขาในแบรนด์</td></tr> : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <div className="border-b border-slate-200 p-4">
          <h2 className="font-black text-slate-950">รายการ READY ที่จะย้าย</h2>
          <p className="text-sm text-slate-500">จำนวนจริง ณ preview; ระบบจะตรวจ token และล็อกยอดซ้ำก่อน execute</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr><th className="px-4 py-3">สินค้า</th><th className="px-4 py-3 text-right">RAW ก่อนย้าย</th><th className="px-4 py-3 text-right">READY เดิม</th><th className="px-4 py-3 text-right">ต้นทุน</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {preview.transfer_candidates.map((item) => (
                <tr key={`${item.product_id}-${item.variant_id ?? "base"}`}>
                  <td className="px-4 py-3"><p className="font-bold text-slate-950">{item.product_name}</p><p className="text-xs text-slate-500">{item.sku} · {item.unit ?? "หน่วย"}</p></td>
                  <td className="px-4 py-3 text-right font-black text-blue-700">{qty(item.qty)}</td>
                  <td className="px-4 py-3 text-right text-slate-700">{qty(item.destination_qty_before)}</td>
                  <td className="px-4 py-3 text-right text-slate-700">{money(item.qty * item.cost_per_unit)}</td>
                </tr>
              ))}
              {preview.transfer_candidates.length === 0 ? <tr><td colSpan={4} className="px-4 py-8 text-center text-slate-500">ไม่มี READY ค้างอยู่ใน RAW</td></tr> : null}
            </tbody>
          </table>
        </div>
      </section>

      <details className="rounded-lg border border-slate-200 bg-white">
        <summary className="cursor-pointer p-4 font-black text-slate-950">Product audit ({preview.product_audit.length})</summary>
        <div className="overflow-x-auto border-t border-slate-200">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500"><tr><th className="px-4 py-3">สินค้า</th><th className="px-4 py-3">Role</th><th className="px-4 py-3">ใช้ในระบบ</th><th className="px-4 py-3">Balances</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {preview.product_audit.map((product) => (
                <tr key={product.product_id}>
                  <td className="px-4 py-3"><p className="font-bold">{product.product_name}</p><p className="text-xs text-slate-500">{product.sku}</p></td>
                  <td className="px-4 py-3 font-semibold">{roleLabel(product.inventory_role)}</td>
                  <td className="px-4 py-3 text-xs text-slate-600">{[product.is_production_output && "ผลผลิต", product.is_production_ingredient && "วัตถุดิบผลิต", product.is_menu_ingredient && "สูตรขาย"].filter(Boolean).join(", ") || "ยอด stock"}</td>
                  <td className="px-4 py-3 text-xs text-slate-600">{product.balances.map((balance) => `${balance.location_code ?? balance.location_name}: ${qty(balance.qty_on_hand)}`).join(" · ") || "0"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      <section className="rounded-lg border-2 border-rose-300 bg-white p-4">
        <div className="flex items-start gap-3">
          <Warehouse className="mt-0.5 h-5 w-5 shrink-0 text-rose-700" />
          <div>
            <h2 className="font-black text-rose-900">ยืนยันการย้ายยอดจริง</h2>
            <p className="mt-1 text-sm text-slate-600">ทำหลัง backup, หยุดรับออเดอร์/ผลิต/Transfer และตรวจนับกายภาพแล้วเท่านั้น การย้ายจะสร้าง transfer_out + transfer_in ที่ตรวจสอบย้อนหลังได้</p>
          </div>
        </div>
        <div className="mt-4 grid gap-3">
          <div>
            <label className="mb-1 block text-sm font-bold text-slate-700">พิมพ์ <code className="rounded bg-slate-100 px-1.5 py-0.5">{preview.required_confirmation}</code></label>
            <Input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} placeholder={preview.required_confirmation} disabled={!preview.is_ready || Boolean(preview.completed_run)} />
          </div>
          <div>
            <label className="mb-1 block text-sm font-bold text-slate-700">หมายเหตุ cutover</label>
            <textarea className="min-h-20 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={note} onChange={(event) => setNote(event.target.value)} placeholder="ผู้ตรวจนับ / เลขที่เอกสาร backup / หมายเหตุ" disabled={!preview.is_ready || Boolean(preview.completed_run)} />
          </div>
          <Button variant="destructive" disabled={!canExecute} onClick={() => executeMutation.mutate()}>
            {executeMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ArrowRight className="mr-2 h-4 w-4" />}
            ยืนยันย้าย RAW → READY
          </Button>
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-200 p-4">
          <h2 className="flex items-center font-black text-slate-950"><History className="mr-2 h-5 w-5" /> ประวัติ cutover</h2>
          <Button asChild variant="outline" size="sm"><Link to={`/central/${brandSlug}/reports`}>ดู Stock Dashboard</Link></Button>
        </div>
        {runsQuery.isLoading ? <div className="p-6 text-center text-slate-500">กำลังโหลดประวัติ</div> : (
          <div className="divide-y divide-slate-100">
            {(runsQuery.data ?? []).map((run) => (
              <div key={run.id} className="flex flex-col gap-1 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div><p className="font-bold text-slate-950">{run.status === "completed" ? "สำเร็จ" : run.status} · {run.item_count} รายการ</p><p className="text-xs text-slate-500">{dateTime(run.executed_at ?? run.created_at)} · Run {run.id.slice(0, 8)}</p></div>
                <p className="font-black text-blue-700">{qty(run.total_qty)} หน่วย</p>
              </div>
            ))}
            {(runsQuery.data ?? []).length === 0 ? <div className="p-6 text-center text-slate-500">ยังไม่มีประวัติ cutover</div> : null}
          </div>
        )}
      </section>
    </div>
  );
}
