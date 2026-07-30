import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/ui/use-toast";
import { payableApi } from "@/lib/payableApi";
import { supplierApi } from "@/lib/purchaseApi";
import { useAuthStore } from "@/stores/auth.store";
import type { ApiResponse } from "@/types/api";
import type { Supplier } from "@/types/purchase";
import type { SupplierInvoice } from "@/types/payable";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => Promise<void> | void;
  preselectedInvoiceId?: string;
};

type RowState = {
  invoice_id: string;
  allocated_amount: string;
  wht_amount: string;
  wht_rate: string;
  wht_type: string;
};

const EMPTY_ROW: RowState = {
  invoice_id: "",
  allocated_amount: "0.00",
  wht_amount: "0.00",
  wht_rate: "0.00",
  wht_type: ""
};

function round2(value: number): string {
  return (Math.round((value + Number.EPSILON) * 100) / 100).toFixed(2);
}

export default function PaymentDialog({ open, onOpenChange, onSuccess, preselectedInvoiceId }: Props): JSX.Element {
  const { toast } = useToast();
  const branchId = useAuthStore((state) => state.branchId);
  const [paymentDate, setPaymentDate] = useState(new Date().toISOString().slice(0, 10));
  const [paymentMethod, setPaymentMethod] = useState<"bank_transfer" | "cheque" | "cash">("bank_transfer");
  const [bankAccount, setBankAccount] = useState("");
  const [referenceNo, setReferenceNo] = useState("");
  const [note, setNote] = useState("");
  const [rows, setRows] = useState<RowState[]>([EMPTY_ROW]);

  const invoicesQuery = useQuery({
    queryKey: ["payable", "payment-dialog-invoices"],
    queryFn: async () => (await payableApi.listInvoices({ page: 1, limit: 200 })).data as ApiResponse<SupplierInvoice[]>,
    enabled: open
  });
  const suppliersQuery = useQuery({
    queryKey: ["purchase", "suppliers", "payment-dialog"],
    queryFn: async () => (await supplierApi.list({ page: 1, limit: 200 })).data as ApiResponse<Supplier[]>,
    enabled: open
  });

  const invoices = useMemo(
    () => (invoicesQuery.data?.data ?? []).filter((item) => item.status === "unpaid" || item.status === "partial"),
    [invoicesQuery.data?.data]
  );
  const invoiceMap = useMemo(() => new Map(invoices.map((item) => [item.id, item])), [invoices]);
  const supplierMap = useMemo(() => new Map((suppliersQuery.data?.data ?? []).map((item) => [item.id, item])), [suppliersQuery.data?.data]);
  const selectedSupplierId = useMemo(() => {
    const first = rows.find((item) => item.invoice_id);
    return first ? invoiceMap.get(first.invoice_id)?.supplier_id ?? null : null;
  }, [invoiceMap, rows]);

  const availableInvoices = useMemo(
    () => invoices.filter((item) => !rows.some((row) => row.invoice_id === item.id) && (!selectedSupplierId || item.supplier_id === selectedSupplierId)),
    [invoices, rows, selectedSupplierId]
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    if (!preselectedInvoiceId || !invoiceMap.has(preselectedInvoiceId)) {
      setRows([EMPTY_ROW]);
      return;
    }
    const invoice = invoiceMap.get(preselectedInvoiceId)!;
    const supplier = supplierMap.get(invoice.supplier_id);
    const rate = Number(supplier?.wht_rate ?? 0);
    setRows([{
      invoice_id: invoice.id,
      allocated_amount: round2(Number(invoice.remaining_amount)),
      wht_amount: round2(Number(invoice.remaining_amount) * rate / 100),
      wht_rate: round2(rate),
      wht_type: supplier?.wht_type ?? ""
    }]);
    setBankAccount(supplier?.bank_account ?? "");
  }, [invoiceMap, open, preselectedInvoiceId, supplierMap]);

  const totals = useMemo(() => {
    const totalAllocated = rows.reduce((sum, row) => sum + Number(row.allocated_amount || 0), 0);
    const totalWht = rows.reduce((sum, row) => sum + Number(row.wht_amount || 0), 0);
    return { totalAllocated, totalWht, netPaid: totalAllocated - totalWht };
  }, [rows]);

  function updateRow(index: number, patch: Partial<RowState>): void {
    setRows((prev) => prev.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)));
  }

  function createRowForInvoice(invoice: SupplierInvoice): RowState {
    const supplier = supplierMap.get(invoice.supplier_id);
    const rate = Number(supplier?.wht_rate ?? 0);
    return {
      invoice_id: invoice.id,
      allocated_amount: round2(Number(invoice.remaining_amount)),
      wht_amount: round2(Number(invoice.remaining_amount) * rate / 100),
      wht_rate: round2(rate),
      wht_type: supplier?.wht_type ?? ""
    };
  }

  function handleInvoiceChange(index: number, invoiceId: string): void {
    const invoice = invoiceMap.get(invoiceId);
    if (!invoice) {
      updateRow(index, EMPTY_ROW);
      return;
    }
    const nextRow = createRowForInvoice(invoice);
    setRows((prev) => prev.map((row, rowIndex) => (rowIndex === index ? nextRow : row)));
  }

  function addRow(): void {
    if (!availableInvoices.length) {
      return;
    }
    setRows((prev) => [...prev, createRowForInvoice(availableInvoices[0])]);
  }

  function removeRow(index: number): void {
    setRows((prev) => (prev.length === 1 ? [EMPTY_ROW] : prev.filter((_, rowIndex) => rowIndex !== index)));
  }

  async function submit(): Promise<void> {
    if (!branchId) {
      toast({ title: "ไม่พบสาขาปัจจุบัน", variant: "destructive" });
      return;
    }
    const validRows = rows.filter((item) => item.invoice_id);
    if (!validRows.length) {
      toast({ title: "เลือกใบแจ้งหนี้อย่างน้อย 1 ใบ", variant: "destructive" });
      return;
    }
    try {
      const response = await payableApi.createPayment({
        branch_id: branchId,
        payment_date: paymentDate,
        payment_method: paymentMethod,
        bank_account: bankAccount || null,
        reference_no: referenceNo || null,
        allocations: validRows.map((item) => ({
          invoice_id: item.invoice_id,
          allocated_amount: Number(item.allocated_amount || 0),
          wht_amount: Number(item.wht_amount || 0),
          wht_rate: Number(item.wht_rate || 0),
          wht_type: item.wht_type || null
        })),
        note: note || null
      });
      toast({ title: `บันทึกการจ่ายแล้ว: ${response.data.data.payment_number}` });
      if (totals.totalWht > 0) {
        toast({ title: "ออกใบรับรอง WHT อัตโนมัติ" });
      }
      onOpenChange(false);
      await onSuccess();
    } catch (error) {
      toast({
        title: "บันทึกการจ่ายไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl">
        <DialogHeader>
          <DialogTitle>บันทึกการจ่าย</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>วันที่จ่าย*</Label>
                <Input type="date" value={paymentDate} onChange={(event) => setPaymentDate(event.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>วิธีการจ่าย*</Label>
                <div className="flex gap-4 rounded-md border border-gray-200 px-3 py-2 text-sm">
                  {[
                    { value: "bank_transfer", label: "โอนธนาคาร" },
                    { value: "cheque", label: "เช็ค" },
                    { value: "cash", label: "เงินสด" }
                  ].map((item) => (
                    <label key={item.value} className="flex items-center gap-2">
                      <input type="radio" checked={paymentMethod === item.value} onChange={() => setPaymentMethod(item.value as typeof paymentMethod)} />
                      {item.label}
                    </label>
                  ))}
                </div>
              </div>
              {paymentMethod !== "cash" ? (
                <>
                  <div className="space-y-2">
                    <Label>บัญชีปลายทาง</Label>
                    <Input value={bankAccount} onChange={(event) => setBankAccount(event.target.value)} />
                  </div>
                  <div className="space-y-2">
                    <Label>เลขที่อ้างอิง</Label>
                    <Input value={referenceNo} onChange={(event) => setReferenceNo(event.target.value)} />
                  </div>
                </>
              ) : null}
            </div>

            <div className="rounded-xl border border-gray-200">
              <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
                <p className="font-medium text-gray-900">ใบแจ้งหนี้ที่จ่าย</p>
                <Button variant="outline" size="sm" onClick={addRow} disabled={!availableInvoices.length}>Add invoice</Button>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>SINV</TableHead>
                    <TableHead className="text-right">ยอดค้าง</TableHead>
                    <TableHead className="text-right">จ่ายครั้งนี้</TableHead>
                    <TableHead className="text-right">WHT</TableHead>
                    <TableHead className="text-right">WHT%</TableHead>
                    <TableHead>wht_type</TableHead>
                    <TableHead className="text-right">จ่ายสุทธิ</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row, index) => {
                    const invoice = invoiceMap.get(row.invoice_id);
                    const options = invoice ? [invoice, ...availableInvoices] : availableInvoices;
                    const netPaid = Number(row.allocated_amount || 0) - Number(row.wht_amount || 0);
                    return (
                      <TableRow key={`${row.invoice_id || "new"}-${index}`}>
                        <TableCell>
                          <select className="h-9 rounded-md border border-gray-300 px-2 text-sm" value={row.invoice_id} onChange={(event) => handleInvoiceChange(index, event.target.value)}>
                            <option value="">เลือกใบแจ้งหนี้</option>
                            {options.map((item) => (
                              <option key={item.id} value={item.id}>{item.invoice_number}</option>
                            ))}
                          </select>
                        </TableCell>
                        <TableCell className="text-right">{invoice ? Number(invoice.remaining_amount).toLocaleString("th-TH", { minimumFractionDigits: 2 }) : "-"}</TableCell>
                        <TableCell><Input type="number" value={row.allocated_amount} onChange={(event) => updateRow(index, { allocated_amount: event.target.value })} /></TableCell>
                        <TableCell><Input type="number" value={row.wht_amount} onChange={(event) => updateRow(index, { wht_amount: event.target.value })} /></TableCell>
                        <TableCell><Input type="number" value={row.wht_rate} onChange={(event) => updateRow(index, { wht_rate: event.target.value })} /></TableCell>
                        <TableCell><Input value={row.wht_type} onChange={(event) => updateRow(index, { wht_type: event.target.value })} /></TableCell>
                        <TableCell className="text-right font-medium text-blue-700">{netPaid.toLocaleString("th-TH", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</TableCell>
                        <TableCell><Button variant="outline" size="sm" onClick={() => removeRow(index)}>ลบ</Button></TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>

            <div className="space-y-2">
              <Label>หมายเหตุ</Label>
              <textarea className="min-h-[96px] w-full rounded-md border border-gray-300 px-3 py-2 text-sm" value={note} onChange={(event) => setNote(event.target.value)} />
            </div>
          </div>

          <div className="h-fit rounded-2xl border border-blue-100 bg-blue-50 p-5">
            <p className="text-sm font-medium text-blue-900">สรุป</p>
            <div className="mt-4 space-y-3 text-sm">
              <div className="flex items-center justify-between"><span>รวมยอดจ่าย</span><strong>{totals.totalAllocated.toLocaleString("th-TH", { minimumFractionDigits: 2 })}</strong></div>
              <div className="flex items-center justify-between"><span>รวม WHT หัก</span><strong>{totals.totalWht.toLocaleString("th-TH", { minimumFractionDigits: 2 })}</strong></div>
              <div className="flex items-center justify-between border-t border-blue-200 pt-3 text-base text-blue-900"><span>เงินโอนจริง</span><strong>{totals.netPaid.toLocaleString("th-TH", { minimumFractionDigits: 2 })}</strong></div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>ยกเลิก</Button>
          <Button onClick={() => void submit()}>บันทึกการจ่าย</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
