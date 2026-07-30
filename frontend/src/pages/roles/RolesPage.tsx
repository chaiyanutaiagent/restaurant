import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Plus, ShieldCheck, Trash2 } from "lucide-react";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import { useMemo, useState } from "react";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/ui/use-toast";
import { usePermission } from "@/hooks/usePermission";
import { roleApi } from "@/lib/adminApi";
import { systemApi } from "@/lib/api";
import type { RoleDetail } from "@/types/admin";
import type { Permission } from "@/types/user";

const moduleLabels: Record<string, string> = {
  system: "System",
  pos: "POS",
  inventory: "Inventory",
  accounting: "Accounting",
  hr: "HR",
  fb: "Restaurant",
  brand: "Brand Store"
};

const rolePresets = [
  {
    key: "erp-admin",
    name: "ERP Admin",
    description: "ERP core administration",
    branchAssignable: false,
    codes: [
      "system.company.view",
      "system.company.edit",
      "system.branch.view",
      "system.branch.create",
      "system.branch.edit",
      "system.user.view",
      "system.user.create",
      "system.user.edit",
      "system.user.approve",
      "system.role.view",
      "system.role.create",
      "system.role.edit",
      "inventory.product.view",
      "inventory.product.create",
      "inventory.product.edit",
      "inventory.stock.view",
      "inventory.stock.adjust",
      "inventory.purchase.view",
      "inventory.purchase.create",
      "inventory.transfer.view",
      "inventory.transfer.create",
      "brand.central.raw_stock.view",
      "brand.central.raw_stock.manage",
      "brand.central.ready_stock.view",
      "brand.central.ready_stock.manage",
      "brand.central.production.view",
      "brand.central.production.manage",
      "brand.store.stock.view",
      "brand.store.stock.adjust",
      "accounting.report.view",
      "accounting.invoice.view",
      "accounting.payment.view",
    ],
  },
  {
    key: "pos-manager",
    name: "POS Manager",
    description: "POS operations and reports",
    branchAssignable: true,
    codes: [
      "pos.sale.view",
      "pos.sale.create",
      "pos.sale.void",
      "pos.discount.apply",
      "pos.discount.override",
      "pos.refund.create",
      "pos.cashier.open_shift",
      "pos.cashier.close_shift",
      "pos.report.view",
      "system.user.request",
      "inventory.product.view",
      "inventory.stock.view",
    ],
  },
  {
    key: "cashier",
    name: "Cashier",
    description: "Cashier POS access",
    branchAssignable: true,
    codes: [
      "pos.sale.view",
      "pos.sale.create",
      "pos.discount.apply",
      "pos.cashier.open_shift",
      "pos.cashier.close_shift",
      "inventory.product.view",
      "inventory.stock.view",
    ],
  },
  {
    key: "store-manager",
    name: "Store Manager",
    description: "Brand store operations and branch staff requests",
    branchAssignable: true,
    codes: [
      "brand.store.order.create",
      "brand.store.shift.close",
      "brand.store.replenishment.submit",
      "brand.store.delivery.receive",
      "brand.store.stock.view",
      "brand.store.stock.adjust",
      "fb.order.create",
      "fb.report.view",
      "system.user.request",
    ],
  },
  {
    key: "store-cashier",
    name: "Store Cashier",
    description: "Brand storefront sales, shift close, and delivery receive",
    branchAssignable: true,
    codes: [
      "brand.store.order.create",
      "brand.store.shift.close",
      "brand.store.replenishment.submit",
      "brand.store.delivery.receive",
      "brand.store.stock.view",
    ],
  },
  {
    key: "restaurant-manager",
    name: "Restaurant Manager",
    description: "Restaurant operations and admin",
    branchAssignable: true,
    codes: [
      "fb.menu.view",
      "fb.order.create",
      "fb.kitchen.manage",
      "fb.table.manage",
      "fb.recipe.manage",
      "fb.report.view",
      "fb.settings.manage",
      "brand.central.raw_stock.view",
      "brand.central.raw_stock.manage",
      "brand.central.ready_stock.view",
      "brand.central.ready_stock.manage",
      "brand.central.production.view",
      "brand.central.production.manage",
      "inventory.product.view",
      "inventory.stock.view",
      "system.user.request",
    ],
  },
  {
    key: "kitchen-staff",
    name: "Kitchen Staff",
    description: "Kitchen display access",
    branchAssignable: true,
    codes: [
      "fb.menu.view",
      "fb.kitchen.manage",
      "brand.central.raw_stock.view",
      "brand.central.ready_stock.view",
      "brand.central.production.view",
      "brand.central.production.manage",
    ],
  },
  {
    key: "integration-admin",
    name: "Integration Admin",
    description: "API keys, webhooks, and external orders",
    branchAssignable: false,
    codes: [
      "system.company.edit",
      "pos.sale.view",
      "pos.sale.create",
    ],
  },
];

type RoleFormState = {
  name: string;
  description: string;
  permission_ids: string[];
  is_branch_assignable: boolean;
};

const emptyRoleForm: RoleFormState = {
  name: "",
  description: "",
  permission_ids: [],
  is_branch_assignable: false
};

export default function RolesPage(): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const canCreate = usePermission("system.role.create");
  const canEdit = usePermission("system.role.edit");
  const canDelete = usePermission("system.role.delete");

  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingRole, setEditingRole] = useState<RoleDetail | null>(null);
  const [form, setForm] = useState<RoleFormState>(emptyRoleForm);

  const rolesQuery = useQuery({
    queryKey: ["admin", "roles"],
    queryFn: async () => (await roleApi.list()).data.data
  });

  const permissionsQuery = useQuery({
    queryKey: ["system", "permissions"],
    queryFn: async () => (await systemApi.permissions()).data.data
  });

  const roles = rolesQuery.data ?? [];
  const permissions = permissionsQuery.data ?? [];
  const selectedRole = roles.find((role) => role.id === selectedRoleId) ?? null;

  const groupedPermissions = useMemo(() => {
    return permissions.reduce<Record<string, Permission[]>>((accumulator, permission) => {
      const key = permission.module || "system";
      accumulator[key] = [...(accumulator[key] ?? []), permission];
      return accumulator;
    }, {});
  }, [permissions]);

  const saveRoleMutation = useMutation({
    mutationFn: async () => {
      if (editingRole) {
        return roleApi.update(editingRole.id, form);
      }
      return roleApi.create(form);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin", "roles"] });
      setDialogOpen(false);
      setEditingRole(null);
      setForm(emptyRoleForm);
      toast({ title: editingRole ? "อัปเดต Role แล้ว" : "สร้าง Role แล้ว" });
    },
    onError: (error: Error) => {
      toast({ title: "บันทึก Role ไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const deleteRoleMutation = useMutation({
    mutationFn: async (roleId: string) => roleApi.delete(roleId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin", "roles"] });
      toast({ title: "ลบ Role แล้ว" });
    },
    onError: (error: Error) => {
      toast({ title: "ลบ Role ไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const openCreate = (): void => {
    setEditingRole(null);
    setForm(emptyRoleForm);
    setDialogOpen(true);
  };

  const openEdit = (role: RoleDetail): void => {
    setEditingRole(role);
    setForm({
      name: role.name,
      description: role.description ?? "",
      permission_ids: role.permissions.map((permission) => permission.id),
      is_branch_assignable: role.is_branch_assignable
    });
    setDialogOpen(true);
  };

  const visiblePermissions = selectedRole?.permissions ?? permissions;

  return (
    <div className="space-y-6">
      <PageHeader
        title="บทบาทและสิทธิ์"
        subtitle="จัดการ Role และ Permission"
        actions={
          canCreate ? (
            <Button onClick={openCreate}>
              <Plus className="mr-2 h-4 w-4" />
              สร้าง Role
            </Button>
          ) : null
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>รายการบทบาท</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ชื่อ Role</TableHead>
                <TableHead>คำอธิบาย</TableHead>
                <TableHead>จำนวนผู้ใช้</TableHead>
                <TableHead>จำนวนสิทธิ์</TableHead>
                <TableHead>System Role</TableHead>
                <TableHead>สาขาขอได้</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {roles.map((role) => (
                <TableRow
                  key={role.id}
                  className="cursor-pointer"
                  onClick={() => setSelectedRoleId(role.id === selectedRoleId ? null : role.id)}
                >
                  <TableCell className="font-medium text-gray-900">{role.name}</TableCell>
                  <TableCell>{role.description || "-"}</TableCell>
                  <TableCell>{role.user_count}</TableCell>
                  <TableCell>{role.permissions.length}</TableCell>
                  <TableCell>
                    {role.is_system ? <Badge variant="outline">System Role</Badge> : "-"}
                  </TableCell>
                  <TableCell>
                    {role.is_branch_assignable ? <Badge variant="success">อนุญาต</Badge> : "-"}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      {canEdit ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={(event) => {
                            event.stopPropagation();
                            openEdit(role);
                          }}
                        >
                          แก้ไข
                        </Button>
                      ) : null}
                      {canDelete ? (
                        <Button
                          variant="destructive"
                          size="sm"
                          disabled={role.is_system}
                          onClick={(event) => {
                            event.stopPropagation();
                            if (window.confirm(`ต้องการลบ Role ${role.name} หรือไม่`)) {
                              deleteRoleMutation.mutate(role.id);
                            }
                          }}
                        >
                          ลบ
                        </Button>
                      ) : null}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            {selectedRole ? `สิทธิ์ของ ${selectedRole.name}` : "สิทธิ์ทั้งหมดตามโมดูล"}
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          {Object.entries(
            visiblePermissions.reduce<Record<string, Permission[]>>((accumulator, permission) => {
              const key = permission.module || "system";
              accumulator[key] = [...(accumulator[key] ?? []), permission];
              return accumulator;
            }, {})
          ).map(([module, items]) => (
            <div key={module} className="rounded-xl border border-gray-200 p-4">
              <div className="mb-3 flex items-center gap-2">
                <ChevronDown className="h-4 w-4 text-gray-400" />
                <p className="font-medium text-gray-900">{moduleLabels[module] ?? module}</p>
              </div>
              <div className="space-y-2">
                {items.map((permission) => (
                  <div key={permission.id} className="rounded-lg bg-gray-50 px-3 py-2">
                    <div className="text-sm font-medium text-gray-900">{permission.name}</div>
                    <code className="text-xs text-gray-500">{permission.code}</code>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <RoleDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editingRole={editingRole}
        permissions={permissions}
        groupedPermissions={groupedPermissions}
        form={form}
        setForm={setForm}
        onSubmit={() => saveRoleMutation.mutate()}
      />
    </div>
  );
}

type RoleDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editingRole: RoleDetail | null;
  permissions: Permission[];
  groupedPermissions: Record<string, Permission[]>;
  form: RoleFormState;
  setForm: Dispatch<SetStateAction<RoleFormState>>;
  onSubmit: () => void;
};

function RoleDialog({
  open,
  onOpenChange,
  editingRole,
  permissions,
  groupedPermissions,
  form,
  setForm,
  onSubmit
}: RoleDialogProps): JSX.Element {
  const applyPreset = (presetKey: string): void => {
    const preset = rolePresets.find((item) => item.key === presetKey);
    if (!preset) return;
    const ids = permissions
      .filter((permission) => preset.codes.includes(permission.code))
      .map((permission) => permission.id);
    setForm({
      name: preset.name,
      description: preset.description,
      permission_ids: ids,
      is_branch_assignable: preset.branchAssignable,
    });
  };

  const togglePermission = (permissionId: string): void => {
    setForm((prev) => ({
      ...prev,
      permission_ids: prev.permission_ids.includes(permissionId)
        ? prev.permission_ids.filter((id) => id !== permissionId)
        : [...prev.permission_ids, permissionId]
    }));
  };

  const toggleModule = (module: string): void => {
    const modulePermissions = groupedPermissions[module] ?? [];
    const moduleIds = modulePermissions.map((permission) => permission.id);
    const allSelected = moduleIds.every((id) => form.permission_ids.includes(id));
    setForm((prev) => ({
      ...prev,
      permission_ids: allSelected
        ? prev.permission_ids.filter((id) => !moduleIds.includes(id))
        : Array.from(new Set([...prev.permission_ids, ...moduleIds]))
    }));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>{editingRole ? "แก้ไข Role" : "สร้าง Role"}</DialogTitle>
          <DialogDescription>เลือก permission ที่ต้องการให้กับบทบาทนี้</DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          {!editingRole ? (
            <Field label="Role preset">
              <select
                className="h-10 rounded-md border border-gray-300 bg-white px-3 text-sm"
                defaultValue=""
                onChange={(event) => applyPreset(event.target.value)}
              >
                <option value="">เลือก preset</option>
                {rolePresets.map((preset) => (
                  <option key={preset.key} value={preset.key}>{preset.name}</option>
                ))}
              </select>
            </Field>
          ) : null}
          <Field label="ชื่อ Role *">
            <Input value={form.name} onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))} />
          </Field>
          <Field label="คำอธิบาย">
            <Input
              value={form.description}
              onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))}
            />
          </Field>
          <label className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={form.is_branch_assignable}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, is_branch_assignable: event.target.checked }))
              }
            />
            <span>
              <span className="block font-medium text-gray-900">อนุญาตให้สาขาร้องขอบทบาทนี้</span>
              <span className="block text-gray-500">
                ระบบจะปฏิเสธหากบทบาทมีสิทธิ์แอดมินหรือสิทธิ์อนุมัติระดับกลาง
              </span>
            </span>
          </label>
          <div className="grid gap-4 md:grid-cols-2">
            {Object.entries(groupedPermissions).map(([module, items]) => {
              const allSelected = items.every((permission) => form.permission_ids.includes(permission.id));
              return (
                <details key={module} open className="rounded-xl border border-gray-200 p-4">
                  <summary className="flex cursor-pointer list-none items-center justify-between font-medium text-gray-900">
                    <span>{moduleLabels[module] ?? module}</span>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={(event) => {
                        event.preventDefault();
                        toggleModule(module);
                      }}
                    >
                      {allSelected ? "ยกเลิกทั้งหมด" : "เลือกทั้งหมด"}
                    </Button>
                  </summary>
                  <div className="mt-4 space-y-3">
                    {items.map((permission) => (
                      <label key={permission.id} className="flex items-start gap-3 rounded-lg border border-gray-100 px-3 py-2">
                        <input
                          type="checkbox"
                          checked={form.permission_ids.includes(permission.id)}
                          onChange={() => togglePermission(permission.id)}
                        />
                        <span>
                          <span className="block text-sm font-medium text-gray-900">{permission.name}</span>
                          <code className="text-xs text-gray-500">{permission.code}</code>
                        </span>
                      </label>
                    ))}
                  </div>
                </details>
              );
            })}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            ยกเลิก
          </Button>
          <Button onClick={onSubmit}>
            {editingRole ? "บันทึกการแก้ไข" : "สร้าง Role"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
