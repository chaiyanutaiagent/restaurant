import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Calculator, CreditCard, Download, FileCheck2, FileText, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import { usePermission } from "@/hooks/usePermission";
import { payableApi } from "@/lib/payableApi";
import { supplierApi } from "@/lib/purchaseApi";
import CreateInvoiceDialog from "@/pages/payable/CreateInvoiceDialog";
import PaymentDialog from "@/pages/payable/PaymentDialog";
import type { ApiResponse } from "@/types/api";
import type { Supplier } from "@/types/purchase";
import type { APPayment, SupplierInvoice, VatReturnReport, WHTCertificate } from "@/types/payable";

function formatCurrency(value: number | string): string {
  return new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB", minimumFractionDigits: 2 }).format(Number(value || 0));
}

function formatThaiDate(value: string): string {
  const dt = new Date(value.includes("T") ? value : `${value}T00:00:00`);
  return new Intl.DateTimeFormat("th-TH", { dateStyle: "medium" }).format(dt);
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(url);
}

const STATUS_STYLES: Record<string, string> = {
  unpaid: "bg-red-100 text-red-700",
  partial: "bg-orange-100 text-orange-700",
  paid: "bg-green-100 text-green-700",
  cancelled: "bg-gray-100 text-gray-700"
};

export default function PayablePage(): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const canCreate = usePermission("accounting.payment.create");
  const [supplierId, setSupplierId] = useState("");
  const [statusValue, setStatusValue] = useState("");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [paymentDialogOpen, setPaymentDialogOpen] = useState(false);
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string | undefined>(undefined);
  const [year, setYear] = useState(new Date().getFullYear());
  const [month, setMonth] = useState(new Date().getMonth() + 1);

  const suppliersQuery = useQuery({
    queryKey: ["purchase", "suppliers", "payable-page"],
    queryFn: async () => (await supplierApi.list({ page: 1, limit: 200 })).data as ApiResponse<Supplier[]>
  });
  const invoicesQuery = useQuery({
    queryKey: ["payable", "invoices", supplierId, statusValue, overdueOnly, dateFrom, dateTo],
    queryFn: async () => (
      await payableApi.listInvoices({
        supplier_id: supplierId || undefined,
        status: statusValue || undefined,
        overdue_only: overdueOnly || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        page: 1,
        limit: 200
      })
    ).data as ApiResponse<SupplierInvoice[]>
  });
  const paymentsQuery = useQuery({
    queryKey: ["payable", "payments"],
    queryFn: async () => (await payableApi.listPayments({ page: 1, limit: 200 })).data as ApiResponse<APPayment[]>
  });
  const certsQuery = useQuery({
    queryKey: ["payable", "wht-certs"],
    queryFn: async () => (await payableApi.listWhtCerts({ page: 1, limit: 200 })).data as ApiResponse<WHTCertificate[]>
  });
  const vatQuery = useQuery({
    queryKey: ["payable", "vat-return", year, month],
    queryFn: async () => (await payableApi.vatReturn(year, month)).data as ApiResponse<VatReturnReport>
  });

  const invoices = invoicesQuery.data?.data ?? [];
  const payments = paymentsQuery.data?.data ?? [];
  const certs = certsQuery.data?.data ?? [];
  const vat = vatQuery.data?.data;
  const certByPaymentId = useMemo(() => new Map(certs.map((item) => [item.payment_id, item])), [certs]);
  const summary = useMemo(() => {
    const outstanding = invoices.filter((item) => item.status === "unpaid" || item.status === "partial");
    const overdue = invoices.filter((item) => item.is_overdue);
    const paid = invoices.filter((item) => item.status === "paid");
    return {
      outstandingCount: outstanding.length,
      outstandingAmount: outstanding.reduce((sum, item) => sum + Number(item.remaining_amount), 0),
      overdueCount: overdue.length,
      overdueAmount: overdue.reduce((sum, item) => sum + Number(item.remaining_amount), 0),
      paidCount: paid.length
    };
  }, [invoices]);

  async function refreshAll(): Promise<void> {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["payable"] }),
      queryClient.invalidateQueries({ queryKey: ["etax"] })
    ]);
  }

  async function cancelInvoice(invoice: SupplierInvoice): Promise<void> {
    if (!window.confirm(`ต้องการยกเลิก ${invoice.invoice_number} ใช่หรือไม่`)) {
      return;
    }
    try {
      await payableApi.cancelInvoice(invoice.id);
      toast({ title: `ยกเลิกแล้ว: ${invoice.invoice_number}` });
      await refreshAll();
    } catch (error) {
      toast({
        title: "ยกเลิกไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  async function downloadVoucher(payment: APPayment): Promise<void> {
    const response = await payableApi.downloadVoucher(payment.id);
    downloadBlob(response.data, `voucher_${payment.payment_number}.html`);
  }

  async function downloadWht(cert: WHTCertificate): Promise<void> {
    const response = await payableApi.downloadWhtCert(cert.id);
    downloadBlob(response.data, `${cert.certificate_number}.html`);
  }

  return (
    <div className="space-y-6">
      <PageHeader title="เจ้าหนี้และการจ่าย" subtitle="Accounts Payable" actions={canCreate ? <Button onClick={() => setCreateDialogOpen(true)}><Plus className="mr-2 h-4 w-4" />สร้างใบแจ้งหนี้</Button> : undefined} />

      <Tabs defaultValue="invoices" className="space-y-6">
        <TabsList className="grid w-full grid-cols-2 md:grid-cols-4">
          <TabsTrigger value="invoices">ใบแจ้งหนี้</TabsTrigger>
          <TabsTrigger value="payments">บันทึกการจ่าย</TabsTrigger>
          <TabsTrigger value="wht">ใบรับรอง WHT</TabsTrigger>
          <TabsTrigger value="vat">ภ.พ.30</TabsTrigger>
        </TabsList>

        <TabsContent value="invoices" className="space-y-4">
          <div className="grid gap-3 xl:grid-cols-4">
            <select className="h-10 rounded-md border border-gray-300 px-3 text-sm" value={supplierId} onChange={(event) => setSupplierId(event.target.value)}>
              <option value="">ทุกซัพพลายเออร์</option>
              {(suppliersQuery.data?.data ?? []).map((item) => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
            <select className="h-10 rounded-md border border-gray-300 px-3 text-sm" value={statusValue} onChange={(event) => setStatusValue(event.target.value)}>
              <option value="">ทุกสถานะ</option>
              <option value="unpaid">unpaid</option>
              <option value="partial">partial</option>
              <option value="paid">paid</option>
              <option value="cancelled">cancelled</option>
            </select>
            <label className="flex items-center gap-2 rounded-md border border-gray-300 px-3 text-sm text-gray-700">
              <input type="checkbox" checked={overdueOnly} onChange={(event) => setOverdueOnly(event.target.checked)} />
              เกินกำหนดเท่านั้น
            </label>
            <div className="grid gap-3 md:grid-cols-2">
              <Input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
              <Input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <Card className="border-orange-200 bg-orange-50"><CardContent className="p-4"><p className="text-sm text-orange-700">ยังค้างชำระ</p><p className="mt-2 text-2xl font-semibold text-orange-900">{summary.outstandingCount} ใบ</p><p className="text-sm text-orange-700">{formatCurrency(summary.outstandingAmount)}</p></CardContent></Card>
            <Card className="border-red-200 bg-red-50"><CardContent className="p-4"><p className="text-sm text-red-700">เกินกำหนด</p><p className="mt-2 text-2xl font-semibold text-red-900">{summary.overdueCount} ใบ</p><p className="text-sm text-red-700">{formatCurrency(summary.overdueAmount)}</p></CardContent></Card>
            <Card className="border-green-200 bg-green-50"><CardContent className="p-4"><p className="text-sm text-green-700">ชำระแล้ว</p><p className="mt-2 text-2xl font-semibold text-green-900">{summary.paidCount} ใบ</p></CardContent></Card>
          </div>

          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>เลขที่ใบแจ้งหนี้</TableHead>
                    <TableHead>ซัพพลายเออร์</TableHead>
                    <TableHead>เลข PO อ้างอิง</TableHead>
                    <TableHead>วันที่ใบแจ้งหนี้</TableHead>
                    <TableHead>ครบกำหนด</TableHead>
                    <TableHead>ยอดรวม</TableHead>
                    <TableHead>ชำระแล้ว</TableHead>
                    <TableHead>ค้างชำระ</TableHead>
                    <TableHead>สถานะ</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {invoices.map((invoice) => (
                    <TableRow key={invoice.id}>
                      <TableCell className="font-mono text-xs">{invoice.invoice_number}</TableCell>
                      <TableCell>{invoice.supplier_name}</TableCell>
                      <TableCell>{invoice.po_id ? invoice.po_id.slice(0, 8) : "-"}</TableCell>
                      <TableCell>{formatThaiDate(invoice.invoice_date)}</TableCell>
                      <TableCell className={invoice.is_overdue ? "font-medium text-red-600" : ""}>{formatThaiDate(invoice.due_date)}</TableCell>
                      <TableCell>{formatCurrency(invoice.total_amount)}</TableCell>
                      <TableCell>{formatCurrency(invoice.paid_amount)}</TableCell>
                      <TableCell className={Number(invoice.remaining_amount) > 0 ? "font-semibold text-red-600" : ""}>{formatCurrency(invoice.remaining_amount)}</TableCell>
                      <TableCell><Badge variant="secondary" className={STATUS_STYLES[invoice.status] ?? ""}>{invoice.status}</Badge></TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-2">
                          {canCreate && invoice.status !== "paid" && invoice.status !== "cancelled" ? (
                            <Button variant="outline" size="sm" onClick={() => { setSelectedInvoiceId(invoice.id); setPaymentDialogOpen(true); }}>จ่าย</Button>
                          ) : null}
                          {canCreate && invoice.status === "unpaid" ? (
                            <Button variant="outline" size="sm" onClick={() => void cancelInvoice(invoice)}>ยกเลิก</Button>
                          ) : null}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="payments" className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><CreditCard className="h-5 w-5" />บันทึกการจ่าย</CardTitle></CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>เลขที่การจ่าย</TableHead>
                    <TableHead>วันที่จ่าย</TableHead>
                    <TableHead>วิธีจ่าย</TableHead>
                    <TableHead>ใบแจ้งหนี้ที่ตัด</TableHead>
                    <TableHead>จำนวน</TableHead>
                    <TableHead>เลขที่อ้างอิง</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {payments.map((payment) => {
                    const cert = certByPaymentId.get(payment.id);
                    return (
                      <TableRow key={payment.id}>
                        <TableCell className="font-mono text-xs">{payment.payment_number}</TableCell>
                        <TableCell>{formatThaiDate(payment.payment_date)}</TableCell>
                        <TableCell>{payment.payment_method}</TableCell>
                        <TableCell>{payment.allocations.map((item) => item.invoice_number).join(", ")}</TableCell>
                        <TableCell>{formatCurrency(payment.total_amount)}</TableCell>
                        <TableCell>{payment.reference_no || "-"}</TableCell>
                        <TableCell>
                          <div className="flex flex-wrap gap-2">
                            <Button variant="outline" size="sm" onClick={() => window.alert(`${payment.payment_number}\n${formatCurrency(payment.total_amount)}`)}>ดู</Button>
                            <Button variant="outline" size="sm" onClick={() => void downloadVoucher(payment)}><FileText className="mr-1 h-4 w-4" />ใบสำคัญจ่าย</Button>
                            <Button variant="outline" size="sm" disabled={!cert} onClick={() => cert ? void downloadWht(cert) : undefined}><FileCheck2 className="mr-1 h-4 w-4" />WHT</Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="wht" className="space-y-4">
          <Card>
            <CardHeader><CardTitle>ใบรับรอง WHT</CardTitle></CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>เลขที่ใบรับรอง</TableHead>
                    <TableHead>ซัพพลายเออร์</TableHead>
                    <TableHead>ประเภทเงินได้</TableHead>
                    <TableHead>อัตรา WHT (%)</TableHead>
                    <TableHead>เงินได้</TableHead>
                    <TableHead>ภาษีที่หัก</TableHead>
                    <TableHead>วันที่ออก</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {certs.map((cert) => (
                    <TableRow key={cert.id}>
                      <TableCell className="font-mono text-xs">{cert.certificate_number}</TableCell>
                      <TableCell><div>{cert.supplier_name}</div><div className="text-xs text-gray-500">{cert.supplier_tax_id || "-"}</div></TableCell>
                      <TableCell>{cert.income_type || cert.wht_type}</TableCell>
                      <TableCell>{Number(cert.wht_rate).toFixed(2)}%</TableCell>
                      <TableCell>{formatCurrency(cert.base_amount)}</TableCell>
                      <TableCell>{formatCurrency(cert.wht_amount)}</TableCell>
                      <TableCell>{formatThaiDate(cert.issue_date)}</TableCell>
                      <TableCell><Button variant="outline" size="sm" onClick={() => void downloadWht(cert)}><Download className="mr-1 h-4 w-4" />ดาวน์โหลด 50 ทวิ</Button></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="vat" className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Calculator className="h-5 w-5" />สรุปภาษีมูลค่าเพิ่ม (ภ.พ.30)</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <Input type="number" value={year} onChange={(event) => setYear(Number(event.target.value))} />
                <Input type="number" min={1} max={12} value={month} onChange={(event) => setMonth(Number(event.target.value))} />
                <Button onClick={() => void vatQuery.refetch()}>คำนวณ</Button>
              </div>
              <div className={Number(vat?.net_vat_payable ?? 0) > 0 ? "rounded-3xl border border-orange-200 bg-orange-50 p-6" : Number(vat?.net_vat_payable ?? 0) < 0 ? "rounded-3xl border border-green-200 bg-green-50 p-6" : "rounded-3xl border border-blue-200 bg-blue-50 p-6"}>
                <div className="mb-6 text-center"><h3 className="text-2xl font-semibold text-gray-900">สรุปภาษีมูลค่าเพิ่ม (ภ.พ.30)</h3><p className="mt-2 text-gray-600">เดือน {vat?.month_label ?? "-"}</p></div>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-2xl border border-white/80 bg-white/70 p-4">
                    <p className="font-medium text-gray-900">ภาษีขาย (ขาออก)</p>
                    <p className="mt-3 text-sm text-gray-600">จำนวนเอกสาร: {vat?.output_doc_count ?? 0}</p>
                    <p className="text-sm text-gray-600">VAT ขาย: {formatCurrency(vat?.output_vat_sales ?? 0)}</p>
                    <p className="text-sm text-gray-600">VAT รวม: {formatCurrency(vat?.output_vat_total ?? 0)}</p>
                  </div>
                  <div className="rounded-2xl border border-white/80 bg-white/70 p-4">
                    <p className="font-medium text-gray-900">ภาษีซื้อ (ขาเข้า)</p>
                    <p className="mt-3 text-sm text-gray-600">จำนวนใบแจ้งหนี้: {vat?.input_invoice_count ?? 0}</p>
                    <p className="text-sm text-gray-600">VAT ซื้อ: {formatCurrency(vat?.input_vat_purchases ?? 0)}</p>
                    <p className="text-sm text-gray-600">VAT รวม: {formatCurrency(vat?.input_vat_total ?? 0)}</p>
                  </div>
                </div>
                <div className="mt-5 rounded-2xl bg-white/80 p-5 text-center">
                  <p className="text-lg font-semibold text-gray-900">VAT สุทธิ = {formatCurrency(vat?.output_vat_total ?? 0)} - {formatCurrency(vat?.input_vat_total ?? 0)} = {formatCurrency(vat?.net_vat_payable ?? 0)}</p>
                  <p className="mt-2 text-sm text-gray-600">{vat?.net_vat_label ?? "-"}</p>
                  <p className="mt-1 text-sm text-gray-600">ต้องยื่นภายใน: {vat?.filing_due_date ?? "-"}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <CreateInvoiceDialog open={createDialogOpen} onOpenChange={setCreateDialogOpen} onSuccess={refreshAll} />
      <PaymentDialog open={paymentDialogOpen} onOpenChange={(open) => { setPaymentDialogOpen(open); if (!open) { setSelectedInvoiceId(undefined); } }} onSuccess={refreshAll} preselectedInvoiceId={selectedInvoiceId} />
    </div>
  );
}
