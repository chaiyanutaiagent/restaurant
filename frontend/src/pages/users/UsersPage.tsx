import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Eye, EyeOff, Plus, Send, Shield, UserCog, UserMinus, Users } from "lucide-react";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import { useEffect, useMemo, useState } from "react";
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
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import { usePermission } from "@/hooks/usePermission";
import { branchApi, invitationApi, roleApi, staffAssignmentApi, userApi } from "@/lib/adminApi";
import { formatDateTimeTh } from "@/lib/utils";
import type { BranchDetail, InviteResponse, RoleDetail, RoleScope, UserDetail } from "@/types/admin";
import UserAccessRequestsPanel from "./UserAccessRequestsPanel";

type UserFormState = {
  first_name: string;
  last_name: string;
  display_name: string;
  email: string;
  phone: string;
  username: string;
  password: string;
  confirm_password: string;
  branch_id: string;
  role_id: string;
};

type InviteFormState = {
  email: string;
  phone: string;
  first_name: string;
  last_name: string;
  branch_id: string;
  role_id: string;
};

type EditableUserState = {
  email: string;
  phone: string;
  first_name: string;
  last_name: string;
  display_name: string;
  is_active: boolean;
};

type PasswordFormState = {
  new_password: string;
  confirm_password: string;
};

const emptyUserForm: UserFormState = {
  first_name: "",
  last_name: "",
  display_name: "",
  email: "",
  phone: "",
  username: "",
  password: "",
  confirm_password: "",
  branch_id: "",
  role_id: ""
};

const emptyInviteForm: InviteFormState = {
  email: "",
  phone: "",
  first_name: "",
  last_name: "",
  branch_id: "",
  role_id: ""
};

function hashColor(input: string): string {
  const colors = [
    "bg-rose-100 text-rose-700",
    "bg-sky-100 text-sky-700",
    "bg-emerald-100 text-emerald-700",
    "bg-amber-100 text-amber-700",
    "bg-indigo-100 text-indigo-700",
    "bg-cyan-100 text-cyan-700"
  ];
  const hash = Array.from(input).reduce((sum, char) => sum + char.charCodeAt(0), 0);
  return colors[hash % colors.length];
}

function getInitials(user: UserDetail): string {
  const source = user.display_name || `${user.first_name ?? ""} ${user.last_name ?? ""}`.trim() || user.username;
  return source
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("");
}

function formatBranches(user: UserDetail): string {
  if (user.branches.length <= 2) {
    return user.branches.map((branch) => branch.branch_name).join(", ");
  }
  return `${user.branches
    .slice(0, 2)
    .map((branch) => branch.branch_name)
    .join(", ")} +${user.branches.length - 2} สาขา`;
}

function defaultRoleName(user: UserDetail): string {
  return user.branches.find((branch) => branch.is_default)?.role_name ?? "-";
}

function mapEditableUser(user: UserDetail): EditableUserState {
  return {
    email: user.email ?? "",
    phone: user.phone ?? "",
    first_name: user.first_name ?? "",
    last_name: user.last_name ?? "",
    display_name: user.display_name ?? "",
    is_active: user.is_active
  };
}

export default function UsersPage(): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const canCreate = usePermission("system.user.create");
  const canEdit = usePermission("system.user.edit");
  const canDeactivate = usePermission("system.user.delete");
  const canViewCompanyRequests = usePermission("*");

  const [search, setSearch] = useState("");
  const [branchFilter, setBranchFilter] = useState("");
  const [activeFilter, setActiveFilter] = useState("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [userForm, setUserForm] = useState<UserFormState>(emptyUserForm);
  const [inviteForm, setInviteForm] = useState<InviteFormState>(emptyInviteForm);
  const [inviteResult, setInviteResult] = useState<InviteResponse | null>(null);
  const [showCreatePassword, setShowCreatePassword] = useState(false);
  const [showSecurityPassword, setShowSecurityPassword] = useState(false);
  const [editUser, setEditUser] = useState<EditableUserState | null>(null);
  const [passwordForm, setPasswordForm] = useState<PasswordFormState>({
    new_password: "",
    confirm_password: ""
  });
  const [assignBranchId, setAssignBranchId] = useState("");
  const [assignRoleId, setAssignRoleId] = useState("");

  const usersQuery = useQuery({
    queryKey: ["admin", "users", { search, branchFilter, activeFilter }],
    queryFn: async () => {
      const response = await userApi.list({
        search: search || undefined,
        branch_id: branchFilter || undefined,
        is_active: activeFilter === "all" ? undefined : activeFilter === "active"
      });
      return response.data;
    }
  });

  const rolesQuery = useQuery({
    queryKey: ["admin", "roles"],
    queryFn: async () => (await roleApi.list()).data.data
  });

  const branchesQuery = useQuery({
    queryKey: ["admin", "branches"],
    queryFn: async () => (await branchApi.list()).data.data
  });

  const selectedUserQuery = useQuery({
    queryKey: ["admin", "users", selectedUserId],
    enabled: Boolean(selectedUserId),
    queryFn: async () => (await userApi.get(selectedUserId ?? "")).data.data
  });

  const users = usersQuery.data?.data ?? [];
  const selectedUser = selectedUserQuery.data ?? null;
  const branches = branchesQuery.data ?? [];
  const roles = rolesQuery.data ?? [];

  const availableBranchOptions = useMemo(
    () => branches.filter((branch) => branch.is_active),
    [branches]
  );

  useEffect(() => {
    if (selectedUser) {
      setEditUser(mapEditableUser(selectedUser));
    }
  }, [selectedUser]);

  const invalidateUsers = async (): Promise<void> => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] }),
      queryClient.invalidateQueries({ queryKey: ["admin", "branches"] })
    ]);
  };

  const createUserMutation = useMutation({
    mutationFn: async () => {
      if (userForm.password !== userForm.confirm_password) {
        throw new Error("กรุณายืนยันรหัสผ่านให้ตรงกัน");
      }
      return userApi.create({
        username: userForm.username,
        password: userForm.password,
        first_name: userForm.first_name || null,
        last_name: userForm.last_name || null,
        display_name: userForm.display_name || null,
        email: userForm.email || null,
        phone: userForm.phone || null,
        branch_id: userForm.branch_id,
        role_id: userForm.role_id
      });
    },
    onSuccess: async () => {
      await invalidateUsers();
      setCreateOpen(false);
      setUserForm(emptyUserForm);
      toast({ title: "สร้างผู้ใช้สำเร็จ" });
    },
    onError: (error: Error) => {
      toast({ title: "สร้างผู้ใช้ไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const inviteMutation = useMutation({
    mutationFn: async () => {
      if (!inviteForm.email && !inviteForm.phone) {
        throw new Error("กรุณากรอก email หรือเบอร์โทรศัพท์อย่างน้อย 1 รายการ");
      }
      const response = await invitationApi.create({
        email: inviteForm.email || null,
        phone: inviteForm.phone || null,
        first_name: inviteForm.first_name || null,
        last_name: inviteForm.last_name || null,
        branch_id: inviteForm.branch_id,
        role_id: inviteForm.role_id
      });
      return response.data.data;
    },
    onSuccess: (result) => {
      setInviteResult(result);
      toast({ title: "สร้างคำเชิญสำเร็จ" });
    },
    onError: (error: Error) => {
      toast({ title: "สร้างคำเชิญไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const updateUserMutation = useMutation({
    mutationFn: async () => {
      if (!selectedUserId || !editUser) {
        throw new Error("ไม่พบผู้ใช้งาน");
      }
      return userApi.update(selectedUserId, {
        email: editUser.email || null,
        phone: editUser.phone || null,
        first_name: editUser.first_name || null,
        last_name: editUser.last_name || null,
        display_name: editUser.display_name || null,
        is_active: editUser.is_active
      });
    },
    onSuccess: async () => {
      await invalidateUsers();
      if (selectedUserId) {
        await queryClient.invalidateQueries({ queryKey: ["admin", "users", selectedUserId] });
      }
      toast({ title: "อัปเดตข้อมูลผู้ใช้แล้ว" });
    },
    onError: (error: Error) => {
      toast({ title: "อัปเดตข้อมูลไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const deactivateMutation = useMutation({
    mutationFn: async (userId: string) => userApi.deactivate(userId),
    onSuccess: async (_, userId) => {
      await invalidateUsers();
      await queryClient.invalidateQueries({ queryKey: ["admin", "users", userId] });
      toast({ title: "ปิดใช้งานบัญชีแล้ว" });
    },
    onError: (error: Error) => {
      toast({ title: "ปิดใช้งานไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const changePasswordMutation = useMutation({
    mutationFn: async () => {
      if (!selectedUserId) {
        throw new Error("ไม่พบผู้ใช้งาน");
      }
      if (passwordForm.new_password !== passwordForm.confirm_password) {
        throw new Error("กรุณายืนยันรหัสผ่านให้ตรงกัน");
      }
      return userApi.changePassword(selectedUserId, passwordForm.new_password);
    },
    onSuccess: () => {
      setPasswordForm({ new_password: "", confirm_password: "" });
      toast({ title: "เปลี่ยนรหัสผ่านแล้ว" });
    },
    onError: (error: Error) => {
      toast({ title: "เปลี่ยนรหัสผ่านไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const assignBranchMutation = useMutation({
    mutationFn: async () => {
      if (!selectedUserId) {
        throw new Error("ไม่พบผู้ใช้งาน");
      }
      return userApi.assignBranch(selectedUserId, {
        branch_id: assignBranchId,
        role_id: assignRoleId
      });
    },
    onSuccess: async () => {
      setAssignBranchId("");
      setAssignRoleId("");
      await invalidateUsers();
      if (selectedUserId) {
        await queryClient.invalidateQueries({ queryKey: ["admin", "users", selectedUserId] });
      }
      toast({ title: "เพิ่มสาขาแล้ว" });
    },
    onError: (error: Error) => {
      toast({ title: "เพิ่มสาขาไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const removeBranchMutation = useMutation({
    mutationFn: async (branchId: string) => {
      if (!selectedUserId) {
        throw new Error("ไม่พบผู้ใช้งาน");
      }
      return userApi.removeBranch(selectedUserId, branchId);
    },
    onSuccess: async () => {
      await invalidateUsers();
      if (selectedUserId) {
        await queryClient.invalidateQueries({ queryKey: ["admin", "users", selectedUserId] });
      }
      toast({ title: "ลบสิทธิ์สาขาแล้ว" });
    },
    onError: (error: Error) => {
      toast({ title: "ลบสาขาไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const openDetail = (user: UserDetail): void => {
    setSelectedUserId(user.id);
    setEditUser(mapEditableUser(user));
    setPasswordForm({ new_password: "", confirm_password: "" });
    setAssignBranchId("");
    setAssignRoleId("");
    setDetailOpen(true);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="ผู้ใช้งาน"
        subtitle="จัดการบัญชีผู้ใช้งานทั้งหมด"
        actions={
          <div className="flex gap-2">
            {canCreate ? (
              <Button variant="outline" onClick={() => setInviteOpen(true)}>
                <Send className="mr-2 h-4 w-4" />
                ส่งคำเชิญ
              </Button>
            ) : null}
            {canCreate ? (
              <Button onClick={() => setCreateOpen(true)}>
                <Plus className="mr-2 h-4 w-4" />
                เพิ่มผู้ใช้
              </Button>
            ) : null}
          </div>
        }
      />

      <Tabs defaultValue="accounts">
        <TabsList>
          <TabsTrigger value="accounts">บัญชีผู้ใช้</TabsTrigger>
          {canViewCompanyRequests ? <TabsTrigger value="requests">คำขอทุกแบรนด์</TabsTrigger> : null}
        </TabsList>
        <TabsContent value="accounts">
      <Card>
        <CardContent className="space-y-4 p-5">
          <div className="grid gap-3 md:grid-cols-[1.6fr_1fr_180px]">
            <Input
              placeholder="ค้นหาจาก username, ชื่อ หรือ email"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <select
              className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm"
              value={branchFilter}
              onChange={(event) => setBranchFilter(event.target.value)}
            >
              <option value="">ทุกสาขา</option>
              {branches.map((branch) => (
                <option key={branch.id} value={branch.id}>
                  {branch.name}
                </option>
              ))}
            </select>
            <select
              className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm"
              value={activeFilter}
              onChange={(event) => setActiveFilter(event.target.value)}
            >
              <option value="all">ทั้งหมด</option>
              <option value="active">เฉพาะ Active</option>
              <option value="inactive">เฉพาะ Inactive</option>
            </select>
          </div>

          {usersQuery.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : users.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Avatar</TableHead>
                  <TableHead>ชื่อ</TableHead>
                  <TableHead>Email | โทรศัพท์</TableHead>
                  <TableHead>สาขาที่มีสิทธิ์</TableHead>
                  <TableHead>บทบาทหลัก</TableHead>
                  <TableHead>เข้าสู่ระบบล่าสุด</TableHead>
                  <TableHead>สถานะ</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((user) => (
                  <TableRow key={user.id}>
                    <TableCell>
                      <div className={`flex h-10 w-10 items-center justify-center rounded-full text-sm font-semibold ${hashColor(user.username)}`}>
                        {getInitials(user)}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="font-medium text-gray-900">{user.display_name || `${user.first_name ?? ""} ${user.last_name ?? ""}`.trim() || "-"}</div>
                      <div className="text-xs text-gray-500">@{user.username}</div>
                    </TableCell>
                    <TableCell>
                      <div>{user.email || "-"}</div>
                      <div className="text-xs text-gray-500">{user.phone || "-"}</div>
                    </TableCell>
                    <TableCell>{formatBranches(user)}</TableCell>
                    <TableCell>{defaultRoleName(user)}</TableCell>
                    <TableCell>{user.last_login_at ? formatDateTimeTh(user.last_login_at) : "ยังไม่เคย"}</TableCell>
                    <TableCell>
                      <Badge variant={user.is_active ? "success" : "destructive"}>
                        {user.is_active ? "active" : "inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button variant="outline" size="sm" onClick={() => openDetail(user)}>
                          <UserCog className="mr-2 h-4 w-4" />
                          จัดการ
                        </Button>
                        {canDeactivate && user.is_active ? (
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => {
                              if (window.confirm(`ต้องการปิดใช้งาน ${user.username} หรือไม่`)) {
                                deactivateMutation.mutate(user.id);
                              }
                            }}
                          >
                            <UserMinus className="mr-2 h-4 w-4" />
                            ปิดใช้งาน
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
                <Users className="h-8 w-8" />
              </div>
              <p className="mt-4 text-lg font-semibold text-gray-900">ยังไม่มีผู้ใช้งานที่ตรงกับเงื่อนไข</p>
              <p className="mt-1 text-sm text-gray-500">ลองปรับตัวกรองหรือสร้างผู้ใช้ใหม่ได้จากปุ่มด้านบน</p>
            </div>
          )}
        </CardContent>
      </Card>
        </TabsContent>
        {canViewCompanyRequests ? (
          <TabsContent value="requests">
            <UserAccessRequestsPanel branches={branches} />
          </TabsContent>
        ) : null}
      </Tabs>

      <CreateUserDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        branches={availableBranchOptions}
        roles={roles}
        state={userForm}
        setState={setUserForm}
        loading={createUserMutation.isPending}
        onSubmit={() => createUserMutation.mutate()}
        showPassword={showCreatePassword}
        onTogglePassword={() => setShowCreatePassword((value) => !value)}
      />

      <InviteUserDialog
        open={inviteOpen}
        onOpenChange={(open) => {
          setInviteOpen(open);
          if (!open) {
            setInviteResult(null);
            setInviteForm(emptyInviteForm);
          }
        }}
        branches={availableBranchOptions}
        roles={roles}
        state={inviteForm}
        setState={setInviteForm}
        result={inviteResult}
        loading={inviteMutation.isPending}
        onSubmit={() => inviteMutation.mutate()}
      />

      <UserDetailDialog
        open={detailOpen}
        onOpenChange={setDetailOpen}
        user={selectedUser}
        loading={selectedUserQuery.isLoading}
        editable={editUser}
        setEditable={setEditUser}
        roles={roles}
        branches={availableBranchOptions}
        canEdit={canEdit}
        canDeactivate={canDeactivate}
        assignBranchId={assignBranchId}
        setAssignBranchId={setAssignBranchId}
        assignRoleId={assignRoleId}
        setAssignRoleId={setAssignRoleId}
        onSaveProfile={() => updateUserMutation.mutate()}
        onAssignBranch={() => assignBranchMutation.mutate()}
        onRemoveBranch={(branchId) => removeBranchMutation.mutate(branchId)}
        onDeactivate={() => {
          if (selectedUser && window.confirm(`ต้องการปิดใช้งาน ${selectedUser.username} หรือไม่`)) {
            deactivateMutation.mutate(selectedUser.id);
          }
        }}
        passwordForm={passwordForm}
        setPasswordForm={setPasswordForm}
        showPassword={showSecurityPassword}
        onTogglePassword={() => setShowSecurityPassword((value) => !value)}
        onChangePassword={() => changePasswordMutation.mutate()}
      />
    </div>
  );
}

type CreateUserDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  branches: BranchDetail[];
  roles: RoleDetail[];
  state: UserFormState;
  setState: Dispatch<SetStateAction<UserFormState>>;
  loading: boolean;
  onSubmit: () => void;
  showPassword: boolean;
  onTogglePassword: () => void;
};

function CreateUserDialog({
  open,
  onOpenChange,
  branches,
  roles,
  state,
  setState,
  loading,
  onSubmit,
  showPassword,
  onTogglePassword
}: CreateUserDialogProps): JSX.Element {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>เพิ่มผู้ใช้</DialogTitle>
          <DialogDescription>สร้างผู้ใช้ใหม่พร้อมกำหนดสาขาเริ่มต้นและบทบาทหลัก</DialogDescription>
        </DialogHeader>
        <Tabs defaultValue="profile">
          <TabsList>
            <TabsTrigger value="profile">ข้อมูลส่วนตัว</TabsTrigger>
            <TabsTrigger value="login">ข้อมูลเข้าสู่ระบบ</TabsTrigger>
            <TabsTrigger value="access">สาขาและบทบาท</TabsTrigger>
          </TabsList>
          <TabsContent value="profile" className="grid gap-4">
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="ชื่อ">
                <Input value={state.first_name} onChange={(event) => setState((prev) => ({ ...prev, first_name: event.target.value }))} />
              </Field>
              <Field label="นามสกุล">
                <Input value={state.last_name} onChange={(event) => setState((prev) => ({ ...prev, last_name: event.target.value }))} />
              </Field>
            </div>
            <Field label="ชื่อแสดง">
              <Input value={state.display_name} onChange={(event) => setState((prev) => ({ ...prev, display_name: event.target.value }))} />
            </Field>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Email">
                <Input value={state.email} onChange={(event) => setState((prev) => ({ ...prev, email: event.target.value }))} />
              </Field>
              <Field label="โทรศัพท์">
                <Input value={state.phone} onChange={(event) => setState((prev) => ({ ...prev, phone: event.target.value }))} />
              </Field>
            </div>
          </TabsContent>
          <TabsContent value="login" className="grid gap-4">
            <Field label="Username *">
              <Input value={state.username} onChange={(event) => setState((prev) => ({ ...prev, username: event.target.value }))} />
            </Field>
            <Field label="Password *">
              <div className="relative">
                <Input
                  type={showPassword ? "text" : "password"}
                  value={state.password}
                  onChange={(event) => setState((prev) => ({ ...prev, password: event.target.value }))}
                />
                <button type="button" className="absolute right-3 top-2.5 text-gray-500" onClick={onTogglePassword}>
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </Field>
            <Field label="Confirm Password">
              <Input
                type={showPassword ? "text" : "password"}
                value={state.confirm_password}
                onChange={(event) => setState((prev) => ({ ...prev, confirm_password: event.target.value }))}
              />
            </Field>
          </TabsContent>
          <TabsContent value="access" className="grid gap-4 md:grid-cols-2">
            <Field label="สาขา *">
              <select
                className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm"
                value={state.branch_id}
                onChange={(event) => setState((prev) => ({ ...prev, branch_id: event.target.value }))}
              >
                <option value="">เลือกสาขา</option>
                {branches.map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="บทบาท *">
              <select
                className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm"
                value={state.role_id}
                onChange={(event) => setState((prev) => ({ ...prev, role_id: event.target.value }))}
              >
                <option value="">เลือกบทบาท</option>
                {roles.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.name}
                  </option>
                ))}
              </select>
            </Field>
          </TabsContent>
        </Tabs>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            ยกเลิก
          </Button>
          <Button onClick={onSubmit} disabled={loading}>
            บันทึก
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type InviteUserDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  branches: BranchDetail[];
  roles: RoleDetail[];
  state: InviteFormState;
  setState: Dispatch<SetStateAction<InviteFormState>>;
  result: InviteResponse | null;
  loading: boolean;
  onSubmit: () => void;
};

function InviteUserDialog({
  open,
  onOpenChange,
  branches,
  roles,
  state,
  setState,
  result,
  loading,
  onSubmit
}: InviteUserDialogProps): JSX.Element {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>ส่งคำเชิญผู้ใช้</DialogTitle>
          <DialogDescription>กรอกข้อมูลพื้นฐานและส่ง OTP ให้ผู้ใช้งานนำไปสร้างบัญชี</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Email">
              <Input value={state.email} onChange={(event) => setState((prev) => ({ ...prev, email: event.target.value }))} />
            </Field>
            <Field label="โทรศัพท์">
              <Input value={state.phone} onChange={(event) => setState((prev) => ({ ...prev, phone: event.target.value }))} />
            </Field>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="ชื่อ">
              <Input value={state.first_name} onChange={(event) => setState((prev) => ({ ...prev, first_name: event.target.value }))} />
            </Field>
            <Field label="นามสกุล">
              <Input value={state.last_name} onChange={(event) => setState((prev) => ({ ...prev, last_name: event.target.value }))} />
            </Field>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="สาขา *">
              <select
                className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm"
                value={state.branch_id}
                onChange={(event) => setState((prev) => ({ ...prev, branch_id: event.target.value }))}
              >
                <option value="">เลือกสาขา</option>
                {branches.map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="บทบาท *">
              <select
                className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm"
                value={state.role_id}
                onChange={(event) => setState((prev) => ({ ...prev, role_id: event.target.value }))}
              >
                <option value="">เลือกบทบาท</option>
                {roles.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          {result ? (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
              <p className="text-sm font-medium text-emerald-900">รหัสคำเชิญ (แสดงครั้งเดียว):</p>
              <div className="mt-3 flex items-center gap-3 rounded-lg border border-emerald-200 bg-white px-4 py-3">
                <code className="text-2xl font-bold tracking-[0.25em] text-emerald-700">{result.otp_code}</code>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void navigator.clipboard.writeText(result.otp_code)}
                >
                  <Copy className="mr-2 h-4 w-4" />
                  คัดลอก
                </Button>
              </div>
              <p className="mt-3 text-sm text-emerald-900">หมดอายุ: 72 ชั่วโมง</p>
              <p className="text-sm text-emerald-900">กรุณาส่งรหัสนี้ให้ผู้ใช้งานที่ต้องการเชิญ</p>
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            ปิด
          </Button>
          <Button onClick={onSubmit} disabled={loading}>
            สร้างคำเชิญ
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type UserDetailDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: UserDetail | null;
  loading: boolean;
  editable: EditableUserState | null;
  setEditable: Dispatch<SetStateAction<EditableUserState | null>>;
  roles: RoleDetail[];
  branches: BranchDetail[];
  canEdit: boolean;
  canDeactivate: boolean;
  assignBranchId: string;
  setAssignBranchId: Dispatch<SetStateAction<string>>;
  assignRoleId: string;
  setAssignRoleId: Dispatch<SetStateAction<string>>;
  onSaveProfile: () => void;
  onAssignBranch: () => void;
  onRemoveBranch: (branchId: string) => void;
  onDeactivate: () => void;
  passwordForm: PasswordFormState;
  setPasswordForm: Dispatch<SetStateAction<PasswordFormState>>;
  showPassword: boolean;
  onTogglePassword: () => void;
  onChangePassword: () => void;
};

function UserDetailDialog(props: UserDetailDialogProps): JSX.Element {
  const {
    open,
    onOpenChange,
    user,
    loading,
    editable,
    setEditable,
    roles,
    branches,
    canEdit,
    canDeactivate,
    assignBranchId,
    setAssignBranchId,
    assignRoleId,
    setAssignRoleId,
    onSaveProfile,
    onAssignBranch,
    onRemoveBranch,
    onDeactivate,
    passwordForm,
    setPasswordForm,
    showPassword,
    onTogglePassword,
    onChangePassword
  } = props;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl">
        <DialogHeader>
          <DialogTitle>{user ? `จัดการผู้ใช้: ${user.username}` : "จัดการผู้ใช้"}</DialogTitle>
          <DialogDescription>แก้ไขข้อมูล, สาขาและบทบาท, และความปลอดภัยของบัญชี</DialogDescription>
        </DialogHeader>
        {loading || !user || !editable ? (
          <div className="space-y-3">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-36 w-full" />
          </div>
        ) : (
          <Tabs defaultValue="profile">
            <TabsList>
              <TabsTrigger value="profile">ข้อมูล</TabsTrigger>
              <TabsTrigger value="branches">สาขาและบทบาท</TabsTrigger>
              <TabsTrigger value="security">ความปลอดภัย</TabsTrigger>
            </TabsList>

            <TabsContent value="profile" className="space-y-4">
              <div className="grid gap-3 rounded-xl border border-gray-200 bg-gray-50 p-4 text-sm md:grid-cols-3">
                <div>
                  <p className="text-gray-500">สร้างเมื่อ</p>
                  <p className="font-medium text-gray-900">{formatDateTimeTh(user.created_at)}</p>
                </div>
                <div>
                  <p className="text-gray-500">เข้าสู่ระบบล่าสุด</p>
                  <p className="font-medium text-gray-900">{user.last_login_at ? formatDateTimeTh(user.last_login_at) : "ยังไม่เคย"}</p>
                </div>
                <div className="flex items-center justify-start md:justify-end">
                  {user.is_superuser ? (
                    <Badge variant="outline" className="gap-2">
                      <Shield className="h-3.5 w-3.5" />
                      Superuser
                    </Badge>
                  ) : null}
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <Field label="ชื่อ">
                  <Input value={editable.first_name} onChange={(event) => setEditable((prev) => prev ? { ...prev, first_name: event.target.value } : prev)} />
                </Field>
                <Field label="นามสกุล">
                  <Input value={editable.last_name} onChange={(event) => setEditable((prev) => prev ? { ...prev, last_name: event.target.value } : prev)} />
                </Field>
              </div>
              <Field label="ชื่อแสดง">
                <Input value={editable.display_name} onChange={(event) => setEditable((prev) => prev ? { ...prev, display_name: event.target.value } : prev)} />
              </Field>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Email">
                  <Input value={editable.email} onChange={(event) => setEditable((prev) => prev ? { ...prev, email: event.target.value } : prev)} />
                </Field>
                <Field label="โทรศัพท์">
                  <Input value={editable.phone} onChange={(event) => setEditable((prev) => prev ? { ...prev, phone: event.target.value } : prev)} />
                </Field>
              </div>
              <label className="flex items-center gap-3 rounded-lg border border-gray-200 px-4 py-3 text-sm">
                <input
                  type="checkbox"
                  checked={editable.is_active}
                  onChange={(event) => setEditable((prev) => prev ? { ...prev, is_active: event.target.checked } : prev)}
                />
                เปิดใช้งานบัญชี
              </label>
              {canEdit ? (
                <div className="flex justify-end">
                  <Button onClick={onSaveProfile}>บันทึกข้อมูล</Button>
                </div>
              ) : null}
            </TabsContent>

            <TabsContent value="branches" className="space-y-4">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>สาขา</TableHead>
                    <TableHead>บทบาท</TableHead>
                    <TableHead>สาขาเริ่มต้น</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {user.branches.map((branch) => (
                    <TableRow key={branch.branch_id}>
                      <TableCell>{branch.branch_name}</TableCell>
                      <TableCell>{branch.role_name}</TableCell>
                      <TableCell>{branch.is_default ? <Badge variant="success">Default</Badge> : "-"}</TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={user.branches.length <= 1}
                          onClick={() => onRemoveBranch(branch.branch_id)}
                        >
                          ลบออก
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {user.branches.length <= 1 ? (
                <p className="text-sm text-amber-700">ไม่สามารถลบสาขาสุดท้ายของผู้ใช้งานได้</p>
              ) : null}
              <div className="grid gap-3 rounded-xl border border-dashed border-gray-300 p-4 md:grid-cols-[1fr_1fr_auto]">
                <select
                  className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm"
                  value={assignBranchId}
                  onChange={(event) => setAssignBranchId(event.target.value)}
                >
                  <option value="">เลือกสาขา</option>
                  {branches.map((branch) => (
                    <option key={branch.id} value={branch.id}>
                      {branch.name}
                    </option>
                  ))}
                </select>
                <select
                  className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm"
                  value={assignRoleId}
                  onChange={(event) => setAssignRoleId(event.target.value)}
                >
                  <option value="">เลือกบทบาท</option>
                  {roles.map((role) => (
                    <option key={role.id} value={role.id}>
                      {role.name}
                    </option>
                  ))}
                </select>
                <Button onClick={onAssignBranch}>เพิ่มสาขา</Button>
              </div>
              {canEdit ? (
                <ScopedAssignmentsPanel userId={user.id} roles={roles} canEdit={canEdit} />
              ) : null}
            </TabsContent>

            <TabsContent value="security" className="space-y-5">
              <div className="rounded-xl border border-gray-200 p-4">
                <p className="text-sm font-medium text-gray-900">เปลี่ยนรหัสผ่าน</p>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <Field label="รหัสผ่านใหม่">
                    <div className="relative">
                      <Input
                        type={showPassword ? "text" : "password"}
                        value={passwordForm.new_password}
                        onChange={(event) =>
                          setPasswordForm((prev) => ({ ...prev, new_password: event.target.value }))
                        }
                      />
                      <button type="button" className="absolute right-3 top-2.5 text-gray-500" onClick={onTogglePassword}>
                        {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </Field>
                  <Field label="ยืนยันรหัสผ่าน">
                    <Input
                      type={showPassword ? "text" : "password"}
                      value={passwordForm.confirm_password}
                      onChange={(event) =>
                        setPasswordForm((prev) => ({ ...prev, confirm_password: event.target.value }))
                      }
                    />
                  </Field>
                </div>
                <div className="mt-4 flex justify-end">
                  <Button onClick={onChangePassword}>เปลี่ยนรหัสผ่าน</Button>
                </div>
              </div>

              {canDeactivate ? (
                <div className="rounded-xl border border-red-200 bg-red-50 p-4">
                  <p className="text-sm font-medium text-red-900">ปิดใช้งานบัญชี</p>
                  <p className="mt-1 text-sm text-red-700">บัญชีจะไม่สามารถเข้าสู่ระบบได้อีกจนกว่าจะถูกเปิดใช้งานใหม่</p>
                  <div className="mt-4">
                    <Button variant="destructive" onClick={onDeactivate}>
                      ปิดใช้งานบัญชี
                    </Button>
                  </div>
                </div>
              ) : null}
            </TabsContent>
          </Tabs>
        )}
      </DialogContent>
    </Dialog>
  );
}

type ScopedAssignmentForm = {
  role_id: string;
  scope_type: RoleScope;
  brand_id: string;
  branch_id: string;
  station_key: string;
  reason: string;
};

const emptyScopedAssignmentForm: ScopedAssignmentForm = {
  role_id: "",
  scope_type: "branch",
  brand_id: "",
  branch_id: "",
  station_key: "",
  reason: ""
};

function ScopedAssignmentsPanel({
  userId,
  roles,
  canEdit
}: {
  userId: string;
  roles: RoleDetail[];
  canEdit: boolean;
}): JSX.Element {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [form, setForm] = useState<ScopedAssignmentForm>(emptyScopedAssignmentForm);
  const assignmentsQuery = useQuery({
    queryKey: ["admin", "users", userId, "role-assignments"],
    queryFn: async () => (await userApi.listRoleAssignments(userId)).data.data
  });
  const optionsQuery = useQuery({
    queryKey: ["admin", "staff-assignment-options"],
    queryFn: async () => (await staffAssignmentApi.options()).data.data,
    enabled: canEdit
  });
  const assignments = assignmentsQuery.data ?? [];
  const options = optionsQuery.data;
  const eligibleRoles = roles.filter((role) => role.allowed_scope_types.includes(form.scope_type));
  const selectedBranch = options?.branches.find((branch) => branch.id === form.branch_id);
  const targetReady =
    form.scope_type === "company" ||
    (form.scope_type === "brand" && Boolean(form.brand_id)) ||
    (form.scope_type === "branch" && Boolean(form.branch_id)) ||
    (form.scope_type === "station" && Boolean(form.branch_id) && Boolean(form.station_key));

  const invalidate = async (): Promise<void> => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin", "users", userId, "role-assignments"] }),
      queryClient.invalidateQueries({ queryKey: ["system", "my-branches"] })
    ]);
  };

  const createMutation = useMutation({
    mutationFn: async () =>
      userApi.createRoleAssignment(userId, {
        role_id: form.role_id,
        scope_type: form.scope_type,
        brand_id: form.scope_type === "brand" ? form.brand_id : null,
        branch_id: ["branch", "station"].includes(form.scope_type) ? form.branch_id : null,
        station_key: form.scope_type === "station" ? form.station_key : null,
        reason: form.reason
      }),
    onSuccess: async () => {
      setForm(emptyScopedAssignmentForm);
      await invalidate();
      toast({ title: "เพิ่ม Role scope แล้ว" });
    },
    onError: (error: Error) => {
      toast({ title: "เพิ่ม Role scope ไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const revokeMutation = useMutation({
    mutationFn: async ({ assignmentId, reason }: { assignmentId: string; reason: string }) =>
      userApi.revokeRoleAssignment(userId, assignmentId, reason),
    onSuccess: async () => {
      await invalidate();
      toast({ title: "ยกเลิก Role scope แล้ว" });
    },
    onError: (error: Error) => {
      toast({ title: "ยกเลิก Role scope ไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  return (
    <div className="space-y-4 border-t border-gray-200 pt-5">
      <div>
        <p className="font-medium text-gray-900">Role + Scope assignments</p>
        <p className="text-sm text-gray-500">
          สิทธิ์ใหม่ระดับ Company, Brand, Branch หรือ Kitchen station; รายการสาขาด้านบนยังเป็น compatibility เดิม
        </p>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>บทบาท</TableHead>
            <TableHead>ระดับ</TableHead>
            <TableHead>ขอบเขต</TableHead>
            <TableHead>เหตุผล</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {assignments.map((assignment) => (
            <TableRow key={assignment.id}>
              <TableCell>{assignment.role_name}</TableCell>
              <TableCell><Badge variant="outline">{assignment.scope_type}</Badge></TableCell>
              <TableCell>{assignment.scope_label}</TableCell>
              <TableCell>{assignment.assignment_reason}</TableCell>
              <TableCell className="text-right">
                {canEdit ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      const reason = window.prompt("ระบุเหตุผลที่ยกเลิก assignment");
                      if (reason?.trim()) {
                        revokeMutation.mutate({ assignmentId: assignment.id, reason: reason.trim() });
                      }
                    }}
                  >
                    ยกเลิก
                  </Button>
                ) : null}
              </TableCell>
            </TableRow>
          ))}
          {assignments.length === 0 ? (
            <TableRow>
              <TableCell colSpan={5} className="text-center text-gray-500">ยังไม่มี scoped assignment</TableCell>
            </TableRow>
          ) : null}
        </TableBody>
      </Table>

      {canEdit ? (
        <div className="grid gap-3 rounded-xl border border-dashed border-blue-300 bg-blue-50/40 p-4 md:grid-cols-2">
          <Field label="ระดับ Scope">
            <select
              className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm"
              value={form.scope_type}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  role_id: "",
                  scope_type: event.target.value as RoleScope,
                  brand_id: "",
                  branch_id: "",
                  station_key: ""
                }))
              }
            >
              <option value="company">Company</option>
              <option value="brand">Brand</option>
              <option value="branch">Branch</option>
              <option value="station">Kitchen station</option>
            </select>
          </Field>
          <Field label="บทบาท">
            <select
              className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm"
              value={form.role_id}
              onChange={(event) => setForm((current) => ({ ...current, role_id: event.target.value }))}
            >
              <option value="">เลือกบทบาท</option>
              {eligibleRoles.map((role) => <option key={role.id} value={role.id}>{role.name}</option>)}
            </select>
          </Field>
          {form.scope_type === "company" ? (
            <Field label="Company"><Input value={options?.company.name ?? ""} disabled /></Field>
          ) : null}
          {form.scope_type === "brand" ? (
            <Field label="Brand">
              <select
                className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm"
                value={form.brand_id}
                onChange={(event) => setForm((current) => ({ ...current, brand_id: event.target.value }))}
              >
                <option value="">เลือก Brand</option>
                {options?.brands.map((brand) => <option key={brand.id} value={brand.id}>{brand.name}</option>)}
              </select>
            </Field>
          ) : null}
          {["branch", "station"].includes(form.scope_type) ? (
            <Field label="Branch">
              <select
                className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm"
                value={form.branch_id}
                onChange={(event) => setForm((current) => ({ ...current, branch_id: event.target.value, station_key: "" }))}
              >
                <option value="">เลือก Branch</option>
                {options?.branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.code} · {branch.name}</option>)}
              </select>
            </Field>
          ) : null}
          {form.scope_type === "station" ? (
            <Field label="Kitchen station">
              <select
                className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm"
                value={form.station_key}
                onChange={(event) => setForm((current) => ({ ...current, station_key: event.target.value }))}
              >
                <option value="">เลือก station</option>
                {selectedBranch?.stations.map((station) => <option key={station} value={station}>{station}</option>)}
              </select>
            </Field>
          ) : null}
          <Field label="เหตุผล">
            <Input
              value={form.reason}
              placeholder="เช่น รับผิดชอบสาขานี้ตั้งแต่ 1 ส.ค."
              onChange={(event) => setForm((current) => ({ ...current, reason: event.target.value }))}
            />
          </Field>
          <div className="flex items-end justify-end">
            <Button
              onClick={() => createMutation.mutate()}
              disabled={
                !form.role_id || !targetReady || !form.reason.trim() || createMutation.isPending
              }
            >
              เพิ่ม Role scope
            </Button>
          </div>
        </div>
      ) : null}
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
