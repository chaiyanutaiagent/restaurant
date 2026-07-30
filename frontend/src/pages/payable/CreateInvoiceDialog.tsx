import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { payableApi } from "@/lib/payableApi";
import { poApi, supplierApi } from "@/lib/purchaseApi";
import { useAuthStore } from "@/stores/auth.store";
import type { ApiResponse } from "@/types/api";
import type { PurchaseOrder, Supplier } from "@/types/purchase";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => Promise<void> | void;
};

type FormState = {
  supplier_id: string;
  po_id: string;
  supplier_ref: string;
  invoice_date: string;
  subtotal: string;
  vat_amount: string;
  wht_amount: string;
  note: string;
};

const EMPTY_FORM: FormState = {
  supplier_id: "",
  po_id: "",
  supplier_ref: "",
  invoice_date: new Date().toISOString().slice(0, 10),
  subtotal: "0.00",
  vat_amount: "0.00",
  wht_amount: "0.00",
  note: ""
};

function round2(value: number): string {
  return (Math.round((value + Number.EPSILON) * 100) / 100).toFixed(2);
}

function addDays(isoDate: string, days: number): string {
  const dt = new Date(`${isoDate}T00:00:00`);
  dt.setDate(dt.getDate() + days);
  return dt.toISOString().slice(0, 10);
}

export default function CreateInvoiceDialog({ open, onOpenChange, onSuccess }: Props): JSX.Element {
  const { toast } = useToast();
  const branchId = useAuthStore((state) => state.branchId);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);

  const suppliersQuery = useQuery({
    queryKey: ["purchase", "suppliers", "create-invoice"],
    queryFn: async () => (await supplierApi.list({ page: 1, limit: 200 })).data as ApiResponse<Supplier[]>,
    enabled: open
  });

  const supplier = useMemo(
    () => (suppliersQuery.data?.data ?? []).find((item) => item.id === form.supplier_id) ?? null,
    [form.supplier_id, suppliersQuery.data?.data]
  );

  const poListQuery = useQuery({
    queryKey: ["purchase", "orders", "create-invoice", form.supplier_id],
    queryFn: async () => (
      await poApi.list({ supplier_id: form.supplier_id, page: 1, limit: 200 })
    ).data as ApiResponse<Array<{ id: string; po_number: string; status: string }>>,
    enabled: open && Boolean(form.supplier_id)
  });

  const poOptions = useMemo(
    () => (poListQuery.data?.data ?? []).filter((item) => ["approved", "partially_received", "fully_received"].includes(item.status)),
    [poListQuery.data?.data]
  );

  const dueDate = useMemo(
    () => addDays(form.invoice_date, supplier?.payment_term_days ?? 0),
    [form.invoice_date, supplier?.payment_term_days]
  );
  const netAmount = useMemo(
    () => Number(form.subtotal || 0) + Number(form.vat_amount || 0) - Number(form.wht_amount || 0),
    [form.subtotal, form.vat_amount, form.wht_amount]
  );

  function updateField<K extends keyof FormState>(field: K, value: FormState[K]): void {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function handleSupplierChange(value: string): void {
    const nextSupplier = (suppliersQuery.data?.data ?? []).find((item) => item.id === value) ?? null;
    const subtotal = Number(form.subtotal || 0);
    setForm((prev) => ({
      ...prev,
      supplier_id: value,
      po_id: "",
      vat_amount: round2(subtotal * 0.07),
      wht_amount: round2(subtotal * Number(nextSupplier?.wht_rate ?? 0) / 100)
    }));
  }

  async function handlePoChange(value: string): Promise<void> {
    updateField("po_id", value);
    if (!value) {
      return;
    }
    try {
      const response = await poApi.get(value);
      const po = response.data.data as PurchaseOrder;
      setForm((prev) => ({
        ...prev,
        po_id: value,
        subtotal: round2(Number(po.subtotal)),
        vat_amount: round2(Number(po.vat_amount)),
        wht_amount: round2(Number(po.wht_amount))
      }));
    } catch (error) {
      toast({
        title: "โหลดข้อมูล PO ไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  async function submit(): Promise<void> {
    if (!branchId) {
      toast({ title: "ไม่พบสาขาปัจจุบัน", variant: "destructive" });
      return;
    }
    if (!form.supplier_id || !form.invoice_date) {
      toast({ title: "กรอกข้อมูลไม่ครบ", description: "กรุณาเลือกซัพพลายเออร์และวันที่ใบแจ้งหนี้", variant: "destructive" });
      return;
    }
    try {
      const response = await payableApi.createInvoice({
        supplier_id: form.supplier_id,
        branch_id: branchId,
        po_id: form.po_id || null,
        supplier_ref: form.supplier_ref || null,
        invoice_date: form.invoice_date,
        subtotal: Number(form.subtotal || 0),
        vat_amount: Number(form.vat_amount || 0),
        wht_amount: Number(form.wht_amount || 0),
        note: form.note || null
      });
      toast({ title: `สร้างใบแจ้งหนี้แล้ว: ${response.data.data.invoice_number}` });
      setForm(EMPTY_FORM);
      onOpenChange(false);
      await onSuccess();
    } catch (error) {
      toast({
        title: "สร้างใบแจ้งหนี้ไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>สร้างใบแจ้งหนี้</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label>ซัพพลายเออร์*</Label>
            <select className="h-10 w-full rounded-md border border-gray-300 px-3 text-sm" value={form.supplier_id} onChange={(event) => handleSupplierChange(event.target.value)}>
              <option value="">เลือกซัพพลายเออร์</option>
              {(suppliersQuery.data?.data ?? []).map((item) => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label>อ้างอิง PO</Label>
            <select className="h-10 w-full rounded-md border border-gray-300 px-3 text-sm" value={form.po_id} onChange={(event) => void handlePoChange(event.target.value)} disabled={!form.supplier_id}>
              <option value="">ไม่อ้างอิง</option>
              {poOptions.map((item) => (
                <option key={item.id} value={item.id}>{item.po_number}</option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label>เลขที่ใบแจ้งหนี้ซัพพลายเออร์</Label>
            <Input value={form.supplier_ref} onChange={(event) => updateField("supplier_ref", event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>วันที่ใบแจ้งหนี้*</Label>
            <Input type="date" value={form.invoice_date} onChange={(event) => updateField("invoice_date", event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>วันครบกำหนด</Label>
            <Input value={dueDate} readOnly />
          </div>
          <div className="space-y-2">
            <Label>Payment term / WHT</Label>
            <Input value={supplier ? `${supplier.payment_term_days} วัน | ${Number(supplier.wht_rate)}%` : "-"} readOnly />
          </div>
          <div className="space-y-2">
            <Label>ยอดรวมก่อน VAT*</Label>
            <Input type="number" value={form.subtotal} onChange={(event) => updateField("subtotal", event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>VAT (ภาษีซื้อ)</Label>
            <Input type="number" value={form.vat_amount} onChange={(event) => updateField("vat_amount", event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>WHT (หัก ณ ที่จ่าย)</Label>
            <Input type="number" value={form.wht_amount} onChange={(event) => updateField("wht_amount", event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>ยอดสุทธิ</Label>
            <Input value={round2(netAmount)} readOnly />
          </div>
        </div>

        <div className="space-y-2">
          <Label>หมายเหตุ</Label>
          <textarea className="min-h-[96px] w-full rounded-md border border-gray-300 px-3 py-2 text-sm" value={form.note} onChange={(event) => updateField("note", event.target.value)} />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>ยกเลิก</Button>
          <Button onClick={() => void submit()}>บันทึก</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
