import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";
import { etaxApi } from "@/lib/etaxApi";
import type { ApiResponse } from "@/types/api";
import type { TaxDocumentListItem } from "@/types/etax";

type CreditNoteDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  document: TaxDocumentListItem | null;
  onSuccess?: () => void;
};

function formatCurrency(value: number | string): string {
  return new Intl.NumberFormat("th-TH", {
    style: "currency",
    currency: "THB",
    minimumFractionDigits: 2
  }).format(Number(value || 0));
}

export default function CreditNoteDialog({
  open,
  onOpenChange,
  document,
  onSuccess
}: CreditNoteDialogProps): JSX.Element {
  const { toast } = useToast();
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(): Promise<void> {
    if (!document || !reason.trim()) {
      toast({ title: "กรุณาระบุเหตุผลในการออกใบลดหนี้", variant: "destructive" });
      return;
    }
    setSubmitting(true);
    try {
      const response = await etaxApi.issueCreditNote({
        original_document_id: document.id,
        reason
      });
      const created = (response.data as ApiResponse<{ document_number: string }>).data;
      toast({ title: `ออกใบลดหนี้แล้ว: ${created.document_number}` });
      setReason("");
      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      toast({
        title: "ออกใบลดหนี้ไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>ออกใบลดหนี้</DialogTitle>
          <DialogDescription>ยืนยันการออกใบลดหนี้จากเอกสารต้นทาง</DialogDescription>
        </DialogHeader>

        {document ? (
          <div className="space-y-4">
            <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm">
              <p><strong>เลขที่เอกสาร:</strong> {document.document_number}</p>
              <p><strong>ยอดรวม:</strong> {formatCurrency(document.total_amount)}</p>
              <p><strong>VAT:</strong> {formatCurrency(document.vat_amount)}</p>
            </div>
            <div className="grid gap-2">
              <label className="text-sm font-medium">เหตุผลในการออกใบลดหนี้*</label>
              <textarea
                className="min-h-[120px] rounded-md border border-gray-300 px-3 py-2 text-sm"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </div>
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>ปิด</Button>
          <Button onClick={() => void submit()} disabled={submitting}>ยืนยัน</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
