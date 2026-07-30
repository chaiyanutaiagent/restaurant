import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Receipt, RefreshCcw } from "lucide-react";
import { useMemo, useState } from "react";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import CreditNoteDialog from "@/pages/etax/CreditNoteDialog";
import IssueTaxInvoiceDialog from "@/pages/etax/IssueTaxInvoiceDialog";
import TaxDocumentDetailDialog from "@/pages/etax/TaxDocumentDetailDialog";
import { etaxApi } from "@/lib/etaxApi";
import { payableApi } from "@/lib/payableApi";
import type { ApiResponse } from "@/types/api";
import type { TaxDocumentListItem } from "@/types/etax";
import type { VatReturnReport } from "@/types/payable";

function formatCurrency(value: number | string): string {
  return new Intl.NumberFormat("th-TH", {
    style: "currency",
    currency: "THB",
    minimumFractionDigits: 2
  }).format(Number(value || 0));
}

function formatThaiDate(value: string): string {
  const date = new Date(value);
  return new Intl.DateTimeFormat("th-TH", { dateStyle: "medium" }).format(date);
}

async function downloadFile(fetcher: Promise<{ data: Blob }>, filename: string): Promise<void> {
  const response = await fetcher;
  const url = window.URL.createObjectURL(response.data);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(url);
}

export default function ETaxPage(): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [documentType, setDocumentType] = useState("");
  const [status, setStatus] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [year, setYear] = useState(new Date().getFullYear());
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [issueDialogOpen, setIssueDialogOpen] = useState(false);
  const [detailDocumentId, setDetailDocumentId] = useState<string | null>(null);
  const [creditDocument, setCreditDocument] = useState<TaxDocumentListItem | null>(null);

  const documentsQuery = useQuery({
    queryKey: ["etax", "documents", { documentType, status, dateFrom, dateTo }],
    queryFn: async () => {
      const response = await etaxApi.listDocuments({
        document_type: documentType || undefined,
        status: status || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        page: 1,
        limit: 50
      });
      return response.data as ApiResponse<TaxDocumentListItem[]>;
    }
  });

  const vatSummaryQuery = useQuery({
    queryKey: ["etax", "vat-summary", year, month],
    queryFn: async () => {
      const response = await payableApi.vatReturn(year, month);
      return response.data as ApiResponse<VatReturnReport>;
    }
  });

  const documents = documentsQuery.data?.data ?? [];
  const vatSummary = vatSummaryQuery.data?.data;
  const thaiYear = year + 543;

  const totals = useMemo(() => ({
    totalAmount: documents.reduce((sum, item) => sum + Number(item.total_amount ?? 0), 0),
    totalVat: documents.reduce((sum, item) => sum + Number(item.vat_amount ?? 0), 0)
  }), [documents]);

  async function cancelDocument(document: TaxDocumentListItem): Promise<void> {
    const reason = window.prompt("เหตุผลในการยกเลิกเอกสาร", "ทดสอบการยกเลิก");
    if (!reason) {
      return;
    }
    try {
      await etaxApi.cancelDocument(document.id, reason);
      toast({ title: `ยกเลิกเอกสารแล้ว: ${document.document_number}` });
      await queryClient.invalidateQueries({ queryKey: ["etax"] });
    } catch (error) {
      toast({
        title: "ยกเลิกเอกสารไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="ใบกำกับภาษีอิเล็กทรอนิกส์"
        subtitle="e-Tax Invoice"
        actions={
          <Button onClick={() => setIssueDialogOpen(true)}>
            <Receipt className="mr-2 h-4 w-4" />
            ออกใบกำกับภาษี
          </Button>
        }
      />

      <Tabs defaultValue="documents" className="space-y-6">
        <TabsList className="grid w-full grid-cols-2 md:w-[360px]">
          <TabsTrigger value="documents">เอกสารทั้งหมด</TabsTrigger>
          <TabsTrigger value="vat">ภ.พ.30 สรุป VAT</TabsTrigger>
        </TabsList>

        <TabsContent value="documents" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>เอกสารทั้งหมด</span>
                <Button variant="outline" size="sm" onClick={() => void documentsQuery.refetch()}>
                  <RefreshCcw className="mr-2 h-4 w-4" />
                  รีเฟรช
                </Button>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-4">
                <select className="h-10 rounded-md border border-gray-300 px-3 text-sm" value={documentType} onChange={(event) => setDocumentType(event.target.value)}>
                  <option value="">ประเภททั้งหมด</option>
                  <option value="full_tax_invoice">ใบกำกับภาษีเต็มรูป</option>
                  <option value="abbreviated_tax_invoice">ใบกำกับภาษีอย่างย่อ</option>
                  <option value="credit_note">ใบลดหนี้</option>
                </select>
                <select className="h-10 rounded-md border border-gray-300 px-3 text-sm" value={status} onChange={(event) => setStatus(event.target.value)}>
                  <option value="">สถานะทั้งหมด</option>
                  <option value="issued">ออกแล้ว</option>
                  <option value="cancelled">ยกเลิกแล้ว</option>
                </select>
                <Input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
                <Input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
              </div>

              <div className="overflow-hidden rounded-xl border border-gray-200">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>เลขที่เอกสาร</TableHead>
                      <TableHead>ประเภท</TableHead>
                      <TableHead>วันที่ออก</TableHead>
                      <TableHead>ชื่อผู้ซื้อ</TableHead>
                      <TableHead>เลขผู้เสียภาษี</TableHead>
                      <TableHead>ยอดรวม</TableHead>
                      <TableHead>VAT</TableHead>
                      <TableHead>สถานะ</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {documents.map((document) => (
                      <TableRow key={document.id}>
                        <TableCell className="font-mono text-xs">{document.document_number}</TableCell>
                        <TableCell><Badge>{document.document_type}</Badge></TableCell>
                        <TableCell>{formatThaiDate(document.issue_date)}</TableCell>
                        <TableCell>{document.buyer_name || "-"}</TableCell>
                        <TableCell>{document.buyer_tax_id || "-"}</TableCell>
                        <TableCell>{formatCurrency(document.total_amount)}</TableCell>
                        <TableCell>{formatCurrency(document.vat_amount)}</TableCell>
                        <TableCell>
                          <Badge variant={document.status === "cancelled" ? "destructive" : "success"}>{document.status}</Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap gap-2">
                            <Button variant="outline" size="sm" onClick={() => setDetailDocumentId(document.id)}>ดู</Button>
                            <Button variant="outline" size="sm" onClick={() => void downloadFile(etaxApi.downloadXml(document.id), `${document.document_number}.xml`)}>XML</Button>
                            <Button variant="outline" size="sm" onClick={() => void downloadFile(etaxApi.downloadPdf(document.id), `${document.document_number}.html`)}>PDF</Button>
                            {document.status === "issued" && document.document_type !== "credit_note" ? (
                              <Button variant="outline" size="sm" onClick={() => setCreditDocument(document)}>ใบลดหนี้</Button>
                            ) : null}
                            {document.status === "issued" ? (
                              <Button variant="outline" size="sm" onClick={() => void cancelDocument(document)}>ยกเลิก</Button>
                            ) : null}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              <div className="flex justify-end gap-6 text-sm text-gray-600">
                <span>รวมยอด: {formatCurrency(totals.totalAmount)}</span>
                <span>รวม VAT: {formatCurrency(totals.totalVat)}</span>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="vat" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>ภ.พ.30 สรุป VAT</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <Input type="number" value={year} onChange={(event) => setYear(Number(event.target.value))} />
                <Input type="number" min={1} max={12} value={month} onChange={(event) => setMonth(Number(event.target.value))} />
                <div className="flex items-center rounded-md border border-gray-200 px-3 text-sm text-gray-500">พ.ศ. {thaiYear}</div>
              </div>

              <div className="grid gap-4 lg:grid-cols-3">
                <Card>
                  <CardHeader><CardTitle className="text-base">ภาษีขาย (Output VAT)</CardTitle></CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <p>VAT ขาย: {formatCurrency(vatSummary?.output_vat_sales ?? 0)}</p>
                    <p>VAT รวม: {formatCurrency(vatSummary?.output_vat_total ?? 0)}</p>
                    <p>จำนวนเอกสาร: {vatSummary?.output_doc_count ?? 0} ใบ</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader><CardTitle className="text-base">ภาษีซื้อ (Input VAT)</CardTitle></CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <p>ข้อมูลภาษีซื้อจากเจ้าหนี้</p>
                    <p>VAT ซื้อ: {formatCurrency(vatSummary?.input_vat_purchases ?? 0)}</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader><CardTitle className="text-base">VAT สุทธิที่ต้องนำส่ง</CardTitle></CardHeader>
                  <CardContent className="space-y-2">
                    <p className={`text-3xl font-semibold ${Number(vatSummary?.net_vat_payable ?? 0) >= 0 ? "text-blue-600" : "text-green-600"}`}>
                      {formatCurrency(vatSummary?.net_vat_payable ?? 0)}
                    </p>
                    <p className="text-sm text-gray-500">ยื่นแบบ ภ.พ.30 ภายในวันที่ 15 ของเดือนถัดไป</p>
                  </CardContent>
                </Card>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <IssueTaxInvoiceDialog
        open={issueDialogOpen}
        onOpenChange={setIssueDialogOpen}
        onSuccess={() => void queryClient.invalidateQueries({ queryKey: ["etax"] })}
      />
      <TaxDocumentDetailDialog
        open={Boolean(detailDocumentId)}
        onOpenChange={(value) => {
          if (!value) {
            setDetailDocumentId(null);
          }
        }}
        documentId={detailDocumentId}
      />
      <CreditNoteDialog
        open={Boolean(creditDocument)}
        onOpenChange={(value) => {
          if (!value) {
            setCreditDocument(null);
          }
        }}
        document={creditDocument}
        onSuccess={() => void queryClient.invalidateQueries({ queryKey: ["etax"] })}
      />
    </div>
  );
}
