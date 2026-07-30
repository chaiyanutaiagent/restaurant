import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Truck, Undo2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { authApi, systemApi } from "@/lib/api";
import { formatThaiDate } from "@/lib/cartUtils";
import { productApi } from "@/lib/productApi";
import { stockApi } from "@/lib/stockApi";
import { transferApi } from "@/lib/transferApi";
import type { ApiResponse } from "@/types/api";
import type { Product, ProductListItem } from "@/types/product";
import type { StockBalance, StockLocation } from "@/types/stock";
import type { TransferOrder } from "@/types/transfer";
import type { Branch, UserBranch } from "@/types/user";
import { usePermission } from "@/hooks/usePermission";

type DraftItem = {
  id?: string;
  product_id: string;
  variant_id: string;
  qty_requested: number;
  qty_approved: number;
};

type FormValues = {
  from_branch_id: string;
  to_branch_id: string;
  from_location_id: string;
  to_location_id: string;
  expected_date: string;
  note: string;
};

function todayString(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function TOFormPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const isEditMode = Boolean(id);
  const canApprove = usePermission("inventory.transfer.approve");
  const [form, setForm] = useState<FormValues>({
    from_branch_id: searchParams.get("from_branch") ?? "",
    to_branch_id: "",
    from_location_id: "",
    to_location_id: "",
    expected_date: "",
    note: ""
  });
  const [items, setItems] = useState<DraftItem[]>([{ product_id: "", variant_id: "", qty_requested: 1, qty_approved: 1 }]);

  const branchesQuery = useQuery({
    queryKey: ["transfer", "branches", "form"],
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

  const locationsQuery = useQuery({
    queryKey: ["transfer", "locations", form.from_branch_id, form.to_branch_id],
    queryFn: async () => {
      const [fromResponse, toResponse] = await Promise.all([
        stockApi.listLocations(form.from_branch_id || undefined),
        stockApi.listLocations(form.to_branch_id || undefined)
      ]);
      return {
        from: (fromResponse.data as ApiResponse<StockLocation[]>).data,
        to: (toResponse.data as ApiResponse<StockLocation[]>).data
      };
    }
  });

  const productsQuery = useQuery({
    queryKey: ["transfer", "products"],
    queryFn: async () => {
      const response = await productApi.list({ page: 1, limit: 100 });
      return (response.data as ApiResponse<ProductListItem[]>).data;
    }
  });

  const productDetailsQuery = useQuery({
    queryKey: ["transfer", "product-details"],
    queryFn: async () => {
      const entries = productsQuery.data ?? [];
      const responses = await Promise.all(entries.map((product) => productApi.get(product.id)));
      return responses.map((response) => (response.data as ApiResponse<Product>).data);
    },
    enabled: Boolean(productsQuery.data?.length)
  });

  const transferQuery = useQuery({
    queryKey: ["transfer", "order", id],
    enabled: isEditMode,
    queryFn: async () => {
      const response = await transferApi.get(id as string);
      return response.data as ApiResponse<TransferOrder>;
    }
  });

  const sourceBalancesQuery = useQuery({
    queryKey: ["transfer", "source-balances", form.from_location_id],
    queryFn: async () => {
      const response = await stockApi.listBalances({ location_id: form.from_location_id || undefined });
      return response.data as ApiResponse<StockBalance[]>;
    },
    enabled: Boolean(form.from_location_id)
  });

  useEffect(() => {
    const order = transferQuery.data?.data;
    if (!order) return;
    setForm({
      from_branch_id: order.from_branch_id,
      to_branch_id: order.to_branch_id,
      from_location_id: order.from_location_id,
      to_location_id: order.to_location_id,
      expected_date: order.expected_date ?? "",
      note: order.note ?? ""
    });
    setItems(order.items.map((item) => ({
      id: item.id,
      product_id: item.product_id,
      variant_id: item.variant_id ?? "",
      qty_requested: Number(item.qty_requested),
      qty_approved: Number(item.qty_approved ?? item.qty_requested)
    })));
  }, [transferQuery.data?.data]);

  const order = transferQuery.data?.data ?? null;
  const productMap = new Map((productDetailsQuery.data ?? []).map((product) => [product.id, product]));
  const sourceBalances = sourceBalancesQuery.data?.data ?? [];
  const stockMap = new Map(sourceBalances.map((balance) => [`${balance.product_id}:${balance.variant_id ?? ""}`, balance]));
  const isReadOnly = order ? ["completed", "cancelled"].includes(order.status) : false;

  function updateForm<K extends keyof FormValues>(field: K, value: FormValues[K]): void {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function updateItem(index: number, field: keyof DraftItem, value: string | number): void {
    setItems((prev) => prev.map((item, idx) => (idx === index ? { ...item, [field]: value } : item)));
  }

  function addItem(): void {
    setItems((prev) => [...prev, { product_id: "", variant_id: "", qty_requested: 1, qty_approved: 1 }]);
  }

  function removeItem(index: number): void {
    setItems((prev) => prev.filter((_, idx) => idx !== index));
  }

  async function saveOrder(): Promise<TransferOrder | null> {
    if (!form.from_branch_id || !form.to_branch_id || !form.from_location_id || !form.to_location_id) {
      toast({ title: "กรอกข้อมูลการโอนไม่ครบ", variant: "destructive" });
      return null;
    }
    try {
      const response = await transferApi.create({
        from_branch_id: form.from_branch_id,
        to_branch_id: form.to_branch_id,
        from_location_id: form.from_location_id,
        to_location_id: form.to_location_id,
        expected_date: form.expected_date || undefined,
        note: form.note || undefined,
        items: items.map((item) => ({
          product_id: item.product_id,
          variant_id: item.variant_id || null,
          qty_requested: item.qty_requested
        }))
      });
      const created = (response.data as ApiResponse<TransferOrder>).data;
      toast({ title: "บันทึก TO เรียบร้อยแล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["transfer"] });
      navigate(`/transfer/orders/${created.id}`, { replace: true });
      return created;
    } catch (error) {
      toast({ title: "บันทึก TO ไม่สำเร็จ", description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง", variant: "destructive" });
      return null;
    }
  }

  async function submitOrder(): Promise<void> {
    const current = order ?? await saveOrder();
    if (!current) return;
    try {
      await transferApi.submit(current.id);
      toast({ title: "ส่งขออนุมัติแล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["transfer"] });
    } catch (error) {
      toast({ title: "ส่งอนุมัติไม่สำเร็จ", description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง", variant: "destructive" });
    }
  }

  async function approveOrder(): Promise<void> {
    if (!order) return;
    try {
      await transferApi.approve(order.id, {
        items: items.map((item) => ({ item_id: item.id, qty_approved: item.qty_approved })),
        note: "อนุมัติพร้อมปรับจำนวน"
      });
      toast({ title: "อนุมัติ TO แล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["transfer"] });
    } catch (error) {
      toast({ title: "อนุมัติไม่สำเร็จ", description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง", variant: "destructive" });
    }
  }

  async function shipOrder(): Promise<void> {
    if (!order) return;
    try {
      await transferApi.ship(order.id, "จัดส่งแล้ว");
      toast({ title: "บันทึกจัดส่งแล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["transfer"] });
    } catch (error) {
      toast({ title: "จัดส่งไม่สำเร็จ", description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง", variant: "destructive" });
    }
  }

  async function receiveOrder(): Promise<void> {
    if (!order) return;
    try {
      await transferApi.receive(order.id, {
        items: order.items.map((item) => ({ item_id: item.id, qty_received: item.qty_sent ?? 0 }))
      });
      toast({ title: "ยืนยันรับสินค้าแล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["transfer"] });
    } catch (error) {
      toast({ title: "ยืนยันรับไม่สำเร็จ", description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง", variant: "destructive" });
    }
  }

  async function cancelOrder(): Promise<void> {
    if (!order) return;
    const reason = window.prompt("ระบุเหตุผลในการยกเลิก");
    if (!reason) return;
    try {
      await transferApi.cancel(order.id, reason);
      toast({ title: "ยกเลิก TO แล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["transfer"] });
    } catch (error) {
      toast({ title: "ยกเลิกไม่สำเร็จ", description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง", variant: "destructive" });
    }
  }

  const timelineSteps = [
    { key: "draft", label: "Draft", timestamp: order?.created_at },
    { key: "pending_approval", label: "รออนุมัติ", timestamp: order?.status !== "draft" ? order?.updated_at ?? order?.created_at : null },
    { key: "approved", label: "อนุมัติ", timestamp: order?.approved_at },
    { key: "in_transit", label: "กำลังส่ง", timestamp: order?.shipped_at },
    { key: "completed", label: "รับแล้ว", timestamp: order?.completed_at }
  ];

  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        title={order?.to_number ?? "สร้าง TO ใหม่"}
        subtitle="จัดการการโอนย้ายสินค้าระหว่างสาขา"
        actions={
          <div className="flex flex-wrap gap-2">
            {order ? <Badge variant="secondary">{order.status}</Badge> : null}
            {!order ? <Button variant="outline" onClick={() => void saveOrder()}>บันทึก</Button> : null}
            {!order ? <Button onClick={() => void submitOrder()}>ส่งขออนุมัติ</Button> : null}
            {order?.status === "draft" ? (
              <>
                <Button variant="outline" onClick={() => void saveOrder()}>บันทึก</Button>
                <Button onClick={() => void submitOrder()}>ส่งขออนุมัติ</Button>
                <Button variant="outline" onClick={() => navigate("/transfer/orders")}>ยกเลิก</Button>
              </>
            ) : null}
            {order?.status === "pending_approval" && canApprove ? (
              <>
                <Button onClick={() => void approveOrder()}>อนุมัติพร้อมปรับจำนวน</Button>
                <Button variant="outline" onClick={() => void cancelOrder()}><Undo2 className="h-4 w-4" />ยกเลิก</Button>
              </>
            ) : null}
            {order?.status === "approved" ? (
              <Button onClick={() => void shipOrder()}><Truck className="h-4 w-4" />บันทึกจัดส่ง</Button>
            ) : null}
            {order && ["in_transit", "partially_received"].includes(order.status) ? (
              <Button onClick={() => void receiveOrder()}>ยืนยันรับสินค้าแล้ว</Button>
            ) : null}
          </div>
        }
      />

      <Card>
        <CardHeader><CardTitle>ข้อมูลการโอน</CardTitle></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="grid gap-2">
            <label className="text-sm font-medium">จากสาขา*</label>
            <select className="h-10 rounded-md border border-gray-300 px-3 text-sm" value={form.from_branch_id} disabled={Boolean(order)} onChange={(e) => updateForm("from_branch_id", e.target.value)}>
              <option value="">เลือกสาขา</option>
              {(branchesQuery.data?.data ?? []).map((branch) => (
                <option key={branch.id} value={branch.id}>{branch.name}</option>
              ))}
            </select>
          </div>
          <div className="grid gap-2">
            <label className="text-sm font-medium">ไปสาขา*</label>
            <select className="h-10 rounded-md border border-gray-300 px-3 text-sm" value={form.to_branch_id} disabled={Boolean(order)} onChange={(e) => updateForm("to_branch_id", e.target.value)}>
              <option value="">เลือกสาขา</option>
              {(branchesQuery.data?.data ?? []).filter((branch) => branch.id !== form.from_branch_id).map((branch) => (
                <option key={branch.id} value={branch.id}>{branch.name}</option>
              ))}
            </select>
          </div>
          <div className="grid gap-2">
            <label className="text-sm font-medium">จากคลัง*</label>
            <select className="h-10 rounded-md border border-gray-300 px-3 text-sm" value={form.from_location_id} disabled={Boolean(order)} onChange={(e) => updateForm("from_location_id", e.target.value)}>
              <option value="">เลือกคลัง</option>
              {(locationsQuery.data?.from ?? []).map((location) => (
                <option key={location.id} value={location.id}>{location.name}</option>
              ))}
            </select>
          </div>
          <div className="grid gap-2">
            <label className="text-sm font-medium">ไปคลัง*</label>
            <select className="h-10 rounded-md border border-gray-300 px-3 text-sm" value={form.to_location_id} disabled={Boolean(order)} onChange={(e) => updateForm("to_location_id", e.target.value)}>
              <option value="">เลือกคลัง</option>
              {(locationsQuery.data?.to ?? []).map((location) => (
                <option key={location.id} value={location.id}>{location.name}</option>
              ))}
            </select>
          </div>
          <div className="grid gap-2">
            <label className="text-sm font-medium">วันที่ขอโอน</label>
            <Input type="date" value={order?.request_date ?? todayString()} readOnly />
          </div>
          <div className="grid gap-2">
            <label className="text-sm font-medium">วันที่ต้องการ</label>
            <Input type="date" value={form.expected_date} disabled={isReadOnly || Boolean(order && order.status !== "draft")} onChange={(e) => updateForm("expected_date", e.target.value)} />
          </div>
          <div className="grid gap-2 md:col-span-2">
            <label className="text-sm font-medium">หมายเหตุ</label>
            <textarea className="min-h-[88px] rounded-md border border-gray-300 px-3 py-2 text-sm" value={form.note} disabled={isReadOnly} onChange={(e) => updateForm("note", e.target.value)} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>รายการสินค้า</CardTitle>
            {!order ? (
              <Button variant="outline" size="sm" onClick={addItem}>
                <Plus className="h-4 w-4" />
                เพิ่มสินค้า
              </Button>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {items.map((item, index) => {
            const product = productMap.get(item.product_id);
            const key = `${item.product_id}:${item.variant_id || ""}`;
            const balance = stockMap.get(key);
            const available = Number(balance?.qty_available ?? 0);
            const badgeClass = available > 10 ? "bg-green-100 text-green-700" : available > 0 ? "bg-orange-100 text-orange-700" : "bg-red-100 text-red-700";
            return (
              <div key={`${item.id ?? "new"}-${index}`} className="grid gap-3 rounded-xl border border-gray-200 p-4 md:grid-cols-6">
                <select className="h-10 rounded-md border border-gray-300 px-3 text-sm md:col-span-2" value={item.product_id} disabled={Boolean(order)} onChange={(e) => updateItem(index, "product_id", e.target.value)}>
                  <option value="">เลือกสินค้า</option>
                  {(productsQuery.data ?? []).map((productOption) => (
                    <option key={productOption.id} value={productOption.id}>{productOption.name} ({productOption.sku})</option>
                  ))}
                </select>
                <select className="h-10 rounded-md border border-gray-300 px-3 text-sm" value={item.variant_id} disabled={Boolean(order)} onChange={(e) => updateItem(index, "variant_id", e.target.value)}>
                  <option value="">สินค้าหลัก</option>
                  {(product?.variants ?? []).map((variant) => (
                    <option key={variant.id} value={variant.id}>{variant.name}</option>
                  ))}
                </select>
                <Input type="number" step="0.0001" value={item.qty_requested} disabled={Boolean(order && order.status !== "draft")} onChange={(e) => updateItem(index, "qty_requested", Number(e.target.value))} />
                {order?.status === "pending_approval" && canApprove ? (
                  <Input type="number" step="0.0001" value={item.qty_approved} onChange={(e) => updateItem(index, "qty_approved", Number(e.target.value))} />
                ) : (
                  <div className="flex items-center text-sm text-gray-600">
                    {order?.items[index] ? `ขอ ${order.items[index].qty_requested} | อนุมัติ ${order.items[index].qty_approved ?? "-"} | ส่ง ${order.items[index].qty_sent ?? "-"} | รับ ${order.items[index].qty_received ?? "-"} | ระหว่างทาง ${order.items[index].qty_in_transit ?? 0}` : null}
                  </div>
                )}
                <div className="flex items-center justify-between gap-2">
                  <Badge variant="secondary" className={badgeClass}>คงเหลือ {available}</Badge>
                  {!order ? (
                    <Button variant="outline" size="sm" onClick={() => removeItem(index)}>ลบ</Button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>

      {order ? (
        <Card>
          <CardHeader><CardTitle>Timeline</CardTitle></CardHeader>
          <CardContent>
            <div className="grid gap-3 md:grid-cols-5">
              {timelineSteps.map((step) => {
                const completed = ["draft", "pending_approval", "approved", "in_transit", "completed"].indexOf(order.status) >= ["draft", "pending_approval", "approved", "in_transit", "completed"].indexOf(step.key);
                return (
                  <div key={step.key} className={`rounded-xl border p-4 ${completed ? "border-blue-200 bg-blue-50" : "border-gray-200 bg-gray-50"}`}>
                    <p className="font-medium">{step.label}</p>
                    <p className="mt-2 text-xs text-gray-500">{step.timestamp ? formatThaiDate(step.timestamp) : "รอดำเนินการ"}</p>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
