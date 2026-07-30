import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Ruler, Search, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/ui/use-toast";
import { usePermission } from "@/hooks/usePermission";
import { unitApi } from "@/lib/productApi";
import { syncProductCatalog } from "@/lib/syncService";
import type { ApiResponse } from "@/types/api";
import type { Unit } from "@/types/product";

type UnitFormState = {
  code: string;
  name: string;
  name_en: string;
  decimal_places: string;
  is_active: boolean;
};

const emptyForm: UnitFormState = {
  code: "",
  name: "",
  name_en: "",
  decimal_places: "0",
  is_active: true
};

function toForm(unit: Unit): UnitFormState {
  return {
    code: unit.code,
    name: unit.name,
    name_en: unit.name_en ?? "",
    decimal_places: String(unit.decimal_places),
    is_active: unit.is_active
  };
}

function toPayload(form: UnitFormState): Partial<Unit> {
  return {
    code: form.code.trim().toUpperCase(),
    name: form.name.trim(),
    name_en: form.name_en.trim() || null,
    decimal_places: Math.max(0, Number(form.decimal_places || 0)),
    is_active: form.is_active
  };
}

export default function UnitsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const canCreate = usePermission("inventory.product.create");
  const canEdit = usePermission("inventory.product.edit");
  const canDelete = usePermission("inventory.product.delete");

  const [search, setSearch] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingUnit, setEditingUnit] = useState<Unit | null>(null);
  const [form, setForm] = useState<UnitFormState>(emptyForm);

  const unitsQuery = useQuery({
    queryKey: ["catalog", "units"],
    queryFn: async () => {
      const response = await unitApi.list();
      return response.data as ApiResponse<Unit[]>;
    }
  });

  const units = unitsQuery.data?.data ?? [];
  const filteredUnits = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    if (!keyword) {
      return units;
    }
    return units.filter((unit) =>
      [unit.code, unit.name, unit.name_en ?? ""].some((value) => value.toLowerCase().includes(keyword))
    );
  }, [search, units]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = toPayload(form);
      if (editingUnit) {
        return unitApi.update(editingUnit.id, payload);
      }
      return unitApi.create(payload);
    },
    onSuccess: async () => {
      toast({ title: editingUnit ? "บันทึกหน่วยสินค้าแล้ว" : "เพิ่มหน่วยสินค้าแล้ว" });
      setDialogOpen(false);
      setEditingUnit(null);
      setForm(emptyForm);
      await queryClient.invalidateQueries({ queryKey: ["catalog", "units"] });
      void syncProductCatalog();
    },
    onError: () => {
      toast({
        title: "บันทึกหน่วยสินค้าไม่สำเร็จ",
        description: "ตรวจสอบรหัสหน่วยซ้ำหรือข้อมูลที่กรอก แล้วลองอีกครั้ง",
        variant: "destructive"
      });
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (unitId: string) => unitApi.delete(unitId),
    onSuccess: async () => {
      toast({ title: "ลบหน่วยสินค้าแล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["catalog", "units"] });
      void syncProductCatalog();
    },
    onError: () => {
      toast({
        title: "ลบหน่วยสินค้าไม่สำเร็จ",
        description: "หน่วยนี้อาจยังถูกใช้กับสินค้าอยู่",
        variant: "destructive"
      });
    }
  });

  function openCreateDialog(): void {
    setEditingUnit(null);
    setForm(emptyForm);
    setDialogOpen(true);
  }

  function openEditDialog(unit: Unit): void {
    setEditingUnit(unit);
    setForm(toForm(unit));
    setDialogOpen(true);
  }

  function handleSave(): void {
    if (!form.code.trim() || !form.name.trim()) {
      toast({ title: "กรุณากรอกรหัสและชื่อหน่วย", variant: "destructive" });
      return;
    }
    saveMutation.mutate();
  }

  function handleDelete(unit: Unit): void {
    const confirmed = window.confirm(`ต้องการลบหน่วย ${unit.code} - ${unit.name} ใช่หรือไม่`);
    if (confirmed) {
      deleteMutation.mutate(unit.id);
    }
  }

  return (
    <div>
      <PageHeader
        title="หน่วยสินค้า"
        subtitle="จัดการหน่วยนับของสินค้าและวัตถุดิบ"
        actions={
          canCreate ? (
            <Button onClick={openCreateDialog}>
              <Plus className="h-4 w-4" />
              เพิ่มหน่วย
            </Button>
          ) : null
        }
      />

      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="relative w-full md:max-w-sm">
              <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-gray-400" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="ค้นหารหัสหรือชื่อหน่วย"
                className="pl-9"
              />
            </div>
            <Badge variant="outline">{filteredUnits.length} รายการ</Badge>
          </div>

          {unitsQuery.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : filteredUnits.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>รหัส</TableHead>
                  <TableHead>ชื่อหน่วย</TableHead>
                  <TableHead>ชื่ออังกฤษ</TableHead>
                  <TableHead className="text-right">ทศนิยม</TableHead>
                  <TableHead>สถานะ</TableHead>
                  <TableHead className="text-right">จัดการ</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredUnits.map((unit) => (
                  <TableRow key={unit.id}>
                    <TableCell className="font-mono text-xs font-semibold text-gray-700">{unit.code}</TableCell>
                    <TableCell className="font-medium text-gray-900">{unit.name}</TableCell>
                    <TableCell>{unit.name_en || "-"}</TableCell>
                    <TableCell className="text-right">{unit.decimal_places}</TableCell>
                    <TableCell>
                      <Badge variant={unit.is_active ? "success" : "secondary"}>
                        {unit.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-2">
                        {canEdit ? (
                          <Button variant="ghost" size="icon" onClick={() => openEditDialog(unit)}>
                            <Pencil className="h-4 w-4" />
                          </Button>
                        ) : null}
                        {canDelete ? (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="text-red-600 hover:text-red-700"
                            disabled={deleteMutation.isPending}
                            onClick={() => handleDelete(unit)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        ) : null}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
              <div className="rounded-full bg-blue-50 p-4 text-blue-600">
                <Ruler className="h-8 w-8" />
              </div>
              <p className="mt-4 text-lg font-semibold text-gray-900">ยังไม่มีหน่วยสินค้า</p>
              <p className="mt-1 text-sm text-gray-500">เพิ่มหน่วยสำหรับสินค้าและวัตถุดิบในระบบ</p>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingUnit ? "แก้ไขหน่วยสินค้า" : "เพิ่มหน่วยสินค้า"}</DialogTitle>
            <DialogDescription>ใช้กับสินค้า วัตถุดิบ สูตรอาหาร และงานคลังสินค้า</DialogDescription>
          </DialogHeader>

          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="unit-code">รหัสหน่วย</Label>
              <Input
                id="unit-code"
                value={form.code}
                maxLength={20}
                onChange={(event) => setForm((prev) => ({ ...prev, code: event.target.value.toUpperCase() }))}
                placeholder="เช่น G, KG, ML, SET"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="unit-name">ชื่อหน่วย</Label>
              <Input
                id="unit-name"
                value={form.name}
                onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
                placeholder="เช่น กรัม, กิโลกรัม, ชุด"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="unit-name-en">ชื่ออังกฤษ</Label>
              <Input
                id="unit-name-en"
                value={form.name_en}
                onChange={(event) => setForm((prev) => ({ ...prev, name_en: event.target.value }))}
                placeholder="เช่น gram, kilogram, set"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="unit-decimals">จำนวนทศนิยม</Label>
              <Input
                id="unit-decimals"
                type="number"
                min={0}
                max={6}
                value={form.decimal_places}
                onChange={(event) => setForm((prev) => ({ ...prev, decimal_places: event.target.value }))}
              />
            </div>
            <label className="flex items-center gap-3 rounded-lg border border-gray-200 p-3 text-sm font-medium text-gray-900">
              <Checkbox
                checked={form.is_active}
                onCheckedChange={(checked) => setForm((prev) => ({ ...prev, is_active: checked === true }))}
              />
              เปิดใช้งาน
            </label>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              ยกเลิก
            </Button>
            <Button disabled={saveMutation.isPending} onClick={handleSave}>
              {saveMutation.isPending ? "กำลังบันทึก..." : "บันทึก"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
