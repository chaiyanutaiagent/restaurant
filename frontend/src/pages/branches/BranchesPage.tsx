import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Plus } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { useToast } from "@/components/ui/use-toast";
import { usePermission } from "@/hooks/usePermission";
import { authApi } from "@/lib/api";
import { branchApi } from "@/lib/adminApi";
import type { BranchDetail } from "@/types/admin";

type BranchFormState = {
  code: string;
  name: string;
  name_en: string;
  address: string;
  landmark: string;
  phone: string;
  email: string;
  latitude: string;
  longitude: string;
  google_maps_url: string;
  is_warehouse: boolean;
  sort_order: number;
};

const emptyBranchForm: BranchFormState = {
  code: "",
  name: "",
  name_en: "",
  address: "",
  landmark: "",
  phone: "",
  email: "",
  latitude: "",
  longitude: "",
  google_maps_url: "",
  is_warehouse: false,
  sort_order: 0
};

export default function BranchesPage(): JSX.Element {
  const canCreate = usePermission("system.branch.create");
  const navigate = useNavigate();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState<BranchFormState>(emptyBranchForm);

  const branchesQuery = useQuery({
    queryKey: ["admin", "branches"],
    queryFn: async () => (await branchApi.list()).data.data
  });

  const myBranchesQuery = useQuery({
    queryKey: ["system", "my-branches"],
    queryFn: async () => (await authApi.myBranches()).data.data
  });

  const defaultBranchIds = new Set(
    (myBranchesQuery.data ?? []).filter((branch) => branch.is_default).map((branch) => branch.branch_id)
  );

  const createBranchMutation = useMutation({
    mutationFn: async () => {
      return branchApi.create({
        ...form,
        latitude: form.latitude.trim() ? Number(form.latitude) : null,
        longitude: form.longitude.trim() ? Number(form.longitude) : null,
      });
    },
    onSuccess: async (response) => {
      await queryClient.invalidateQueries({ queryKey: ["admin", "branches"] });
      setDialogOpen(false);
      setForm(emptyBranchForm);
      toast({ title: "สร้างสาขาแล้ว" });
      navigate(`/branches/${response.data.data.id}/settings`);
    },
    onError: (error: Error) => {
      toast({ title: "สร้างสาขาไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const branches = branchesQuery.data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="สาขา"
        subtitle="จัดการสาขาของบริษัท"
        actions={
          canCreate ? (
            <Button onClick={() => setDialogOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              เพิ่มสาขา
            </Button>
          ) : null
        }
      />

      <div className="grid gap-4 md:grid-cols-2">
        {branches.map((branch) => (
          <button
            key={branch.id}
            type="button"
            className="text-left"
            onClick={() => navigate(`/branches/${branch.id}/settings`)}
          >
            <Card className="h-full transition-shadow hover:shadow-md">
              <CardContent className="space-y-4 p-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">{branch.code}</Badge>
                      {defaultBranchIds.has(branch.id) ? <Badge variant="success">สาขาเริ่มต้น</Badge> : null}
                      {branch.is_warehouse ? <Badge variant="secondary">Warehouse</Badge> : null}
                      <Badge variant={branch.is_active ? "success" : "destructive"}>
                        {branch.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </div>
                    <p className="mt-3 text-lg font-semibold text-gray-900">{branch.name}</p>
                    <p className="text-sm text-gray-500">{branch.name_en || "ยังไม่มีชื่อภาษาอังกฤษ"}</p>
                  </div>
                  <div className="rounded-full bg-blue-50 p-3 text-blue-600">
                    <Building2 className="h-5 w-5" />
                  </div>
                </div>
                <div className="grid gap-2 text-sm text-gray-600">
                  <p>ผู้ใช้งานในสาขา: {branch.user_count}</p>
                  <p>โทรศัพท์: {branch.phone || "-"}</p>
                  <p>Email: {branch.email || "-"}</p>
                  <p>พิกัด: {branch.latitude !== null && branch.longitude !== null ? `${branch.latitude}, ${branch.longitude}` : "-"}</p>
                </div>
              </CardContent>
            </Card>
          </button>
        ))}
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>เพิ่มสาขา</DialogTitle>
            <DialogDescription>สร้างสาขาใหม่พร้อมตั้งค่าเริ่มต้นสำหรับ POS และ stock</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4">
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Code *">
                <Input value={form.code} onChange={(event) => setForm((prev) => ({ ...prev, code: event.target.value }))} />
              </Field>
              <Field label="ชื่อสาขา *">
                <Input value={form.name} onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))} />
              </Field>
            </div>
            <Field label="ชื่อภาษาอังกฤษ">
              <Input value={form.name_en} onChange={(event) => setForm((prev) => ({ ...prev, name_en: event.target.value }))} />
            </Field>
            <Field label="ที่อยู่">
              <textarea
                className="min-h-24 rounded-md border border-gray-200 px-3 py-2 text-sm"
                value={form.address}
                onChange={(event) => setForm((prev) => ({ ...prev, address: event.target.value }))}
              />
            </Field>
            <Field label="จุดสังเกต">
              <Input value={form.landmark} onChange={(event) => setForm((prev) => ({ ...prev, landmark: event.target.value }))} />
            </Field>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="โทรศัพท์">
                <Input value={form.phone} onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))} />
              </Field>
              <Field label="Email">
                <Input value={form.email} onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))} />
              </Field>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Latitude">
                <Input value={form.latitude} onChange={(event) => setForm((prev) => ({ ...prev, latitude: event.target.value }))} placeholder="13.7563309" />
              </Field>
              <Field label="Longitude">
                <Input value={form.longitude} onChange={(event) => setForm((prev) => ({ ...prev, longitude: event.target.value }))} placeholder="100.5017651" />
              </Field>
            </div>
            <Field label="Google Maps URL">
              <Input value={form.google_maps_url} onChange={(event) => setForm((prev) => ({ ...prev, google_maps_url: event.target.value }))} />
            </Field>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="flex items-center gap-3 rounded-lg border border-gray-200 px-4 py-3 text-sm">
                <input
                  type="checkbox"
                  checked={form.is_warehouse}
                  onChange={(event) => setForm((prev) => ({ ...prev, is_warehouse: event.target.checked }))}
                />
                ใช้เป็นคลังสินค้า
              </label>
              <Field label="Sort Order">
                <Input
                  type="number"
                  value={form.sort_order}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, sort_order: Number(event.target.value || 0) }))
                  }
                />
              </Field>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              ยกเลิก
            </Button>
            <Button onClick={() => createBranchMutation.mutate()}>
              บันทึก
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Field({
  label,
  children
}: {
  label: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <div className="grid gap-2">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
