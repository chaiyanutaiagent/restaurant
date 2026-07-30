import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { etaxApi } from "@/lib/etaxApi";
import { posApi } from "@/lib/posApi";
import type { ApiResponse } from "@/types/api";
import type { SaleOrder } from "@/types/pos";
import type { TaxDocumentListItem } from "@/types/etax";

type IssueTaxInvoiceDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialSaleOrderId?: string;
  onSuccess?: (documentId: string) => void;
};

function formatCurrency(value: number | string): string {
  return new Intl.NumberFormat("th-TH", {
    style: "currency",
    currency: "THB",
    minimumFractionDigits: 2
  }).format(Number(value || 0));
}

export default function IssueTaxInvoiceDialog({
  open,
  onOpenChange,
  initialSaleOrderId,
  onSuccess
}: IssueTaxInvoiceDialogProps): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [saleOrderId, setSaleOrderId] = useState(initialSaleOrderId ?? "");
  const [documentType, setDocumentType] = useState<"abbreviated_tax_invoice" | "full_tax_invoice">("abbreviated_tax_invoice");
  const [buyerTaxId, setBuyerTaxId] = useState("");
  const [buyerName, setBuyerName] = useState("");
  const [buyerBranchCode, setBuyerBranchCode] = useState("00000");
  const [buyerAddress, setBuyerAddress] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setSaleOrderId(initialSaleOrderId ?? "");
    }
  }, [initialSaleOrderId, open]);

  const salesQuery = useQuery({
    queryKey: ["etax", "sales", "recent"],
    enabled: open,
    queryFn: async () => {
      const response = await posApi.listSales({ status: "completed", limit: 20 });
      return response.data as ApiResponse<SaleOrder[]>;
    }
  });

  const documentsQuery = useQuery({
    queryKey: ["etax", "documents", "issued-lookup"],
    enabled: open,
    queryFn: async () => {
      const response = await etaxApi.listDocuments({ limit: 100 });
      return response.data as ApiResponse<TaxDocumentListItem[]>;
    }
  });

  const selectedSale = useMemo(
    () => (salesQuery.data?.data ?? []).find((sale) => sale.id === saleOrderId) ?? null,
    [saleOrderId, salesQuery.data]
  );

  const existingDocument = useMemo(
    () =>
      (documentsQuery.data?.data ?? []).find((item) =>
        selectedSale ? item.document_number.startsWith("TINV") && item.id && true : false
      ) ?? null,
    [documentsQuery.data, selectedSale]
  );

  async function submit(): Promise<void> {
    if (!saleOrderId) {
      toast({ title: "กรุณาเลือกบิลขาย", variant: "destructive" });
      return;
    }
    if (documentType === "full_tax_invoice" && !buyerTaxId.trim()) {
      toast({ title: "กรุณากรอกเลขผู้เสียภาษีผู้ซื้อ", variant: "destructive" });
      return;
    }
    if (documentType === "full_tax_invoice" && !buyerName.trim()) {
      toast({ title: "กรุณากรอกชื่อผู้ซื้อ", variant: "destructive" });
      return;
    }

    setSubmitting(true);
    try {
      const response = await etaxApi.issueTaxInvoice({
        sale_order_id: saleOrderId,
        document_type: documentType,
        buyer_tax_id: buyerTaxId || undefined,
        buyer_name: buyerName || undefined,
        buyer_branch_code: buyerBranchCode || undefined,
        buyer_address: buyerAddress || undefined
      });
      const document = (response.data as ApiResponse<{ id: string; document_number: string }>).data;
      toast({ title: `ออกใบกำกับภาษีแล้ว: ${document.document_number}` });
      await queryClient.invalidateQueries({ queryKey: ["etax"] });
      onSuccess?.(document.id);
      onOpenChange(false);
    } catch (error) {
      toast({
        title: "ออกใบกำกับภาษีไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>ออกใบกำกับภาษี</DialogTitle>
          <DialogDescription>เลือกบิลขายและระบุประเภทเอกสารก่อนยืนยัน</DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-gray-900">Step 1: เลือกบิลขาย</h3>
            <select
              className="h-10 w-full rounded-md border border-gray-300 px-3 text-sm"
              value={saleOrderId}
              onChange={(event) => setSaleOrderId(event.target.value)}
            >
              <option value="">เลือกบิลขาย</option>
              {(salesQuery.data?.data ?? []).map((sale) => (
                <option key={sale.id} value={sale.id}>
                  {sale.order_number} • {sale.created_at.slice(0, 10)} • {formatCurrency(sale.total_amount)}
                </option>
              ))}
            </select>
            {selectedSale ? (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm">
                <p><strong>เลขที่บิล:</strong> {selectedSale.order_number}</p>
                <p><strong>ยอดรวม:</strong> {formatCurrency(selectedSale.total_amount)}</p>
                <p><strong>VAT:</strong> {formatCurrency(selectedSale.vat_amount)}</p>
              </div>
            ) : null}
            {existingDocument && selectedSale ? (
              <p className="text-sm text-amber-600">บิลนี้อาจมีเอกสารภาษีถูกออกแล้ว กรุณาตรวจสอบก่อนยืนยัน</p>
            ) : null}
          </div>

          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-gray-900">Step 2: ประเภทเอกสาร</h3>
            <div className="grid gap-3 md:grid-cols-2">
              <button
                type="button"
                className={`rounded-lg border p-3 text-left ${documentType === "abbreviated_tax_invoice" ? "border-blue-500 bg-blue-50" : "border-gray-200"}`}
                onClick={() => setDocumentType("abbreviated_tax_invoice")}
              >
                ใบกำกับภาษีอย่างย่อ
              </button>
              <button
                type="button"
                className={`rounded-lg border p-3 text-left ${documentType === "full_tax_invoice" ? "border-blue-500 bg-blue-50" : "border-gray-200"}`}
                onClick={() => setDocumentType("full_tax_invoice")}
              >
                ใบกำกับภาษีแบบเต็มรูปแบบ
              </button>
            </div>
            {documentType === "full_tax_invoice" ? (
              <div className="grid gap-4 md:grid-cols-2">
                <div className="grid gap-2">
                  <Label>เลขผู้เสียภาษีผู้ซื้อ*</Label>
                  <Input value={buyerTaxId} onChange={(event) => setBuyerTaxId(event.target.value)} />
                </div>
                <div className="grid gap-2">
                  <Label>ชื่อผู้ซื้อ*</Label>
                  <Input value={buyerName} onChange={(event) => setBuyerName(event.target.value)} />
                </div>
                <div className="grid gap-2">
                  <Label>รหัสสาขา</Label>
                  <Input value={buyerBranchCode} onChange={(event) => setBuyerBranchCode(event.target.value)} />
                </div>
                <div className="grid gap-2 md:col-span-2">
                  <Label>ที่อยู่</Label>
                  <textarea
                    className="min-h-[100px] rounded-md border border-gray-300 px-3 py-2 text-sm"
                    value={buyerAddress}
                    onChange={(event) => setBuyerAddress(event.target.value)}
                  />
                </div>
              </div>
            ) : null}
          </div>

          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-gray-900">Step 3: ยืนยัน</h3>
            <div className="rounded-lg border border-gray-200 bg-white p-4 text-sm">
              <p><strong>ประเภท:</strong> {documentType === "full_tax_invoice" ? "เต็มรูปแบบ" : "อย่างย่อ"}</p>
              <p><strong>ผู้ซื้อ:</strong> {buyerName || selectedSale?.customer_name || "-"}</p>
              <p><strong>เลขผู้เสียภาษี:</strong> {buyerTaxId || selectedSale?.customer_tax_id || "-"}</p>
              <p><strong>ยอดรวม:</strong> {selectedSale ? formatCurrency(selectedSale.total_amount) : "-"}</p>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            ปิด
          </Button>
          <Button type="button" onClick={() => void submit()} disabled={submitting}>
            ยืนยันการออกใบกำกับภาษี
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
