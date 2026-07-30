import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import { usePermission } from "@/hooks/usePermission";
import { supplierApi } from "@/lib/purchaseApi";
import type { ApiResponse } from "@/types/api";
import type { Supplier } from "@/types/purchase";

type SupplierFormValues = {
  code: string;
  name: string;
  name_en: string;
  tax_id: string;
  branch_code: string;
  address: string;
  phone: string;
  email: string;
  contact_person: string;
  payment_term_days: number;
  wht_rate: number;
  wht_type: string;
  credit_limit: number;
  bank_name: string;
  bank_account: string;
  bank_account_name: string;
  note: string;
  is_active: boolean;
};

const EMPTY_FORM: SupplierFormValues = {
  code: "",
  name: "",
  name_en: "",
  tax_id: "",
  branch_code: "00000",
  address: "",
  phone: "",
  email: "",
  contact_person: "",
  payment_term_days: 30,
  wht_rate: 3,
  wht_type: "",
  credit_limit: 0,
  bank_name: "",
  bank_account: "",
  bank_account_name: "",
  note: "",
  is_active: true
};

function formatTaxId(taxId: string | null): string {
  if (!taxId) {
    return "-";
  }
  const digits = taxId.replace(/\D/g, "");
  if (digits.length !== 13) {
    return taxId;
  }
  return `${digits.slice(0, 1)}-${digits.slice(1, 5)}-${digits.slice(5, 10)}-${digits.slice(10, 12)}-${digits.slice(12)}`;
}

export default function SuppliersPage(): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const canManage = usePermission("inventory.purchase.create");
  const [search, setSearch] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Supplier | null>(null);
  const [form, setForm] = useState<SupplierFormValues>(EMPTY_FORM);

  const suppliersQuery = useQuery({
    queryKey: ["purchase", "suppliers", search],
    queryFn: async () => {
      const response = await supplierApi.list({ search: search || undefined, page: 1, limit: 100 });
      return response.data as ApiResponse<Supplier[]>;
    }
  });

  const rows = useMemo(() => suppliersQuery.data?.data ?? [], [suppliersQuery.data?.data]);

  function openCreate(): void {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  }

  function openEdit(supplier: Supplier): void {
    setEditing(supplier);
    setForm({
      code: supplier.code,
      name: supplier.name,
      name_en: supplier.name_en ?? "",
      tax_id: supplier.tax_id ?? "",
      branch_code: supplier.branch_code ?? "00000",
      address: supplier.address ?? "",
      phone: supplier.phone ?? "",
      email: supplier.email ?? "",
      contact_person: supplier.contact_person ?? "",
      payment_term_days: supplier.payment_term_days,
      wht_rate: Number(supplier.wht_rate),
      wht_type: supplier.wht_type ?? "",
      credit_limit: Number(supplier.credit_limit),
      bank_name: supplier.bank_name ?? "",
      bank_account: supplier.bank_account ?? "",
      bank_account_name: supplier.bank_account_name ?? "",
      note: supplier.note ?? "",
      is_active: supplier.is_active
    });
    setDialogOpen(true);
  }

  function updateField<K extends keyof SupplierFormValues>(field: K, value: SupplierFormValues[K]): void {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function saveSupplier(): Promise<void> {
    if (!form.code.trim() || !form.name.trim()) {
      toast({ title: "กรอกข้อมูลไม่ครบ", description: "กรุณาระบุรหัสและชื่อผู้จำหน่าย", variant: "destructive" });
      return;
    }
    const payload = {
      ...form,
      name_en: form.name_en || null,
      tax_id: form.tax_id || null,
      branch_code: form.branch_code || null,
      address: form.address || null,
      phone: form.phone || null,
      email: form.email || null,
      contact_person: form.contact_person || null,
      wht_type: form.wht_type || null,
      bank_name: form.bank_name || null,
      bank_account: form.bank_account || null,
      bank_account_name: form.bank_account_name || null,
      note: form.note || null
    };

    try {
      if (editing) {
        await supplierApi.update(editing.id, payload);
      } else {
        await supplierApi.create(payload);
      }
      toast({ title: editing ? "อัปเดตผู้จำหน่ายแล้ว" : "เพิ่มผู้จำหน่ายแล้ว" });
      setDialogOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["purchase", "suppliers"] });
    } catch (error) {
      toast({
        title: "บันทึกไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  async function deleteSupplier(id: string): Promise<void> {
    if (!window.confirm("ต้องการลบผู้จำหน่ายรายนี้ใช่หรือไม่")) {
      return;
    }
    try {
      await supplierApi.delete(id);
      toast({ title: "ลบผู้จำหน่ายแล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["purchase", "suppliers"] });
    } catch (error) {
      toast({
        title: "ลบไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  return (
    <div>
      <PageHeader
        title="ผู้จำหน่าย"
        subtitle="จัดการรายชื่อซัพพลายเออร์"
        actions={
          canManage ? (
            <Button onClick={openCreate}>
              <Plus className="h-4 w-4" />
              เพิ่มผู้จำหน่าย
            </Button>
          ) : null
        }
      />

      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="ค้นหาจากรหัส ชื่อ หรือเลขผู้เสียภาษี"
              className="md:max-w-sm"
            />
          </div>

          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>รหัส</TableHead>
                  <TableHead>ชื่อบริษัท</TableHead>
                  <TableHead>เลขผู้เสียภาษี</TableHead>
                  <TableHead>เบอร์โทร | อีเมล</TableHead>
                  <TableHead>เงื่อนไข</TableHead>
                  <TableHead>WHT</TableHead>
                  <TableHead>สถานะ</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((supplier) => (
                  <TableRow key={supplier.id}>
                    <TableCell>
                      <Badge variant="outline" className="font-mono">{supplier.code}</Badge>
                    </TableCell>
                    <TableCell>
                      <div className="font-medium text-gray-900">{supplier.name}</div>
                      <div className="text-xs text-gray-500">{supplier.name_en ?? "-"}</div>
                    </TableCell>
                    <TableCell>{formatTaxId(supplier.tax_id)}</TableCell>
                    <TableCell>
                      <div>{supplier.phone ?? "-"}</div>
                      <div className="text-xs text-gray-500">{supplier.email ?? "-"}</div>
                    </TableCell>
                    <TableCell>{supplier.payment_term_days} วัน</TableCell>
                    <TableCell>{Number(supplier.wht_rate)}%</TableCell>
                    <TableCell>
                      <Badge variant={supplier.is_active ? "default" : "secondary"}>
                        {supplier.is_active ? "active" : "inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-2">
                        {canManage ? (
                          <Button variant="outline" size="sm" onClick={() => openEdit(supplier)}>
                            <Pencil className="h-4 w-4" />
                            แก้ไข
                          </Button>
                        ) : null}
                        {canManage ? (
                          <Button variant="outline" size="sm" onClick={() => void deleteSupplier(supplier.id)}>
                            <Trash2 className="h-4 w-4" />
                            ลบ
                          </Button>
                        ) : null}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editing ? "แก้ไขผู้จำหน่าย" : "เพิ่มผู้จำหน่าย"}</DialogTitle>
          </DialogHeader>

          <Tabs defaultValue="general" className="space-y-4">
            <TabsList className="grid h-auto grid-cols-2 gap-2 md:grid-cols-4">
              <TabsTrigger value="general">ข้อมูลทั่วไป</TabsTrigger>
              <TabsTrigger value="contact">ที่อยู่และติดต่อ</TabsTrigger>
              <TabsTrigger value="finance">การเงิน</TabsTrigger>
              <TabsTrigger value="note">หมายเหตุ</TabsTrigger>
            </TabsList>

            <TabsContent value="general" className="grid gap-4 md:grid-cols-2">
              <div className="grid gap-2">
                <Label>รหัส*</Label>
                <Input value={form.code} onChange={(event) => updateField("code", event.target.value)} />
              </div>
              <div className="grid gap-2">
                <Label>ชื่อบริษัท*</Label>
                <Input value={form.name} onChange={(event) => updateField("name", event.target.value)} />
              </div>
              <div className="grid gap-2">
                <Label>ชื่อภาษาอังกฤษ</Label>
                <Input value={form.name_en} onChange={(event) => updateField("name_en", event.target.value)} />
              </div>
              <div className="grid gap-2">
                <Label>เลขผู้เสียภาษี</Label>
                <Input value={form.tax_id} onChange={(event) => updateField("tax_id", event.target.value)} />
              </div>
              <div className="grid gap-2">
                <Label>รหัสสาขา</Label>
                <Input value={form.branch_code} onChange={(event) => updateField("branch_code", event.target.value)} />
              </div>
              <label className="flex items-center gap-2 pt-8 text-sm">
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(event) => updateField("is_active", event.target.checked)}
                />
                ใช้งานอยู่
              </label>
            </TabsContent>

            <TabsContent value="contact" className="grid gap-4 md:grid-cols-2">
              <div className="grid gap-2 md:col-span-2">
                <Label>ที่อยู่</Label>
                <textarea
                  className="min-h-[96px] rounded-md border border-gray-300 px-3 py-2 text-sm"
                  value={form.address}
                  onChange={(event) => updateField("address", event.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label>เบอร์โทร</Label>
                <Input value={form.phone} onChange={(event) => updateField("phone", event.target.value)} />
              </div>
              <div className="grid gap-2">
                <Label>อีเมล</Label>
                <Input value={form.email} onChange={(event) => updateField("email", event.target.value)} />
              </div>
              <div className="grid gap-2">
                <Label>ผู้ติดต่อ</Label>
                <Input value={form.contact_person} onChange={(event) => updateField("contact_person", event.target.value)} />
              </div>
            </TabsContent>

            <TabsContent value="finance" className="grid gap-4 md:grid-cols-2">
              <div className="grid gap-2">
                <Label>เครดิตเทอม (วัน)</Label>
                <Input
                  type="number"
                  value={form.payment_term_days}
                  onChange={(event) => updateField("payment_term_days", Number(event.target.value))}
                />
              </div>
              <div className="grid gap-2">
                <Label>WHT</Label>
                <select
                  className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                  value={form.wht_rate}
                  onChange={(event) => updateField("wht_rate", Number(event.target.value))}
                >
                  <option value={1}>1%</option>
                  <option value={3}>3%</option>
                  <option value={5}>5%</option>
                </select>
              </div>
              <div className="grid gap-2">
                <Label>ประเภท WHT</Label>
                <Input value={form.wht_type} onChange={(event) => updateField("wht_type", event.target.value)} />
              </div>
              <div className="grid gap-2">
                <Label>วงเงินเครดิต</Label>
                <Input
                  type="number"
                  value={form.credit_limit}
                  onChange={(event) => updateField("credit_limit", Number(event.target.value))}
                />
              </div>
              <div className="grid gap-2">
                <Label>ธนาคาร</Label>
                <Input value={form.bank_name} onChange={(event) => updateField("bank_name", event.target.value)} />
              </div>
              <div className="grid gap-2">
                <Label>เลขบัญชี</Label>
                <Input value={form.bank_account} onChange={(event) => updateField("bank_account", event.target.value)} />
              </div>
              <div className="grid gap-2 md:col-span-2">
                <Label>ชื่อบัญชี</Label>
                <Input
                  value={form.bank_account_name}
                  onChange={(event) => updateField("bank_account_name", event.target.value)}
                />
              </div>
            </TabsContent>

            <TabsContent value="note" className="grid gap-2">
              <Label>หมายเหตุ</Label>
              <textarea
                className="min-h-[160px] rounded-md border border-gray-300 px-3 py-2 text-sm"
                value={form.note}
                onChange={(event) => updateField("note", event.target.value)}
              />
            </TabsContent>
          </Tabs>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
              ยกเลิก
            </Button>
            <Button type="button" onClick={() => void saveSupplier()}>
              บันทึก
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
