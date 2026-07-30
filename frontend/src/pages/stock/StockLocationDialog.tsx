import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
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
import type { BranchDetail } from "@/types/admin";
import type { StockLocation, StockLocationPayload } from "@/types/stock";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  branches: BranchDetail[];
  location: StockLocation | null;
  isPending: boolean;
  onSubmit: (payload: StockLocationPayload) => void;
};

const emptyForm: StockLocationPayload = {
  branch_id: "",
  code: "",
  name: "",
  description: null,
  is_active: true
};

export default function StockLocationDialog({
  open,
  onOpenChange,
  branches,
  location,
  isPending,
  onSubmit
}: Props): JSX.Element {
  const [form, setForm] = useState<StockLocationPayload>(emptyForm);

  useEffect(() => {
    if (!open) return;
    setForm(location ? {
      branch_id: location.branch_id,
      code: location.code,
      name: location.name,
      description: location.description,
      is_active: location.is_active
    } : {
      ...emptyForm,
      branch_id: branches.find((branch) => branch.is_active)?.id ?? ""
    });
  }, [branches, location, open]);

  const canSubmit = Boolean(form.branch_id && form.code.trim() && form.name.trim()) && !isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{location ? "แก้ไขคลัง" : "เพิ่มคลัง"}</DialogTitle>
          <DialogDescription>
            คลังต้องอยู่ในสาขาเดียวกับการใช้งาน RAW, READY หรือ STORE-STOCK และไม่สามารถย้ายสาขาภายหลังได้
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="stock-location-branch">สาขา *</Label>
            <select
              id="stock-location-branch"
              className="h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm disabled:bg-gray-100"
              value={form.branch_id}
              disabled={Boolean(location)}
              onChange={(event) => setForm((current) => ({ ...current, branch_id: event.target.value }))}
            >
              <option value="">เลือกสาขา</option>
              {branches.filter((branch) => branch.is_active).map((branch) => (
                <option key={branch.id} value={branch.id}>{branch.name} ({branch.code})</option>
              ))}
            </select>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="stock-location-code">รหัสคลัง *</Label>
              <Input
                id="stock-location-code"
                maxLength={20}
                placeholder="เช่น CENTRAL-READY"
                value={form.code}
                onChange={(event) => setForm((current) => ({ ...current, code: event.target.value.toUpperCase() }))}
              />
              <p className="text-xs text-gray-500">ไม่เกิน 20 ตัวอักษรและห้ามซ้ำภายในสาขา</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="stock-location-name">ชื่อคลัง *</Label>
              <Input
                id="stock-location-name"
                maxLength={255}
                placeholder="เช่น คลังสินค้าพร้อมส่ง"
                value={form.name}
                onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="stock-location-description">รายละเอียด</Label>
            <textarea
              id="stock-location-description"
              maxLength={500}
              className="min-h-24 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              placeholder="ระบุหน้าที่หรือพื้นที่จัดเก็บของคลัง"
              value={form.description ?? ""}
              onChange={(event) => setForm((current) => ({ ...current, description: event.target.value || null }))}
            />
          </div>

          {location ? (
            <label className="flex items-start gap-3 rounded-lg border border-gray-200 p-3 text-sm">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4"
                checked={form.is_active}
                onChange={(event) => setForm((current) => ({ ...current, is_active: event.target.checked }))}
              />
              <span>
                <span className="block font-medium text-gray-900">เปิดใช้งานคลัง</span>
                <span className="text-gray-500">ระบบจะไม่ให้ปิดคลังที่ยังมียอด ถูกผูกกับแบรนด์ หรือมีกะขายเปิดอยู่</span>
              </span>
            </label>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>ยกเลิก</Button>
          <Button
            disabled={!canSubmit}
            onClick={() => onSubmit({
              ...form,
              code: form.code.trim().toUpperCase(),
              name: form.name.trim(),
              description: form.description?.trim() || null
            })}
          >
            {isPending ? "กำลังบันทึก..." : "บันทึกคลัง"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
