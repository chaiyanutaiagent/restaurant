import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
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
  wht_base_amount: string;
  wht_rate: string;
  wht_type: string;
};

const EMPTY_ROW: RowState = {
  invoice_id: "",
  allocated_amount: "0.00",
  wht_base_amount: "",
  wht_rate: "0.00",
  wht_type: ""
};

function round2(value: number): string {
  return (Math.round((value + Number.EPSILON) * 100) / 100).toFixed(2);
}

export default function PaymentDialog({ open, onOpenChange, onSuccess, preselectedInvoiceId }: Props): JSX.Element {
  const { toast } = useToast();
  const branchId = useAuthStore((state) => state.branchId);
  const companyId = useAuthStore((state) => state.companyId);
  const submitting = useRef(false);
  const initialized = useRef(false);
  const [saving, setSaving] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [requestKey, setRequestKey] = useState(() => crypto.randomUUID());
  const retryPayload = useRef<object | null>(null);
  const [uncertain, setUncertain] = useState(false);
  const [paymentDate, setPaymentDate] = useState(new Date().toISOString().slice(0, 10));
  const [paymentMethod, setPaymentMethod] = useState<"bank_transfer" | "cheque" | "cash">("bank_transfer");
  const [bankAccount, setBankAccount] = useState("");
  const [referenceNo, setReferenceNo] = useState("");
  const [note, setNote] = useState("");
  const [rows, setRows] = useState<RowState[]>([EMPTY_ROW]);

  const invoicesQuery = useQuery({
    queryKey: ["payable", "payment-dialog-invoices", companyId, branchId],
    queryFn: async () => (await payableApi.listInvoices({ page: 1, limit: 200 })).data as ApiResponse<SupplierInvoice[]>,
    enabled: open
  });
  const suppliersQuery = useQuery({
    queryKey: ["purchase", "suppliers", "payment-dialog", companyId, branchId],
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
      initialized.current = false;
      return;
    }
    if (initialized.current || !invoicesQuery.isSuccess || !suppliersQuery.isSuccess) return;
    initialized.current = true;
    setRequestKey(crypto.randomUUID());
    retryPayload.current = null;
    setUncertain(false);
    setReviewed(false);
    if (!preselectedInvoiceId || !invoiceMap.has(preselectedInvoiceId)) {
      setRows([EMPTY_ROW]);
      return;
    }
    const invoice = invoiceMap.get(preselectedInvoiceId)!;
    const supplier = supplierMap.get(invoice.supplier_id);
    setRows([{
      invoice_id: invoice.id,
      allocated_amount: round2(Number(invoice.remaining_amount)),
      wht_base_amount: "",
      wht_rate: "0.00",
      wht_type: ""
    }]);
    setBankAccount(supplier?.bank_account ?? "");
  }, [invoiceMap, open, preselectedInvoiceId, supplierMap, invoicesQuery.isSuccess, suppliersQuery.isSuccess]);

  useEffect(() => { setReviewed(false); }, [rows, branchId, companyId, paymentDate, paymentMethod]);

  const request = useMemo(() => ({
    idempotency_key: requestKey,
    branch_id: branchId, payment_date: paymentDate, payment_method: paymentMethod,
    wht_reviewed: true,
    allocations: rows.filter((row) => row.invoice_id).map((row) => ({
      invoice_id: row.invoice_id, allocated_amount: Number(row.allocated_amount),
      wht_rate: Number(row.wht_rate), wht_type: row.wht_type.trim(),
      wht_base_amount: row.wht_base_amount === "" ? null : Number(row.wht_base_amount)
    }))
  }), [requestKey, branchId, paymentDate, paymentMethod, rows]);
  const canPreview = Boolean(open && branchId && paymentDate && request.allocations.length
    && request.allocations.every((row) => row.allocated_amount > 0 && row.wht_type && Number.isFinite(row.wht_rate)));
  const previewQuery = useQuery({
    queryKey: ["payable", "payment-preview", companyId, request],
    queryFn: async () => (await payableApi.previewPayment(request)).data.data as {
      allocations: Array<{ invoice_id: string; wht_amount: number; wht_base_amount: number; vat_exclusive_amount: number; net_amount: number }>;
      total_allocated: number; total_wht: number; net_amount: number;
    },
    enabled: canPreview, retry: false, refetchOnWindowFocus: false
  });
  const preview = canPreview && !previewQuery.isFetching && !previewQuery.isError ? previewQuery.data : undefined;

  const totals = useMemo(() => {
    return { totalAllocated: Number(preview?.total_allocated ?? 0), totalWht: Number(preview?.total_wht ?? 0), netPaid: Number(preview?.net_amount ?? 0) };
  }, [preview]);

  function updateRow(index: number, patch: Partial<RowState>): void {
    setRows((prev) => prev.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)));
  }

  function createRowForInvoice(invoice: SupplierInvoice): RowState {
    return {
      invoice_id: invoice.id,
      allocated_amount: round2(Number(invoice.remaining_amount)),
      wht_base_amount: "",
      wht_rate: "0.00",
      wht_type: ""
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
    if (submitting.current || (!uncertain && (!preview || !reviewed))) return;
    if (!branchId) {
      toast({ title: "ไม่พบสาขาปัจจุบัน", variant: "destructive" });
      return;
    }
    const validRows = rows.filter((item) => item.invoice_id);
    if (!validRows.length) {
      toast({ title: "เลือกใบแจ้งหนี้อย่างน้อย 1 ใบ", variant: "destructive" });
      return;
    }
    submitting.current = true;
    setSaving(true);
    try {
      const payload = retryPayload.current ?? {
        ...request,
        bank_account: bankAccount || null,
        reference_no: referenceNo || null,
        allocations: request.allocations.map((item) => ({ ...item,
          wht_amount: preview!.allocations.find((row) => row.invoice_id === item.invoice_id)!.wht_amount,
          wht_base_amount: preview!.allocations.find((row) => row.invoice_id === item.invoice_id)!.wht_base_amount
        })),
        note: note || null
      };
      retryPayload.current = payload;
      const response = await payableApi.createPayment(payload);
      toast({ title: `บันทึกการจ่ายแล้ว: ${response.data.data.payment_number}` });
      if (totals.totalWht > 0) {
        toast({ title: "ออกใบรับรอง WHT อัตโนมัติ" });
      }
      onOpenChange(false);
      await onSuccess();
    } catch (error) {
      setReviewed(false);
      const httpStatus = (error as { response?: { status?: number } })?.response?.status;
      if (httpStatus && httpStatus >= 400 && httpStatus < 500) {
        retryPayload.current = null;
        setUncertain(false);
        setRequestKey(crypto.randomUUID());
        await previewQuery.refetch();
      } else {
        setUncertain(true);
      }
      toast({
        title: "บันทึกการจ่ายไม่สำเร็จ",
        description: httpStatus && httpStatus < 500 ? paymentError(error) : "ยังยืนยันผลไม่ได้ ให้ตรวจผลคำขอเดิมก่อน ห้ามสร้างรายการใหม่ซ้ำ",
        variant: "destructive"
      });
    } finally {
      submitting.current = false;
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-6xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>บันทึกการจ่าย</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-slate-600">ยอดตัดหนี้รวม VAT แต่ฐาน WHT ไม่รวม VAT ระบบคำนวณตามสัดส่วนเมื่อจ่ายบางส่วน ระบุอัตราและประเภทเงินได้เอง ไม่ใช้ค่าผู้จำหน่ายโดยอัตโนมัติ หากมีหลายประเภทเงินได้/หลายอัตรา ให้แยกใบแจ้งหนี้</p>
        {rows.some((row) => Number(invoiceMap.get(row.invoice_id)?.wht_amount ?? 0) > 0) && <p role="alert" className="text-red-700">ใบแจ้งหนี้เดิมหัก WHT ตอนตั้งหนี้แล้ว ต้องให้บัญชีตรวจทานก่อนจ่ายต่อ ไม่หักซ้ำอัตโนมัติ</p>}

        <fieldset disabled={saving || uncertain} className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div className="min-w-0 space-y-4">
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
                    <TableHead className="text-right">ยอดตัดหนี้</TableHead>
                    <TableHead className="text-right">ฐาน WHT ไม่รวม VAT</TableHead>
                    <TableHead className="text-right">WHT</TableHead>
                    <TableHead className="text-right">WHT%</TableHead>
                    <TableHead>ประเภทเงินได้ / เหตุผลไม่หัก</TableHead>
                    <TableHead className="text-right">จ่ายสุทธิ</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row, index) => {
                    const invoice = invoiceMap.get(row.invoice_id);
                    const options = invoice ? [invoice, ...availableInvoices] : availableInvoices;
                    const calculated = preview?.allocations.find((item) => item.invoice_id === row.invoice_id);
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
                        <TableCell><Input aria-label={`ยอดตัดหนี้ ${index + 1}`} type="number" min="0.01" step="0.01" value={row.allocated_amount} onChange={(event) => updateRow(index, { allocated_amount: event.target.value, wht_base_amount: "" })} /></TableCell>
                        <TableCell><Input aria-label={`ฐาน WHT ${index + 1}`} type="number" min="0" step="0.01" placeholder={calculated ? String(calculated.wht_base_amount) : "อัตโนมัติ"} value={row.wht_base_amount} onChange={(event) => updateRow(index, { wht_base_amount: event.target.value })} /></TableCell>
                        <TableCell>{calculated ? Number(calculated.wht_amount).toFixed(2) : "—"}</TableCell>
                        <TableCell><Input aria-label={`อัตรา WHT ${index + 1}`} type="number" min="0" max="100" step="0.01" value={row.wht_rate} onChange={(event) => updateRow(index, { wht_rate: event.target.value, wht_base_amount: "" })} /></TableCell>
                        <TableCell><Input aria-label={`ประเภทเงินได้ ${index + 1}`} maxLength={50} value={row.wht_type} onChange={(event) => updateRow(index, { wht_type: event.target.value })} /></TableCell>
                        <TableCell className="text-right font-medium text-blue-700">{calculated ? Number(calculated.net_amount).toFixed(2) : "—"}</TableCell>
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
              <div className="flex items-center justify-between"><span>รวมยอดตัดหนี้</span><strong>{totals.totalAllocated.toLocaleString("th-TH", { minimumFractionDigits: 2 })}</strong></div>
              <div className="flex items-center justify-between"><span>รวม WHT หัก</span><strong>{totals.totalWht.toLocaleString("th-TH", { minimumFractionDigits: 2 })}</strong></div>
              <div className="flex items-center justify-between border-t border-blue-200 pt-3 text-base text-blue-900"><span>จ่ายสุทธิ</span><strong>{preview ? totals.netPaid.toLocaleString("th-TH", { minimumFractionDigits: 2 }) : "รอตรวจยอด"}</strong></div>
            </div>
          </div>
        </fieldset>
        {previewQuery.isFetching && <p role="status">กำลังตรวจยอดกับระบบ…</p>}
        {previewQuery.isError && <p role="alert" className="text-red-700">{paymentError(previewQuery.error)}</p>}
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={reviewed} disabled={!preview || saving} onChange={(event) => setReviewed(event.target.checked)} />ยืนยันประเภทเงินได้ อัตรา ฐานภาษี และยอดจ่ายสุทธิแล้ว</label>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>ยกเลิก</Button>
          <Button disabled={saving || (!uncertain && (!preview || !reviewed))} onClick={() => void submit()}>{saving ? "กำลังบันทึก…" : uncertain ? "ตรวจผลคำขอเดิม (ไม่จ่ายซ้ำ)" : "บันทึกการจ่าย"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function paymentError(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : "ตรวจยอดไม่สำเร็จ กรุณาตรวจจำนวนเงิน อัตรา และประเภทเงินได้ แล้วลองใหม่";
}
