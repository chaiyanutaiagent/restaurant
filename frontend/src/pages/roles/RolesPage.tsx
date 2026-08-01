import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Plus } from "lucide-react";
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
import type { RoleDetail, RolePreset, RoleScope } from "@/types/admin";
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

const scopeLabels: Record<RolePreset["default_scope"], string> = {
  company: "ทั้งบริษัท",
  brand: "แบรนด์",
  branch: "สาขา",
  station: "จุดปฏิบัติงาน"
};

type RoleFormState = {
  name: string;
  description: string;
  permission_ids: string[];
  is_branch_assignable: boolean;
  allowed_scope_types: RoleScope[];
};

const emptyRoleForm: RoleFormState = {
  name: "",
  description: "",
  permission_ids: [],
  is_branch_assignable: false,
  allowed_scope_types: ["branch"]
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

  const rolePresetsQuery = useQuery({
    queryKey: ["system", "role-presets"],
    queryFn: async () => (await roleApi.presets()).data.data,
    enabled: canCreate
  });

  const roles = rolesQuery.data ?? [];
  const permissions = permissionsQuery.data ?? [];
  const rolePresets = rolePresetsQuery.data ?? [];
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
      is_branch_assignable: role.is_branch_assignable,
      allowed_scope_types: role.allowed_scope_types
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
                <TableHead>Scope</TableHead>
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
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {role.allowed_scope_types.map((scope) => (
                        <Badge key={scope} variant="outline">{scopeLabels[scope]}</Badge>
                      ))}
                    </div>
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
        rolePresets={rolePresets}
        rolePresetsError={rolePresetsQuery.isError}
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
  rolePresets: RolePreset[];
  rolePresetsError: boolean;
  groupedPermissions: Record<string, Permission[]>;
  form: RoleFormState;
  setForm: Dispatch<SetStateAction<RoleFormState>>;
  onSubmit: () => void;
};

function RoleDialog({
  open,
  onOpenChange,
  editingRole,
  rolePresets,
  rolePresetsError,
  groupedPermissions,
  form,
  setForm,
  onSubmit
}: RoleDialogProps): JSX.Element {
  const applyPreset = (presetKey: string): void => {
    const preset = rolePresets.find((item) => item.key === presetKey);
    if (!preset || !preset.is_available) return;
    setForm({
      name: preset.name,
      description: preset.description,
      permission_ids: preset.permission_ids,
      is_branch_assignable: preset.is_branch_assignable,
      allowed_scope_types: preset.allowed_scopes
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
                  <option key={preset.key} value={preset.key} disabled={!preset.is_available}>
                    {preset.name} · {scopeLabels[preset.default_scope]}
                    {preset.is_available ? "" : " (permission ไม่ครบ)"}
                  </option>
                ))}
              </select>
              {rolePresetsError ? (
                <p className="text-xs text-red-600">โหลด Role preset จากระบบไม่สำเร็จ</p>
              ) : null}
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
          <Field label="ขอบเขตที่ Role นี้ใช้ได้">
            <div className="grid gap-2 sm:grid-cols-4">
              {(Object.keys(scopeLabels) as RoleScope[]).map((scope) => (
                <label key={scope} className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm">
                  <input
                    type="checkbox"
                    checked={form.allowed_scope_types.includes(scope)}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        allowed_scope_types: event.target.checked
                          ? [...current.allowed_scope_types, scope]
                          : current.allowed_scope_types.filter((item) => item !== scope)
                      }))
                    }
                  />
                  {scopeLabels[scope]}
                </label>
              ))}
            </div>
          </Field>
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
