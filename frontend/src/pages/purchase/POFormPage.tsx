import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileDown, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { authApi, systemApi } from "@/lib/api";
import { formatThaiCurrency, formatThaiDate } from "@/lib/cartUtils";
import { grApi, poApi, supplierApi } from "@/lib/purchaseApi";
import { productApi } from "@/lib/productApi";
import type { ApiResponse } from "@/types/api";
import type { GoodsReceipt, PurchaseOrder, Supplier } from "@/types/purchase";
import type { Product, ProductListItem } from "@/types/product";
import type { Branch, UserBranch } from "@/types/user";
import { usePermission } from "@/hooks/usePermission";
import ReceiveGoodsDialog from "@/pages/purchase/ReceiveGoodsDialog";

type DraftItem = {
  id?: string;
  product_id: string;
  variant_id: string;
  qty_ordered: number;
  unit_cost: number;
  discount_amount: number;
  vat_type: string;
  vat_rate: number;
};

type FormValues = {
  supplier_id: string;
  branch_id: string;
  order_date: string;
  expected_date: string;
  vat_type: string;
  note: string;
  internal_note: string;
};

function todayString(): string {
  return new Date().toISOString().slice(0, 10);
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function calcVat(subtotal: number, vatType: string, vatRate: number): number {
  if (vatType === "included") {
    return subtotal * vatRate / (100 + vatRate);
  }
  if (vatType === "excluded") {
    return subtotal * vatRate / 100;
  }
  return 0;
}

function calcLineSubtotal(item: DraftItem): number {
  return item.qty_ordered * item.unit_cost - item.discount_amount;
}

export default function POFormPage(): JSX.Element {
  const navigate = useNavigate();
  const { id } = useParams();
  const isEditMode = Boolean(id);
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const canApprove = usePermission("inventory.purchase.approve");
  const [form, setForm] = useState<FormValues>({
    supplier_id: "",
    branch_id: "",
    order_date: todayString(),
    expected_date: "",
    vat_type: "excluded",
    note: "",
    internal_note: ""
  });
  const [items, setItems] = useState<DraftItem[]>([
    { product_id: "", variant_id: "", qty_ordered: 1, unit_cost: 0, discount_amount: 0, vat_type: "excluded", vat_rate: 7 }
  ]);
  const [receiveOpen, setReceiveOpen] = useState(false);

  const suppliersQuery = useQuery({
    queryKey: ["purchase", "suppliers", "po-form"],
    queryFn: async () => {
      const response = await supplierApi.list({ page: 1, limit: 100 });
      return response.data as ApiResponse<Supplier[]>;
    }
  });

  const branchesQuery = useQuery({
    queryKey: ["purchase", "branches", "po-form"],
    queryFn: async () => {
      try {
        const response = await systemApi.branches();
        return response.data as ApiResponse<Branch[]>;
      } catch {
        const fallback = await authApi.myBranches();
        return {
          data: fallback.data.data.map((item: UserBranch) => ({
            id: item.branch_id,
            company_id: "",
            code: item.branch_name,
            name: item.branch_name,
            name_en: null,
            is_warehouse: false,
            is_active: true,
            sort_order: 0
          })),
          meta: fallback.data.meta,
          error: fallback.data.error
        } satisfies ApiResponse<Branch[]>;
      }
    }
  });

  const productsQuery = useQuery({
    queryKey: ["catalog", "products", "purchase-form"],
    queryFn: async () => {
      const response = await productApi.list({ page: 1, limit: 100 });
      return (response.data as ApiResponse<ProductListItem[]>).data;
    }
  });

  const productDetailsQuery = useQuery({
    queryKey: ["catalog", "products", "purchase-details"],
    queryFn: async () => {
      const entries = productsQuery.data ?? [];
      const responses = await Promise.all(entries.map((product) => productApi.get(product.id)));
      return responses.map((response) => (response.data as ApiResponse<Product>).data);
    },
    enabled: Boolean(productsQuery.data?.length)
  });

  const poQuery = useQuery({
    queryKey: ["purchase", "order", id],
    enabled: isEditMode,
    queryFn: async () => {
      const response = await poApi.get(id as string);
      return response.data as ApiResponse<PurchaseOrder>;
    }
  });

  const receiptsQuery = useQuery({
    queryKey: ["purchase", "receipts", id],
    enabled: isEditMode,
    queryFn: async () => {
      const response = await grApi.listByPO(id as string);
      return response.data as ApiResponse<GoodsReceipt[]>;
    }
  });

  useEffect(() => {
    const branches = branchesQuery.data?.data ?? [];
    if (!form.branch_id && branches.length === 1) {
      setForm((prev) => ({ ...prev, branch_id: branches[0].id }));
    }
  }, [branchesQuery.data?.data, form.branch_id]);

  useEffect(() => {
    const po = poQuery.data?.data;
    if (!po) {
      return;
    }
    setForm({
      supplier_id: po.supplier_id,
      branch_id: po.branch_id,
      order_date: po.order_date,
      expected_date: po.expected_date ?? "",
      vat_type: po.vat_type,
      note: po.note ?? "",
      internal_note: po.supplier.note ?? ""
    });
    setItems(
      po.items.map((item) => ({
        id: item.id,
        product_id: item.product_id,
        variant_id: item.variant_id ?? "",
        qty_ordered: Number(item.qty_ordered),
        unit_cost: Number(item.unit_cost),
        discount_amount: Number(item.discount_amount),
        vat_type: item.vat_type,
        vat_rate: Number(item.vat_rate)
      }))
    );
  }, [poQuery.data?.data]);

  const selectedSupplier = useMemo(
    () => (suppliersQuery.data?.data ?? []).find((supplier) => supplier.id === form.supplier_id) ?? null,
    [form.supplier_id, suppliersQuery.data?.data]
  );
  const currentPO = poQuery.data?.data ?? null;
  const receipts = receiptsQuery.data?.data ?? [];
  const productOptions = productsQuery.data ?? [];
  const productMap = new Map((productDetailsQuery.data ?? []).map((product) => [product.id, product]));
  const isReadOnly = currentPO ? ["fully_received", "cancelled"].includes(currentPO.status) : false;

  const summary = useMemo(() => {
    const subtotal = items.reduce((sum, item) => sum + calcLineSubtotal(item), 0);
    const vatAmount = items.reduce((sum, item) => sum + calcVat(calcLineSubtotal(item), item.vat_type, item.vat_rate), 0);
    const whtRate = Number(selectedSupplier?.wht_rate ?? 0);
    const whtAmount = subtotal * whtRate / 100;
    const totalAmount = subtotal + (form.vat_type === "excluded" ? vatAmount : 0) - whtAmount;
    return { subtotal, vatAmount, whtAmount, totalAmount };
  }, [form.vat_type, items, selectedSupplier?.wht_rate]);

  function updateForm<K extends keyof FormValues>(field: K, value: FormValues[K]): void {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function updateItem(index: number, field: keyof DraftItem, value: string | number): void {
    setItems((prev) => prev.map((item, idx) => (idx === index ? { ...item, [field]: value } : item)));
  }

  function addItem(): void {
    setItems((prev) => [
      ...prev,
      { product_id: "", variant_id: "", qty_ordered: 1, unit_cost: 0, discount_amount: 0, vat_type: form.vat_type, vat_rate: 7 }
    ]);
  }

  function removeItem(index: number): void {
    setItems((prev) => prev.filter((_, idx) => idx !== index));
  }

  async function saveOrder(): Promise<PurchaseOrder | null> {
    if (!form.supplier_id || !form.branch_id || items.length === 0 || items.some((item) => !item.product_id)) {
      toast({ title: "กรอกข้อมูล PO ไม่ครบ", variant: "destructive" });
      return null;
    }

    const payload = {
      supplier_id: form.supplier_id,
      branch_id: form.branch_id,
      order_date: form.order_date || undefined,
      expected_date: form.expected_date || undefined,
      vat_type: form.vat_type,
      note: form.note || undefined,
      internal_note: form.internal_note || undefined,
      items: items.map((item) => ({
        product_id: item.product_id,
        variant_id: item.variant_id || null,
        qty_ordered: item.qty_ordered,
        unit_cost: item.unit_cost,
        discount_amount: item.discount_amount,
        vat_type: item.vat_type,
        vat_rate: item.vat_rate
      }))
    };

    try {
      const response = isEditMode && id
        ? await poApi.update(id, payload)
        : await poApi.create(payload);
      const po = (response.data as ApiResponse<PurchaseOrder>).data;
      await queryClient.invalidateQueries({ queryKey: ["purchase"] });
      if (!isEditMode) {
        navigate(`/purchase/orders/${po.id}`, { replace: true });
      }
      toast({ title: "บันทึก PO เรียบร้อยแล้ว" });
      return po;
    } catch (error) {
      toast({
        title: "บันทึก PO ไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
      return null;
    }
  }

  async function submitForApproval(): Promise<void> {
    const po = currentPO ?? await saveOrder();
    if (!po) {
      return;
    }
    try {
      await poApi.submit(po.id);
      toast({ title: "ส่งอนุมัติแล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["purchase"] });
    } catch (error) {
      toast({
        title: "ส่งอนุมัติไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  async function approveOrder(): Promise<void> {
    if (!currentPO) {
      return;
    }
    try {
      await poApi.approve(currentPO.id, "อนุมัติจากหน้า PO");
      toast({ title: "อนุมัติ PO แล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["purchase"] });
    } catch (error) {
      toast({
        title: "อนุมัติไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  async function cancelOrder(): Promise<void> {
    const reason = window.prompt("ระบุเหตุผลในการยกเลิก PO");
    if (!reason || !currentPO) {
      return;
    }
    try {
      await poApi.cancel(currentPO.id, reason);
      toast({ title: "ยกเลิก PO แล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["purchase"] });
    } catch (error) {
      toast({
        title: "ยกเลิกไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  async function downloadPdf(): Promise<void> {
    if (!currentPO) {
      return;
    }
    try {
      const response = await poApi.pdf(currentPO.id);
      const contentType = String(response.headers["content-type"] ?? "");
      const isPdf = contentType.includes("pdf");
      downloadBlob(response.data as Blob, `${currentPO.po_number}.${isPdf ? "pdf" : "html"}`);
    } catch (error) {
      toast({
        title: "ดาวน์โหลดไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        title={currentPO?.po_number ?? "สร้าง PO ใหม่"}
        subtitle="จัดการใบสั่งซื้อและการรับสินค้า"
        actions={
          <div className="flex flex-wrap gap-2">
            {currentPO ? (
              <Badge variant="secondary">{currentPO.status}</Badge>
            ) : null}
            {currentPO ? (
              <Button variant="outline" onClick={() => void downloadPdf()}>
                <FileDown className="h-4 w-4" />
                PDF
              </Button>
            ) : null}
            {!isReadOnly && (currentPO?.status === "draft" || !currentPO) ? (
              <Button variant="outline" onClick={() => void saveOrder()}>
                บันทึก
              </Button>
            ) : null}
            {!isReadOnly && (currentPO?.status === "draft" || !currentPO) ? (
              <Button onClick={() => void submitForApproval()}>ส่งอนุมัติ</Button>
            ) : null}
            {currentPO?.status === "pending_approval" && canApprove ? (
              <Button onClick={() => void approveOrder()}>อนุมัติ</Button>
            ) : null}
            {(currentPO?.status === "approved" || currentPO?.status === "partially_received") ? (
              <Button onClick={() => setReceiveOpen(true)}>รับสินค้า</Button>
            ) : null}
            {currentPO && ["draft", "pending_approval", "approved"].includes(currentPO.status) ? (
              <Button variant="outline" onClick={() => void cancelOrder()}>
                ยกเลิก PO
              </Button>
            ) : null}
          </div>
        }
      />

      <Card>
        <CardHeader><CardTitle>ข้อมูล PO</CardTitle></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="grid gap-2">
            <label className="text-sm font-medium">ผู้จำหน่าย*</label>
            <select
              className="h-10 rounded-md border border-gray-300 px-3 text-sm"
              value={form.supplier_id}
              disabled={isReadOnly}
              onChange={(event) => updateForm("supplier_id", event.target.value)}
            >
              <option value="">เลือกผู้จำหน่าย</option>
              {(suppliersQuery.data?.data ?? []).map((supplier) => (
                <option key={supplier.id} value={supplier.id}>{supplier.name}</option>
              ))}
            </select>
          </div>
          <div className="grid gap-2">
            <label className="text-sm font-medium">สาขา*</label>
            <select
              className="h-10 rounded-md border border-gray-300 px-3 text-sm"
              value={form.branch_id}
              disabled={isReadOnly}
              onChange={(event) => updateForm("branch_id", event.target.value)}
            >
              <option value="">เลือกสาขา</option>
              {(branchesQuery.data?.data ?? []).map((branch) => (
                <option key={branch.id} value={branch.id}>{branch.name}</option>
              ))}
            </select>
          </div>
          <div className="grid gap-2">
            <label className="text-sm font-medium">วันที่สั่งซื้อ</label>
            <Input type="date" value={form.order_date} disabled={isReadOnly} onChange={(event) => updateForm("order_date", event.target.value)} />
          </div>
          <div className="grid gap-2">
            <label className="text-sm font-medium">วันที่ต้องการ</label>
            <Input type="date" value={form.expected_date} disabled={isReadOnly} onChange={(event) => updateForm("expected_date", event.target.value)} />
          </div>
          <div className="grid gap-2">
            <label className="text-sm font-medium">ประเภท VAT</label>
            <select
              className="h-10 rounded-md border border-gray-300 px-3 text-sm"
              value={form.vat_type}
              disabled={isReadOnly}
              onChange={(event) => updateForm("vat_type", event.target.value)}
            >
              <option value="excluded">excluded</option>
              <option value="included">included</option>
              <option value="exempt">exempt</option>
            </select>
          </div>
          <div className="grid gap-2 md:col-span-2">
            <label className="text-sm font-medium">หมายเหตุ</label>
            <textarea
              className="min-h-[88px] rounded-md border border-gray-300 px-3 py-2 text-sm"
              value={form.note}
              disabled={isReadOnly}
              onChange={(event) => updateForm("note", event.target.value)}
            />
          </div>
          <div className="grid gap-2 md:col-span-2">
            <label className="text-sm font-medium">หมายเหตุภายใน</label>
            <textarea
              className="min-h-[88px] rounded-md border border-gray-300 px-3 py-2 text-sm"
              value={form.internal_note}
              disabled={isReadOnly}
              onChange={(event) => updateForm("internal_note", event.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>รายการสินค้า</CardTitle>
            {!isReadOnly ? (
              <Button variant="outline" size="sm" onClick={addItem}>
                <Plus className="h-4 w-4" />
                เพิ่มรายการ
              </Button>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {items.map((item, index) => {
            const selectedProduct = productMap.get(item.product_id);
            const lineSubtotal = calcLineSubtotal(item);
            return (
              <div key={`${item.id ?? "new"}-${index}`} className="grid gap-3 rounded-xl border border-gray-200 p-4 md:grid-cols-6">
                <select
                  className="h-10 rounded-md border border-gray-300 px-3 text-sm md:col-span-2"
                  value={item.product_id}
                  disabled={isReadOnly}
                  onChange={(event) => updateItem(index, "product_id", event.target.value)}
                >
                  <option value="">เลือกสินค้า</option>
                  {productOptions.map((product) => (
                    <option key={product.id} value={product.id}>
                      {product.name} ({product.sku})
                    </option>
                  ))}
                </select>
                <select
                  className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                  value={item.variant_id}
                  disabled={isReadOnly}
                  onChange={(event) => updateItem(index, "variant_id", event.target.value)}
                >
                  <option value="">สินค้าหลัก</option>
                  {(selectedProduct?.variants ?? []).map((variant) => (
                    <option key={variant.id} value={variant.id}>{variant.name}</option>
                  ))}
                </select>
                <Input type="number" step="0.0001" disabled={isReadOnly} value={item.qty_ordered} onChange={(event) => updateItem(index, "qty_ordered", Number(event.target.value))} />
                <Input type="number" step="0.0001" disabled={isReadOnly} value={item.unit_cost} onChange={(event) => updateItem(index, "unit_cost", Number(event.target.value))} />
                <div className="flex gap-2">
                  <Input type="number" step="0.0001" disabled={isReadOnly} value={item.discount_amount} onChange={(event) => updateItem(index, "discount_amount", Number(event.target.value))} />
                  {!isReadOnly ? (
                    <Button variant="outline" size="icon" onClick={() => removeItem(index)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  ) : null}
                </div>
                <div className="text-sm text-gray-600 md:col-span-6">
                  รวมรายการ: <span className="font-medium text-gray-900">{formatThaiCurrency(lineSubtotal)}</span>
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>สรุปยอด</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-right">
          <div>ยอดรวมก่อน VAT: {formatThaiCurrency(summary.subtotal)}</div>
          <div>VAT 7%: {formatThaiCurrency(summary.vatAmount)}</div>
          <div>WHT {selectedSupplier?.wht_rate ?? 0}%: - {formatThaiCurrency(summary.whtAmount)}</div>
          <div className="border-t pt-3 text-xl font-semibold text-blue-700">
            ยอดสุทธิ: {formatThaiCurrency(summary.totalAmount)}
          </div>
          {currentPO ? (
            <>
              <div>ชำระแล้ว: {formatThaiCurrency(Number(currentPO.paid_amount))}</div>
              <div>ยังค้างชำระ: {formatThaiCurrency(Number(currentPO.remaining_amount))}</div>
            </>
          ) : null}
        </CardContent>
      </Card>

      {currentPO ? (
        <Card>
          <CardHeader><CardTitle>ประวัติการรับสินค้า</CardTitle></CardHeader>
          <CardContent>
            {receipts.length > 0 ? (
              <div className="space-y-3">
                {receipts.map((receipt) => (
                  <div key={receipt.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-gray-200 p-3">
                    <div>
                      <p className="font-medium">{receipt.gr_number}</p>
                      <p className="text-sm text-gray-500">{formatThaiDate(`${receipt.received_date}T00:00:00`)}</p>
                    </div>
                    <div className="text-sm text-gray-600">{receipt.items.length} รายการ</div>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={() => navigate(`/purchase/orders/${currentPO.id}`)}>
                        ดูรายละเอียด
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-500">ยังไม่มีประวัติการรับสินค้า</p>
            )}
          </CardContent>
        </Card>
      ) : null}

      {currentPO ? (
        <ReceiveGoodsDialog
          open={receiveOpen}
          onOpenChange={setReceiveOpen}
          po={currentPO}
          onSuccess={() => {
            void queryClient.invalidateQueries({ queryKey: ["purchase"] });
          }}
        />
      ) : null}
    </div>
  );
}
