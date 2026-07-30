import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import { crmApi } from "@/lib/crmApi";
import type { Customer, CustomerPurchaseHistory, CustomerTag, PointsTransaction } from "@/types/crm";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customerId: string | null;
  tags: CustomerTag[];
};

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(value || 0);
}

export default function CustomerProfileDialog({ open, onOpenChange, customerId, tags }: Props): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const customerQuery = useQuery({
    queryKey: ["crm", "customer", customerId],
    queryFn: async () => (await crmApi.getCustomer(customerId!)).data.data as Customer,
    enabled: open && Boolean(customerId)
  });
  const purchaseHistoryQuery = useQuery({
    queryKey: ["crm", "customer-history", customerId],
    queryFn: async () => (await crmApi.getPurchaseHistory(customerId!)).data.data as CustomerPurchaseHistory,
    enabled: open && Boolean(customerId)
  });
  const pointsQuery = useQuery({
    queryKey: ["crm", "customer-points", customerId],
    queryFn: async () => (await crmApi.getPointsHistory(customerId!, { page: 1, limit: 20 })).data.data as PointsTransaction[],
    enabled: open && Boolean(customerId)
  });

  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    display_name: "",
    phone: "",
    email: "",
    tax_id: "",
    date_of_birth: "",
    gender: "",
    address: "",
    note: "",
    tag_ids: [] as string[]
  });

  useEffect(() => {
    if (customerQuery.data) {
      const customer = customerQuery.data;
      setForm({
        first_name: customer.first_name || "",
        last_name: customer.last_name || "",
        display_name: customer.display_name || "",
        phone: customer.phone || "",
        email: customer.email || "",
        tax_id: customer.tax_id || "",
        date_of_birth: customer.date_of_birth || "",
        gender: customer.gender || "",
        address: customer.address || "",
        note: customer.note || "",
        tag_ids: customer.tags.map((tag) => tag.id)
      });
    }
  }, [customerQuery.data]);

  const updateMutation = useMutation({
    mutationFn: async () => crmApi.updateCustomer(customerId!, {
      ...form,
      first_name: form.first_name || null,
      last_name: form.last_name || null,
      display_name: form.display_name || null,
      phone: form.phone || null,
      email: form.email || null,
      tax_id: form.tax_id || null,
      date_of_birth: form.date_of_birth || null,
      gender: form.gender || null,
      address: form.address || null,
      note: form.note || null
    }),
    onSuccess: async () => {
      toast({ title: "บันทึกข้อมูลสมาชิกแล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["crm"] });
    },
    onError: (error: Error) => {
      toast({ title: "บันทึกไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const customer = customerQuery.data;
  const history = purchaseHistoryQuery.data;
  const points = pointsQuery.data ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>โปรไฟล์สมาชิก</DialogTitle>
        </DialogHeader>
        {customer ? (
          <Tabs defaultValue="info">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="info">ข้อมูลสมาชิก</TabsTrigger>
              <TabsTrigger value="orders">ประวัติการซื้อ</TabsTrigger>
              <TabsTrigger value="points">ประวัติแต้ม</TabsTrigger>
            </TabsList>
            <TabsContent value="info" className="grid gap-4 lg:grid-cols-[320px,1fr]">
              <div className="space-y-4 rounded-xl border bg-slate-50 p-4">
                <div className="flex h-24 w-24 items-center justify-center rounded-full bg-slate-200 text-2xl font-semibold">
                  {(customer.display_name || customer.first_name || customer.customer_code).slice(0, 1)}
                </div>
                <div>
                  <div className="text-lg font-semibold">{customer.display_name || [customer.first_name, customer.last_name].filter(Boolean).join(" ")}</div>
                  <div className="text-sm text-slate-500">{customer.customer_code}</div>
                </div>
                <div className="inline-flex rounded-full px-3 py-1 text-sm font-medium" style={{ backgroundColor: `${customer.tier?.color ?? "#e2e8f0"}22`, color: customer.tier?.color ?? "#334155" }}>
                  {customer.tier?.name_th ?? customer.tier?.name ?? "No Tier"}
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2"><Label>ชื่อ</Label><Input value={form.first_name} onChange={(event) => setForm((prev) => ({ ...prev, first_name: event.target.value }))} /></div>
                <div className="space-y-2"><Label>นามสกุล</Label><Input value={form.last_name} onChange={(event) => setForm((prev) => ({ ...prev, last_name: event.target.value }))} /></div>
                <div className="space-y-2 md:col-span-2"><Label>ชื่อแสดงผล</Label><Input value={form.display_name} onChange={(event) => setForm((prev) => ({ ...prev, display_name: event.target.value }))} /></div>
                <div className="space-y-2"><Label>เบอร์โทร</Label><Input value={form.phone} onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))} /></div>
                <div className="space-y-2"><Label>อีเมล</Label><Input value={form.email} onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))} /></div>
                <div className="space-y-2"><Label>เลขผู้เสียภาษี</Label><Input value={form.tax_id} onChange={(event) => setForm((prev) => ({ ...prev, tax_id: event.target.value }))} /></div>
                <div className="space-y-2"><Label>วันเกิด</Label><Input type="date" value={form.date_of_birth} onChange={(event) => setForm((prev) => ({ ...prev, date_of_birth: event.target.value }))} /></div>
                <div className="space-y-2"><Label>เพศ</Label><Input value={form.gender} onChange={(event) => setForm((prev) => ({ ...prev, gender: event.target.value }))} /></div>
                <div className="space-y-2 md:col-span-2"><Label>ที่อยู่</Label><textarea className="min-h-[90px] w-full rounded-md border border-gray-300 px-3 py-2" value={form.address} onChange={(event) => setForm((prev) => ({ ...prev, address: event.target.value }))} /></div>
                <div className="space-y-2 md:col-span-2"><Label>Tags</Label><select multiple className="min-h-[120px] w-full rounded-md border border-gray-300 px-3 py-2" value={form.tag_ids} onChange={(event) => setForm((prev) => ({ ...prev, tag_ids: Array.from(event.target.selectedOptions).map((option) => option.value) }))}>
                  {tags.map((tag) => <option key={tag.id} value={tag.id}>{tag.name}</option>)}
                </select></div>
                <div className="space-y-2 md:col-span-2"><Label>หมายเหตุ</Label><textarea className="min-h-[90px] w-full rounded-md border border-gray-300 px-3 py-2" value={form.note} onChange={(event) => setForm((prev) => ({ ...prev, note: event.target.value }))} /></div>
              </div>
            </TabsContent>
            <TabsContent value="orders" className="space-y-4">
              <div className="grid gap-3 md:grid-cols-5">
                <div className="rounded-lg border p-3">จำนวนออเดอร์: {history?.total_orders ?? 0}</div>
                <div className="rounded-lg border p-3">ยอดรวม: {formatCurrency(history?.total_spend ?? 0)}</div>
                <div className="rounded-lg border p-3">เฉลี่ย/ครั้ง: {formatCurrency(history?.avg_order_value ?? 0)}</div>
                <div className="rounded-lg border p-3">ซื้อแรก: {history?.first_purchase_at ? new Date(history.first_purchase_at).toLocaleDateString("th-TH") : "-"}</div>
                <div className="rounded-lg border p-3">ซื้อล่าสุด: {history?.last_purchase_at ? new Date(history.last_purchase_at).toLocaleDateString("th-TH") : "-"}</div>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>วันที่</TableHead>
                    <TableHead>ยอด</TableHead>
                    <TableHead>Order</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(history?.recent_orders ?? []).map((order) => (
                    <TableRow key={order.id}>
                      <TableCell>{new Date(order.created_at).toLocaleDateString("th-TH")}</TableCell>
                      <TableCell>{formatCurrency(order.total_amount)}</TableCell>
                      <TableCell>{order.id}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TabsContent>
            <TabsContent value="points">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>วันที่</TableHead>
                    <TableHead>ประเภท</TableHead>
                    <TableHead>แต้ม</TableHead>
                    <TableHead>ยอดซื้อ</TableHead>
                    <TableHead>คงเหลือ</TableHead>
                    <TableHead>หมายเหตุ</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {points.map((tx) => (
                    <TableRow key={tx.id}>
                      <TableCell>{new Date(tx.created_at).toLocaleString("th-TH")}</TableCell>
                      <TableCell>{tx.transaction_type}</TableCell>
                      <TableCell>{tx.points}</TableCell>
                      <TableCell>{tx.spend_amount ?? tx.redeem_amount ?? "-"}</TableCell>
                      <TableCell>{tx.balance_after}</TableCell>
                      <TableCell>{tx.note || "-"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TabsContent>
          </Tabs>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>ปิด</Button>
          <Button onClick={() => updateMutation.mutate()} disabled={updateMutation.isPending || !customerId}>บันทึก</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
