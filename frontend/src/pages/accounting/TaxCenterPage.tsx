import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { AlertTriangle, CheckCircle2, Download, FileCheck2, LockKeyhole, RefreshCw, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import { taxOperationsApi } from "@/lib/taxOperationsApi";
import { useAuthStore } from "@/stores/auth.store";
import type { TaxExportType } from "@/types/taxOperations";

const exportOptions: { value: TaxExportType; label: string }[] = [
  { value: "vat_sales", label: "รายงานภาษีขาย" },
  { value: "vat_purchases", label: "รายงานภาษีซื้อ" },
  { value: "pp30_summary", label: "สรุป ภ.พ.30" },
  { value: "wht_pnd3", label: "ภ.ง.ด.3" },
  { value: "wht_pnd53", label: "ภ.ง.ด.53" },
  { value: "etax_manifest", label: "บัญชี e-Tax" },
  { value: "tax_archive", label: "ชุดหลักฐานปิดงวด" },
];

function money(value: string | number): string {
  return new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(Number(value));
}

function errorMessage(error: unknown): string {
  if (!axios.isAxiosError(error)) return "กรุณาลองใหม่อีกครั้ง";
  const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail;
  return typeof detail === "string" ? detail : error.message;
}

export default function TaxCenterPage(): JSX.Element {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [exportType, setExportType] = useState<TaxExportType>("vat_sales");
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const canManage = hasPermission("accounting.tax.manage") || hasPermission("system.company.edit");
  const queryKey = useMemo(() => ["tax-operations", year, month], [year, month]);
  const dashboardQuery = useQuery({
    queryKey,
    queryFn: async () => (await taxOperationsApi.dashboard(year, month)).data.data,
  });
  const dashboard = dashboardQuery.data;

  async function refresh(): Promise<void> {
    await queryClient.invalidateQueries({ queryKey });
  }

  function useOperationMutation<T>(run: () => Promise<T>, success: string) {
    return useMutation({
      mutationFn: run,
      onSuccess: async () => { await refresh(); toast({ title: success }); },
      onError: (error) => toast({ title: "ดำเนินการไม่สำเร็จ", description: errorMessage(error), variant: "destructive" }),
    });
  }

  // Hooks use fixed call order; each mutation only receives current period values when invoked.
  const syncMutation = useOperationMutation(() => taxOperationsApi.syncLegacy(year, month), "นำข้อมูลขายและซื้อเข้าบัญชีภาษีแล้ว");
  const reconcileMutation = useOperationMutation(() => taxOperationsApi.reconcile(year, month), "กระทบยอดและตรวจความพร้อมแล้ว");
  const reviewMutation = useOperationMutation(() => taxOperationsApi.changePeriod("review", year, month), "ส่งงวดให้ตรวจสอบแล้ว");
  const closeMutation = useOperationMutation(() => taxOperationsApi.changePeriod("close", year, month), "ปิดงวดภาษีแล้ว");
  const reopenMutation = useOperationMutation(() => taxOperationsApi.changePeriod("reopen", year, month, null, window.prompt("เหตุผลการเปิดงวดใหม่") || ""), "เปิดงวดภาษีใหม่แล้ว");
  const exportMutation = useOperationMutation(() => taxOperationsApi.createExport(year, month, exportType), "สร้างไฟล์ภาษีแล้ว");
  const issueMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "resolved" | "ignored" }) => taxOperationsApi.resolveIssue(id, status, status === "resolved" ? "ตรวจสอบและแก้ไขแล้ว" : "รับทราบและยกเว้นรายการนี้"),
    onSuccess: refresh,
    onError: (error) => toast({ title: "บันทึกไม่สำเร็จ", description: errorMessage(error), variant: "destructive" }),
  });

  async function download(id: string, filename: string): Promise<void> {
    try {
      const response = await taxOperationsApi.download(id);
      const url = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url);
    } catch (error) {
      toast({ title: "ดาวน์โหลดไม่สำเร็จ", description: errorMessage(error), variant: "destructive" });
    }
  }

  if (dashboardQuery.isLoading) return <div className="rounded-xl border bg-white p-8 text-center text-gray-500">กำลังโหลดศูนย์ภาษี...</div>;
  if (!dashboard) return <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-red-700">โหลดข้อมูลไม่สำเร็จ <Button variant="outline" className="ml-3" onClick={() => void dashboardQuery.refetch()}>ลองอีกครั้ง</Button></div>;

  const isBusy = syncMutation.isPending || reconcileMutation.isPending || reviewMutation.isPending || closeMutation.isPending || reopenMutation.isPending;
  return (
    <div className="space-y-6">
      <PageHeader title="ศูนย์ภาษี" subtitle="รวมภาษีขาย ภาษีซื้อ หัก ณ ที่จ่าย e‑Tax การปิดงวด และชุดข้อมูลสำหรับผู้ทำบัญชี" />
      <div className="flex flex-wrap items-end gap-3 rounded-xl border bg-white p-4">
        <label className="space-y-1 text-sm"><span className="text-gray-600">ปี</span><Input className="w-28" type="number" value={year} onChange={(event) => setYear(Number(event.target.value))} /></label>
        <label className="space-y-1 text-sm"><span className="text-gray-600">เดือน</span><select className="h-10 rounded-md border bg-white px-3" value={month} onChange={(event) => setMonth(Number(event.target.value))}>{Array.from({ length: 12 }, (_, index) => <option key={index + 1} value={index + 1}>{index + 1}</option>)}</select></label>
        <Badge variant={dashboard.period.status === "closed" ? "success" : "secondary"}>สถานะงวด: {dashboard.period.status}</Badge>
        {canManage ? <><Button variant="outline" disabled={isBusy || dashboard.period.status === "closed"} onClick={() => syncMutation.mutate()}><RefreshCw className="mr-2 h-4 w-4" />ดึงข้อมูลล่าสุด</Button><Button variant="outline" disabled={isBusy} onClick={() => reconcileMutation.mutate()}><FileCheck2 className="mr-2 h-4 w-4" />ตรวจความพร้อม</Button></> : null}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Summary title="ภาษีขาย" value={money(dashboard.summary.output_tax)} note={`ฐาน ${money(dashboard.summary.output_base)}`} />
        <Summary title="ภาษีซื้อใช้สิทธิ์" value={money(dashboard.summary.input_tax)} note={`ฐาน ${money(dashboard.summary.input_base)}`} />
        <Summary title="ภาษีสุทธิ" value={money(dashboard.summary.net_tax)} note="ภาษีขาย − ภาษีซื้อ" />
        <Summary title="หัก ณ ที่จ่าย" value={money(dashboard.summary.wht_amount)} note="ใบรับรองในงวด" />
      </div>

      <div className={`rounded-xl border p-4 ${dashboard.readiness.ready_to_close && dashboard.readiness.configured ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex gap-3">{dashboard.readiness.ready_to_close && dashboard.readiness.configured ? <CheckCircle2 className="h-6 w-6 text-emerald-600" /> : <AlertTriangle className="h-6 w-6 text-amber-600" />}<div><p className="font-semibold">{dashboard.readiness.ready_to_close && dashboard.readiness.configured ? "งวดพร้อมปิด" : "งวดยังต้องตรวจสอบ"}</p><p className="text-sm text-gray-600">ประเด็นสำคัญ {dashboard.readiness.open_blockers} · คำเตือน {dashboard.readiness.open_warnings} · รอกระทบยอด {dashboard.readiness.pending_reconciliation} · ตั้งค่าภาษี {dashboard.readiness.configured ? "ครบ" : "ยังไม่ครบ"}</p></div></div>
          {canManage ? <div className="flex gap-2">{dashboard.period.status === "open" ? <Button onClick={() => reviewMutation.mutate()}>ส่งตรวจงวด</Button> : null}{dashboard.period.status === "review" ? <Button disabled={!dashboard.readiness.ready_to_close} onClick={() => closeMutation.mutate()}><LockKeyhole className="mr-2 h-4 w-4" />ปิดงวด</Button> : null}{dashboard.period.status === "closed" ? <Button variant="outline" onClick={() => reopenMutation.mutate()}>เปิดงวดใหม่</Button> : null}</div> : null}
        </div>
      </div>

      <Tabs defaultValue="ledger" className="space-y-4">
        <TabsList className="flex h-auto flex-wrap"><TabsTrigger value="ledger">บัญชีภาษี ({dashboard.ledger.length})</TabsTrigger><TabsTrigger value="issues">ตรวจสอบ ({dashboard.issues.filter((item) => item.status === "open").length})</TabsTrigger><TabsTrigger value="wht">หัก ณ ที่จ่าย ({dashboard.wht.length})</TabsTrigger><TabsTrigger value="exports">ส่งออก</TabsTrigger><TabsTrigger value="audit">หลักฐานปิดงวด</TabsTrigger></TabsList>
        <TabsContent value="ledger"><Card><CardHeader><CardTitle>รายการภาษีขายและภาษีซื้อ</CardTitle></CardHeader><CardContent><Table><TableHeader><TableRow><TableHead>วันที่/เอกสาร</TableHead><TableHead>ระบบ</TableHead><TableHead>ประเภท</TableHead><TableHead>คู่ค้า</TableHead><TableHead className="text-right">ฐาน</TableHead><TableHead className="text-right">VAT</TableHead><TableHead>กระทบยอด</TableHead></TableRow></TableHeader><TableBody>{dashboard.ledger.map((row) => <TableRow key={row.id}><TableCell><div>{row.document_date}</div><div className="text-xs text-gray-500">{row.document_number}</div></TableCell><TableCell>{row.source_module}</TableCell><TableCell><Badge variant="secondary">{row.tax_direction === "output" ? "ขาย" : "ซื้อ"}</Badge></TableCell><TableCell>{row.counterparty_name || "ลูกค้าทั่วไป"}</TableCell><TableCell className="text-right">{money(row.base_amount)}</TableCell><TableCell className="text-right">{money(row.tax_amount)}</TableCell><TableCell>{row.reconciliation_status}</TableCell></TableRow>)}</TableBody></Table>{dashboard.ledger.length === 0 ? <Empty text="ยังไม่มีรายการ กดดึงข้อมูลล่าสุดเพื่อเริ่มต้น" /> : null}</CardContent></Card></TabsContent>
        <TabsContent value="issues"><Card><CardHeader><CardTitle>ผลตรวจความพร้อม</CardTitle></CardHeader><CardContent className="space-y-3">{dashboard.issues.map((issue) => <div key={issue.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-4"><div><div className="flex gap-2"><Badge variant={issue.severity === "warning" ? "secondary" : "destructive"}>{issue.severity}</Badge><Badge variant="outline">{issue.status}</Badge></div><p className="mt-2 font-medium">{issue.message}</p><p className="text-xs text-gray-500">{issue.issue_code}</p></div>{canManage && issue.status === "open" && issue.severity === "warning" ? <div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => issueMutation.mutate({ id: issue.id, status: "ignored" })}>รับทราบ</Button><Button size="sm" onClick={() => issueMutation.mutate({ id: issue.id, status: "resolved" })}>ตรวจแล้ว</Button></div> : null}</div>)}{dashboard.issues.length === 0 ? <Empty text="ยังไม่มีผลตรวจ กดตรวจความพร้อม" /> : null}</CardContent></Card></TabsContent>
        <TabsContent value="wht"><Card><CardHeader><CardTitle>ทะเบียนหัก ณ ที่จ่าย</CardTitle></CardHeader><CardContent><Table><TableHeader><TableRow><TableHead>วันที่/เลขที่</TableHead><TableHead>ผู้ถูกหัก</TableHead><TableHead>ประเภท</TableHead><TableHead className="text-right">ฐาน</TableHead><TableHead className="text-right">ภาษี</TableHead></TableRow></TableHeader><TableBody>{dashboard.wht.map((row) => <TableRow key={row.id}><TableCell>{row.issue_date}<div className="text-xs text-gray-500">{row.certificate_number}</div></TableCell><TableCell>{row.supplier_name}<div className="text-xs text-gray-500">{row.supplier_tax_id || "ไม่มีเลขภาษี"}</div></TableCell><TableCell>{row.tax_entity_type}</TableCell><TableCell className="text-right">{money(row.base_amount)}</TableCell><TableCell className="text-right">{money(row.wht_amount)}</TableCell></TableRow>)}</TableBody></Table>{dashboard.wht.length === 0 ? <Empty text="ไม่มีใบรับรองในงวดนี้" /> : null}</CardContent></Card></TabsContent>
        <TabsContent value="exports"><Card><CardHeader><CardTitle>ชุดข้อมูลสำหรับผู้ทำบัญชี</CardTitle></CardHeader><CardContent className="space-y-4"><div className="flex flex-wrap gap-2"><select className="h-10 rounded-md border bg-white px-3" value={exportType} onChange={(event) => setExportType(event.target.value as TaxExportType)}>{exportOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select>{canManage ? <Button disabled={exportMutation.isPending} onClick={() => exportMutation.mutate()}>สร้างไฟล์</Button> : null}</div><div className="space-y-2">{dashboard.exports.map((row) => <div key={row.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3"><div><p className="font-medium">{row.filename}</p><p className="text-xs text-gray-500">{row.row_count} รายการ · SHA256 {row.content_sha256.slice(0, 16)}…</p></div><Button size="sm" variant="outline" onClick={() => void download(row.id, row.filename)}><Download className="mr-2 h-4 w-4" />ดาวน์โหลด</Button></div>)}</div></CardContent></Card></TabsContent>
        <TabsContent value="audit"><Card><CardHeader><CardTitle>หลักฐานและความสมบูรณ์ของงวด</CardTitle></CardHeader><CardContent className="space-y-4"><div className="flex gap-3 rounded-lg border p-4"><ShieldCheck className="h-6 w-6 text-blue-600" /><div><p className="font-medium">ลายนิ้วมือบัญชีภาษี</p><p className="break-all text-sm text-gray-500">{dashboard.period.ledger_sha256 || "จะสร้างเมื่อส่งตรวจหรือปิดงวด"}</p></div></div><p className="text-sm text-gray-600">ระบบเก็บผู้ทำรายการ เวลาทำรายการ เหตุผลการเปิดงวดใหม่ และ SHA‑256 ของชุดข้อมูลเพื่อใช้ตรวจสอบย้อนหลัง ชุดส่งออกเป็นข้อมูลเตรียมยื่น ไม่ใช่การส่งแบบให้กรมสรรพากรโดยอัตโนมัติ</p></CardContent></Card></TabsContent>
      </Tabs>
    </div>
  );
}

function Summary({ title, value, note }: { title: string; value: string; note: string }): JSX.Element { return <Card><CardContent className="pt-6"><p className="text-sm text-gray-500">{title}</p><p className="mt-1 text-2xl font-semibold">{value}</p><p className="mt-1 text-xs text-gray-500">{note}</p></CardContent></Card>; }
function Empty({ text }: { text: string }): JSX.Element { return <div className="py-10 text-center text-sm text-gray-500">{text}</div>; }
