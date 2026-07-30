import { useQuery } from "@tanstack/react-query";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { etaxApi } from "@/lib/etaxApi";
import { formatDateTimeTh } from "@/lib/utils";
import type { ApiResponse } from "@/types/api";
import type { TaxDocument } from "@/types/etax";

type TaxDocumentDetailDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  documentId: string | null;
};

function formatCurrency(value: number | string): string {
  return new Intl.NumberFormat("th-TH", {
    style: "currency",
    currency: "THB",
    minimumFractionDigits: 2
  }).format(Number(value || 0));
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

export default function TaxDocumentDetailDialog({
  open,
  onOpenChange,
  documentId
}: TaxDocumentDetailDialogProps): JSX.Element {
  const detailQuery = useQuery({
    queryKey: ["etax", "document", documentId],
    enabled: open && Boolean(documentId),
    queryFn: async () => {
      const response = await etaxApi.getDocument(documentId ?? "");
      return response.data as ApiResponse<TaxDocument>;
    }
  });

  const document = detailQuery.data?.data;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            <span>{document?.document_number ?? "รายละเอียดเอกสาร"}</span>
            {document ? <Badge>{document.document_type}</Badge> : null}
            {document ? <Badge variant={document.status === "cancelled" ? "destructive" : "success"}>{document.status}</Badge> : null}
          </DialogTitle>
        </DialogHeader>

        {document ? (
          <div className="space-y-6">
            <section className="grid gap-4 md:grid-cols-2">
              <div className="rounded-lg border border-gray-200 p-4 text-sm">
                <h3 className="mb-2 font-semibold">ข้อมูลเอกสาร</h3>
                <p>เลขที่: {document.document_number}</p>
                <p>วันที่ออก: {formatDateTimeTh(document.issue_datetime)}</p>
                <p>ประเภท: {document.document_type}</p>
                <p>อ้างอิงบิลขาย: {document.reference_type} / {document.reference_id}</p>
              </div>
              <div className="rounded-lg border border-gray-200 p-4 text-sm">
                <h3 className="mb-2 font-semibold">ผู้ขาย</h3>
                <p>{document.seller_name}</p>
                <p>{document.seller_tax_id}</p>
                <p>สาขา: {document.seller_branch_code ?? "-"}</p>
                <p>{document.seller_address ?? "-"}</p>
              </div>
            </section>

            <section className="rounded-lg border border-gray-200 p-4 text-sm">
              <h3 className="mb-2 font-semibold">ผู้ซื้อ</h3>
              <p>{document.buyer_name || "ไม่ระบุ"}</p>
              <p>{document.buyer_tax_id || "ไม่ระบุ"}</p>
              <p>สาขา: {document.buyer_branch_code || "-"}</p>
              <p>{document.buyer_address || "-"}</p>
            </section>

            <section className="overflow-hidden rounded-lg border border-gray-200">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ลำดับ</TableHead>
                    <TableHead>รายการ</TableHead>
                    <TableHead>จำนวน</TableHead>
                    <TableHead>หน่วย</TableHead>
                    <TableHead>ราคา/หน่วย</TableHead>
                    <TableHead>ส่วนลด</TableHead>
                    <TableHead>VAT</TableHead>
                    <TableHead>รวม</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {document.items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>{item.line_number}</TableCell>
                      <TableCell>{item.description}</TableCell>
                      <TableCell>{item.qty}</TableCell>
                      <TableCell>{item.unit_code ?? "-"}</TableCell>
                      <TableCell>{formatCurrency(item.unit_price)}</TableCell>
                      <TableCell>{formatCurrency(item.discount_amount)}</TableCell>
                      <TableCell>{formatCurrency(item.vat_amount)}</TableCell>
                      <TableCell>{formatCurrency(item.line_total)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </section>

            <section className="rounded-lg border border-gray-200 p-4 text-sm">
              <h3 className="mb-2 font-semibold">สรุปยอด</h3>
              <p>ยอดรวมก่อน VAT: {formatCurrency(document.subtotal)}</p>
              <p>VAT 7%: {formatCurrency(document.vat_amount)}</p>
              <p className="font-semibold">รวมทั้งสิ้น: {formatCurrency(document.total_amount)}</p>
              <p className="mt-3 text-xs text-gray-500">XML Hash: {(document.xml_hash ?? "-").slice(0, 32)}...</p>
              {document.cancelled_at ? (
                <p className="mt-2 text-red-600">ยกเลิกเมื่อ {formatDateTimeTh(document.cancelled_at)} • {document.cancel_reason}</p>
              ) : null}
              {document.document_type === "credit_note" ? (
                <p className="mt-2 text-gray-600">อ้างอิงเอกสารต้นทาง: {document.original_document_id}</p>
              ) : null}
            </section>
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>ปิด</Button>
          {document ? (
            <>
              <Button variant="outline" onClick={() => void downloadFile(etaxApi.downloadXml(document.id), `${document.document_number}.xml`)}>
                ดาวน์โหลด XML
              </Button>
              <Button onClick={() => void downloadFile(etaxApi.downloadPdf(document.id), `${document.document_number}.html`)}>
                ดาวน์โหลด PDF
              </Button>
            </>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
