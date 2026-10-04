import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { Building2, CheckCircle2, Landmark, Percent, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import { taxSettingsApi } from "@/lib/taxSettingsApi";
import type {
  BranchTaxProfilePayload,
  CompanyTaxProfilePayload,
  TaxCategory,
  TaxRateRuleCreatePayload,
  TaxSettings,
  VatType,
} from "@/types/taxSettings";

const today = (): string => new Date().toISOString().slice(0, 10);
const fieldClass = "h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm";
const textAreaClass = "min-h-24 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm";

const emptyCompany = (): CompanyTaxProfilePayload => ({
  legal_name: "",
  tax_id: null,
  vat_registered: false,
  vat_registration_date: null,
  registered_address: null,
  default_price_vat_type: "included",
  default_vat_rate: 7,
  vat_filing_mode: "separate",
  consolidated_filing_approved: false,
  effective_from: today(),
  reason: "กำหนดค่าภาษีบริษัท",
});

const emptyRate = (): TaxRateRuleCreatePayload => ({
  code: "",
  name: "",
  tax_category: "standard",
  rate: 7,
  price_vat_type: "included",
  effective_from: today(),
  effective_to: null,
  is_default: false,
  reason: "เพิ่มอัตราภาษี",
});

function errorMessage(error: unknown): string {
  if (!axios.isAxiosError(error)) return "กรุณาลองใหม่อีกครั้ง";
  const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      if (typeof item === "object" && item && "msg" in item) return String(item.msg);
      return String(item);
    }).join(", ");
  }
  return error.message;
}

function vatTypeLabel(value: VatType): string {
  return value === "included" ? "ราคารวม VAT" : value === "excluded" ? "ราคาไม่รวม VAT" : "ยกเว้น VAT";
}

function categoryLabel(value: TaxCategory): string {
  return value === "standard" ? "อัตรามาตรฐาน" : value === "zero" ? "อัตรา 0%" : "ยกเว้น VAT";
}

export default function TaxSettingsPage(): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [companyForm, setCompanyForm] = useState<CompanyTaxProfilePayload>(emptyCompany);
  const [branchForms, setBranchForms] = useState<Record<string, BranchTaxProfilePayload>>({});
  const [rateForm, setRateForm] = useState<TaxRateRuleCreatePayload>(emptyRate);

  const settingsQuery = useQuery({
    queryKey: ["tax-settings"],
    queryFn: async () => (await taxSettingsApi.get()).data.data,
  });

  const settings = settingsQuery.data;

  useEffect(() => {
    if (!settings) return;
    setCompanyForm({
      legal_name: settings.company.legal_name,
      tax_id: settings.company.tax_id,
      vat_registered: settings.company.vat_registered,
      vat_registration_date: settings.company.vat_registration_date,
      registered_address: settings.company.registered_address,
      default_price_vat_type: settings.company.default_price_vat_type,
      default_vat_rate: Number(settings.company.default_vat_rate),
      vat_filing_mode: settings.company.vat_filing_mode,
      consolidated_filing_approved: settings.company.consolidated_filing_approved,
      effective_from: today(),
      reason: settings.company.configured ? "ปรับปรุงค่าภาษีบริษัท" : "กำหนดค่าภาษีบริษัท",
    });
    setBranchForms(Object.fromEntries(settings.branches.map((branch) => [branch.branch_id, {
      tax_branch_code: branch.tax_branch_code ?? "",
      is_head_office: branch.is_head_office,
      legal_name: branch.legal_name,
      registered_address: branch.registered_address,
      vat_registration_date: branch.vat_registration_date,
      filing_enabled: branch.filing_enabled,
      effective_from: branch.effective_from ?? today(),
      effective_to: branch.effective_to,
      reason: branch.configured ? "ปรับปรุงข้อมูลภาษีสาขา" : "กำหนดข้อมูลภาษีสาขา",
    }])));
  }, [settings]);

  const configuredBranches = useMemo(
    () => settings?.branches.filter((branch) => branch.configured).length ?? 0,
    [settings],
  );

  async function refresh(): Promise<void> {
    await queryClient.invalidateQueries({ queryKey: ["tax-settings"] });
  }

  const companyMutation = useMutation({
    mutationFn: (payload: CompanyTaxProfilePayload) => taxSettingsApi.updateCompany(payload),
    onSuccess: async () => {
      await refresh();
      toast({ title: "บันทึกข้อมูลภาษีบริษัทแล้ว" });
    },
    onError: (error) => toast({ title: "บันทึกไม่สำเร็จ", description: errorMessage(error), variant: "destructive" }),
  });

  const branchMutation = useMutation({
    mutationFn: ({ branchId, payload }: { branchId: string; payload: BranchTaxProfilePayload }) =>
      taxSettingsApi.updateBranch(branchId, payload),
    onSuccess: async () => {
      await refresh();
      toast({ title: "บันทึกข้อมูลภาษีสาขาแล้ว" });
    },
    onError: (error) => toast({ title: "บันทึกไม่สำเร็จ", description: errorMessage(error), variant: "destructive" }),
  });

  const rateMutation = useMutation({
    mutationFn: (payload: TaxRateRuleCreatePayload) => taxSettingsApi.createRate(payload),
    onSuccess: async () => {
      setRateForm(emptyRate());
      await refresh();
      toast({ title: "เพิ่มอัตราภาษีแล้ว" });
    },
    onError: (error) => toast({ title: "เพิ่มอัตราไม่สำเร็จ", description: errorMessage(error), variant: "destructive" }),
  });

  const closeRateMutation = useMutation({
    mutationFn: ({ id, effectiveTo, reason }: { id: string; effectiveTo: string; reason: string }) =>
      taxSettingsApi.updateRate(id, { effective_to: effectiveTo, is_active: false, reason }),
    onSuccess: async () => {
      await refresh();
      toast({ title: "ปิดใช้งานอัตราภาษีแล้ว" });
    },
    onError: (error) => toast({ title: "ปิดใช้งานไม่สำเร็จ", description: errorMessage(error), variant: "destructive" }),
  });

  function updateBranch(branchId: string, patch: Partial<BranchTaxProfilePayload>): void {
    setBranchForms((current) => ({
      ...current,
      [branchId]: { ...current[branchId], ...patch },
    }));
  }

  function changeRateCategory(category: TaxCategory): void {
    setRateForm((current) => ({
      ...current,
      tax_category: category,
      rate: category === "standard" ? 7 : 0,
      price_vat_type: category === "exempt" ? "exempt" : current.price_vat_type === "exempt" ? "excluded" : current.price_vat_type,
    }));
  }

  if (settingsQuery.isLoading) {
    return <div className="rounded-xl border bg-white p-8 text-center text-gray-500">กำลังโหลดค่าภาษี...</div>;
  }

  if (!settings || settingsQuery.isError) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-red-700">
        โหลดค่าภาษีไม่สำเร็จ <Button variant="outline" className="ml-3" onClick={() => void settingsQuery.refetch()}>ลองอีกครั้ง</Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="ตั้งค่าภาษี"
        subtitle="ข้อมูลผู้เสียภาษี สาขาภาษี และอัตรา VAT กลางสำหรับ Restaurant, Retail และ Takeaway"
      />

      <div className="grid gap-4 md:grid-cols-3">
        <SummaryCard icon={Landmark} label="ข้อมูลบริษัท" value={settings.company.configured ? "ตั้งค่าแล้ว" : "รอตั้งค่า"} ready={settings.company.configured} />
        <SummaryCard icon={Building2} label="สาขาภาษี" value={`${configuredBranches}/${settings.branches.length} สาขา`} ready={configuredBranches === settings.branches.length && settings.branches.length > 0} />
        <SummaryCard icon={Percent} label="อัตราภาษี" value={`${settings.rates.filter((rate) => rate.is_active).length} อัตราที่ใช้งาน`} ready={settings.rates.some((rate) => rate.is_active && rate.is_default)} />
      </div>

      <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
        <div className="flex gap-3">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" />
          <p>ค่าชุดนี้เป็นแหล่งข้อมูลกลางของ ERP และถูกนำไปใช้บนเอกสารภาษีของทุก POS การแก้ไขทุกครั้งจะเก็บผู้แก้ เหตุผล และค่าก่อน–หลังไว้ตรวจสอบย้อนหลัง</p>
        </div>
      </div>

      <Tabs defaultValue="company" className="space-y-5">
        <TabsList className="flex h-auto flex-wrap gap-1">
          <TabsTrigger value="company">1. บริษัท</TabsTrigger>
          <TabsTrigger value="branches">2. สาขาภาษี</TabsTrigger>
          <TabsTrigger value="rates">3. อัตราภาษี</TabsTrigger>
        </TabsList>

        <TabsContent value="company">
          <form onSubmit={(event) => { event.preventDefault(); companyMutation.mutate(companyForm); }}>
            <Card>
              <CardHeader><CardTitle>ข้อมูลจดทะเบียนของบริษัท</CardTitle></CardHeader>
              <CardContent className="space-y-5">
                <div className="grid gap-4 md:grid-cols-2">
                  <Field label="ชื่อกิจการตาม ภ.พ.20 *"><Input required value={companyForm.legal_name} onChange={(event) => setCompanyForm((current) => ({ ...current, legal_name: event.target.value }))} /></Field>
                  <Field label="เลขประจำตัวผู้เสียภาษี 13 หลัก"><Input inputMode="numeric" maxLength={13} value={companyForm.tax_id ?? ""} onChange={(event) => setCompanyForm((current) => ({ ...current, tax_id: event.target.value || null }))} /></Field>
                  <Field label="วันที่จดทะเบียน VAT"><Input type="date" value={companyForm.vat_registration_date ?? ""} onChange={(event) => setCompanyForm((current) => ({ ...current, vat_registration_date: event.target.value || null }))} /></Field>
                  <Field label="วันที่เริ่มใช้อัตราเริ่มต้น *"><Input required type="date" value={companyForm.effective_from} onChange={(event) => setCompanyForm((current) => ({ ...current, effective_from: event.target.value }))} /></Field>
                </div>
                <label className="flex items-center gap-3 rounded-lg border p-3 text-sm font-medium"><input type="checkbox" checked={companyForm.vat_registered} onChange={(event) => setCompanyForm((current) => ({ ...current, vat_registered: event.target.checked }))} /> กิจการจดทะเบียนภาษีมูลค่าเพิ่ม</label>
                <Field label="ที่อยู่จดทะเบียน"><textarea className={textAreaClass} value={companyForm.registered_address ?? ""} onChange={(event) => setCompanyForm((current) => ({ ...current, registered_address: event.target.value || null }))} /></Field>
                <div className="grid gap-4 md:grid-cols-3">
                  <Field label="รูปแบบราคาสินค้า"><select className={fieldClass} value={companyForm.default_price_vat_type} onChange={(event) => { const value = event.target.value as VatType; setCompanyForm((current) => ({ ...current, default_price_vat_type: value, default_vat_rate: value === "exempt" ? 0 : current.default_vat_rate })); }}><VatTypeOptions /></select></Field>
                  <Field label="อัตรา VAT เริ่มต้น (%)"><Input type="number" min={0} max={100} step="0.01" value={companyForm.default_vat_rate} disabled={companyForm.default_price_vat_type === "exempt"} onChange={(event) => setCompanyForm((current) => ({ ...current, default_vat_rate: Number(event.target.value) }))} /></Field>
                  <Field label="รูปแบบการยื่น ภ.พ.30"><select className={fieldClass} value={companyForm.vat_filing_mode} onChange={(event) => setCompanyForm((current) => ({ ...current, vat_filing_mode: event.target.value as "separate" | "consolidated", consolidated_filing_approved: event.target.value === "consolidated" ? current.consolidated_filing_approved : false }))}><option value="separate">แยกยื่นรายสาขา</option><option value="consolidated">ยื่นรวมทั้งบริษัท</option></select></Field>
                </div>
                {companyForm.vat_filing_mode === "consolidated" ? <label className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm"><input type="checkbox" checked={companyForm.consolidated_filing_approved} onChange={(event) => setCompanyForm((current) => ({ ...current, consolidated_filing_approved: event.target.checked }))} /> ยืนยันว่าได้รับอนุมัติให้ยื่นรวมแล้ว</label> : null}
                <Field label="เหตุผลการบันทึก *"><Input required minLength={3} value={companyForm.reason} onChange={(event) => setCompanyForm((current) => ({ ...current, reason: event.target.value }))} /></Field>
                <Button type="submit" disabled={companyMutation.isPending}>{companyMutation.isPending ? "กำลังบันทึก..." : "บันทึกข้อมูลบริษัท"}</Button>
              </CardContent>
            </Card>
          </form>
        </TabsContent>

        <TabsContent value="branches" className="space-y-4">
          {!settings.company.configured ? <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">กรุณาบันทึกข้อมูลบริษัทก่อนตั้งค่าสาขาภาษี</div> : null}
          {settings.branches.map((branch) => {
            const form = branchForms[branch.branch_id];
            if (!form) return null;
            return (
              <form key={branch.branch_id} onSubmit={(event) => { event.preventDefault(); branchMutation.mutate({ branchId: branch.branch_id, payload: form }); }}>
                <Card>
                  <CardHeader><CardTitle className="flex flex-wrap items-center justify-between gap-2"><span>{branch.branch_name} <span className="text-sm font-normal text-gray-500">({branch.branch_code})</span></span><Badge variant={branch.configured ? "success" : "secondary"}>{branch.configured ? "ตั้งค่าแล้ว" : "รอตั้งค่า"}</Badge></CardTitle></CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid gap-4 md:grid-cols-3">
                      <Field label="รหัสสาขาภาษี 5 หลัก *"><Input required inputMode="numeric" maxLength={5} placeholder="00000" value={form.tax_branch_code} onChange={(event) => updateBranch(branch.branch_id, { tax_branch_code: event.target.value })} /></Field>
                      <Field label="วันที่เริ่มใช้ *"><Input required type="date" value={form.effective_from} onChange={(event) => updateBranch(branch.branch_id, { effective_from: event.target.value })} /></Field>
                      <Field label="วันที่สิ้นสุด"><Input type="date" value={form.effective_to ?? ""} onChange={(event) => updateBranch(branch.branch_id, { effective_to: event.target.value || null })} /></Field>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      <label className="flex items-center gap-3 rounded-lg border p-3 text-sm"><input type="checkbox" checked={form.is_head_office} onChange={(event) => updateBranch(branch.branch_id, { is_head_office: event.target.checked, tax_branch_code: event.target.checked ? "00000" : form.tax_branch_code === "00000" ? "" : form.tax_branch_code })} /> สำนักงานใหญ่ (ใช้รหัส 00000)</label>
                      <label className="flex items-center gap-3 rounded-lg border p-3 text-sm"><input type="checkbox" checked={form.filing_enabled} onChange={(event) => updateBranch(branch.branch_id, { filing_enabled: event.target.checked })} /> รวมสาขานี้ในการจัดทำรายงานภาษี</label>
                    </div>
                    <div className="grid gap-4 md:grid-cols-2">
                      <Field label="ชื่อกิจการบนเอกสาร (ถ้าต่างจากบริษัท)"><Input value={form.legal_name ?? ""} onChange={(event) => updateBranch(branch.branch_id, { legal_name: event.target.value || null })} /></Field>
                      <Field label="วันที่จดทะเบียน VAT"><Input type="date" value={form.vat_registration_date ?? ""} onChange={(event) => updateBranch(branch.branch_id, { vat_registration_date: event.target.value || null })} /></Field>
                    </div>
                    <Field label="ที่อยู่สาขาตาม ภ.พ.20"><textarea className={textAreaClass} value={form.registered_address ?? ""} onChange={(event) => updateBranch(branch.branch_id, { registered_address: event.target.value || null })} /></Field>
                    <Field label="เหตุผลการบันทึก *"><Input required minLength={3} value={form.reason} onChange={(event) => updateBranch(branch.branch_id, { reason: event.target.value })} /></Field>
                    <Button type="submit" disabled={!settings.company.configured || branchMutation.isPending}>บันทึก {branch.branch_name}</Button>
                  </CardContent>
                </Card>
              </form>
            );
          })}
          {settings.branches.length === 0 ? <div className="rounded-xl border bg-white p-8 text-center text-gray-500">ยังไม่มีสาขาในระบบ กรุณาสร้างสาขาก่อน</div> : null}
        </TabsContent>

        <TabsContent value="rates" className="space-y-5">
          <Card>
            <CardHeader><CardTitle>เพิ่มอัตราภาษีตามช่วงเวลา</CardTitle></CardHeader>
            <CardContent>
              <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); rateMutation.mutate(rateForm); }}>
                <div className="grid gap-4 md:grid-cols-3">
                  <Field label="รหัสอัตรา *"><Input required placeholder="VAT_STANDARD_7" value={rateForm.code} onChange={(event) => setRateForm((current) => ({ ...current, code: event.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, "") }))} /></Field>
                  <Field label="ชื่ออัตรา *"><Input required placeholder="VAT 7%" value={rateForm.name} onChange={(event) => setRateForm((current) => ({ ...current, name: event.target.value }))} /></Field>
                  <Field label="ประเภท"><select className={fieldClass} value={rateForm.tax_category} onChange={(event) => changeRateCategory(event.target.value as TaxCategory)}><option value="standard">อัตรามาตรฐาน</option><option value="zero">อัตรา 0%</option><option value="exempt">ยกเว้น VAT</option></select></Field>
                  <Field label="อัตรา (%)"><Input required type="number" min={0} max={100} step="0.01" disabled={rateForm.tax_category !== "standard"} value={rateForm.rate} onChange={(event) => setRateForm((current) => ({ ...current, rate: Number(event.target.value) }))} /></Field>
                  <Field label="รูปแบบราคา"><select className={fieldClass} value={rateForm.price_vat_type} disabled={rateForm.tax_category === "exempt"} onChange={(event) => setRateForm((current) => ({ ...current, price_vat_type: event.target.value as VatType }))}><VatTypeOptions excludeExempt={rateForm.tax_category !== "exempt"} /></select></Field>
                  <label className="flex items-center gap-3 self-end rounded-lg border p-3 text-sm"><input type="checkbox" checked={rateForm.is_default} onChange={(event) => setRateForm((current) => ({ ...current, is_default: event.target.checked }))} /> ใช้เป็นอัตราเริ่มต้น</label>
                  <Field label="วันที่เริ่มใช้ *"><Input required type="date" value={rateForm.effective_from} onChange={(event) => setRateForm((current) => ({ ...current, effective_from: event.target.value }))} /></Field>
                  <Field label="วันที่สิ้นสุด"><Input type="date" value={rateForm.effective_to ?? ""} onChange={(event) => setRateForm((current) => ({ ...current, effective_to: event.target.value || null }))} /></Field>
                  <Field label="เหตุผล *"><Input required minLength={3} value={rateForm.reason} onChange={(event) => setRateForm((current) => ({ ...current, reason: event.target.value }))} /></Field>
                </div>
                <Button type="submit" disabled={!settings.company.configured || rateMutation.isPending}>เพิ่มอัตราภาษี</Button>
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>อัตราภาษีทั้งหมด</CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-x-auto rounded-xl border">
                <Table>
                  <TableHeader><TableRow><TableHead>รหัส / ชื่อ</TableHead><TableHead>ประเภท</TableHead><TableHead>อัตรา</TableHead><TableHead>รูปแบบราคา</TableHead><TableHead>ช่วงใช้งาน</TableHead><TableHead>สถานะ</TableHead><TableHead /></TableRow></TableHeader>
                  <TableBody>
                    {settings.rates.map((rate) => <TableRow key={rate.id}>
                      <TableCell><div className="font-medium">{rate.name}</div><div className="font-mono text-xs text-gray-500">{rate.code}</div></TableCell>
                      <TableCell>{categoryLabel(rate.tax_category)}</TableCell>
                      <TableCell>{Number(rate.rate).toFixed(2)}%</TableCell>
                      <TableCell>{vatTypeLabel(rate.price_vat_type)}</TableCell>
                      <TableCell>{rate.effective_from} – {rate.effective_to ?? "ไม่กำหนด"}</TableCell>
                      <TableCell><div className="flex flex-wrap gap-1"><Badge variant={rate.is_active ? "success" : "secondary"}>{rate.is_active ? "ใช้งาน" : "ปิดแล้ว"}</Badge>{rate.is_default ? <Badge>ค่าเริ่มต้น</Badge> : null}</div></TableCell>
                      <TableCell>{rate.is_active ? <Button type="button" size="sm" variant="outline" disabled={closeRateMutation.isPending} onClick={() => { const reason = window.prompt("เหตุผลที่ปิดใช้งานอัตรานี้"); if (!reason || reason.trim().length < 3) return; const effectiveTo = rate.effective_from > today() ? rate.effective_from : today(); closeRateMutation.mutate({ id: rate.id, effectiveTo, reason }); }}>ปิดใช้งาน</Button> : null}</TableCell>
                    </TableRow>)}
                    {settings.rates.length === 0 ? <TableRow><TableCell colSpan={7} className="py-8 text-center text-gray-500">ยังไม่มีอัตราภาษี</TableCell></TableRow> : null}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }): JSX.Element {
  return <Label className="space-y-2"><span className="block text-sm font-medium text-gray-700">{label}</span>{children}</Label>;
}

function VatTypeOptions({ excludeExempt = false }: { excludeExempt?: boolean }): JSX.Element {
  return <><option value="included">ราคารวม VAT</option><option value="excluded">ราคาไม่รวม VAT</option>{excludeExempt ? null : <option value="exempt">ยกเว้น VAT</option>}</>;
}

function SummaryCard({ icon: Icon, label, value, ready }: { icon: typeof CheckCircle2; label: string; value: string; ready: boolean }): JSX.Element {
  return <Card><CardContent className="flex items-center gap-4 p-5"><div className={`rounded-xl p-3 ${ready ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}><Icon className="h-5 w-5" /></div><div><p className="text-sm text-gray-500">{label}</p><p className="font-semibold text-gray-900">{value}</p></div></CardContent></Card>;
}
