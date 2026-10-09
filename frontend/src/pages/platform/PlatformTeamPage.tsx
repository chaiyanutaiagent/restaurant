import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { AlertTriangle, CheckCircle2, Copy, CopyPlus, KeyRound, Pencil, Plus, RefreshCw, ShieldAlert, ShieldCheck, UserPlus, Users, X } from "lucide-react";
import { type FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { platformApi, platformErrorMessage } from "@/lib/platformApi";
import { usePlatformAuthStore } from "@/stores/platform-auth.store";
import type { PlatformPermissionDefinition, PlatformRoleCode, PlatformRoleDefinition, PlatformTeamOperator } from "@/types/platform";

const roleFallback: Array<{ code: PlatformRoleCode; label: string }> = [
  { code: "platform_owner", label: "Platform Owner" },
  { code: "operations", label: "Operations" },
  { code: "support", label: "Support" },
  { code: "billing", label: "Billing" },
  { code: "security", label: "Security" },
  { code: "auditor", label: "Auditor" },
];

const hasPermission = (permissions: string[], required: string) =>
  permissions.includes("*") || permissions.includes(required);

type RoleDraft = {
  mode: "create" | "edit";
  code: string;
  label: string;
  description: string;
  permissions: string[];
  isActive: boolean;
  reason: string;
  version: number;
};

export default function PlatformTeamPage(): JSX.Element {
  const operator = usePlatformAuthStore((state) => state.operator);
  const environment = operator?.environment ?? "uat";
  const canView = hasPermission(operator?.permissions ?? [], "platform.team.view");
  const canManage = hasPermission(operator?.permissions ?? [], "platform.team.manage");
  const canRevokeSessions = hasPermission(operator?.permissions ?? [], "platform.security.session.revoke");
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [online, setOnline] = useState(() => navigator.onLine);
  const [search, setSearch] = useState("");
  const [reason, setReason] = useState("");
  const [roleCode, setRoleCode] = useState<PlatformRoleCode>("support");
  const [invite, setInvite] = useState({ username: "", email: "", displayName: "", roleCode: "support" as PlatformRoleCode, reason: "" });
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const [roleDraft, setRoleDraft] = useState<RoleDraft | null>(null);

  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => { window.removeEventListener("online", update); window.removeEventListener("offline", update); };
  }, []);

  const team = useQuery({
    queryKey: ["platform", "team", environment],
    queryFn: async () => (await platformApi.teamOperators(environment)).data.data,
    enabled: canView && online,
  });
  const roles = useQuery({
    queryKey: ["platform", "roles", environment],
    queryFn: async () => (await platformApi.platformRoles(environment)).data.data,
    enabled: canView && online,
  });
  const permissionCatalog = useQuery({
    queryKey: ["platform", "permissions"],
    queryFn: async () => (await platformApi.platformPermissions()).data.data,
    enabled: canView && online,
  });
  const selectedId = searchParams.get("operator");
  const selected = team.data?.find((item) => item.id === selectedId) ?? null;
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return team.data ?? [];
    return (team.data ?? []).filter((item) =>
      [item.display_name, item.username, item.email ?? "", ...item.role_codes]
        .some((value) => value.toLowerCase().includes(needle))
    );
  }, [search, team.data]);

  const refreshTeam = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["platform", "team", environment] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "roles", environment] }),
    ]);
  };
  const roleMutation = useMutation({
    mutationFn: async (draft: RoleDraft) => {
      if (draft.mode === "create") {
        return (await platformApi.createPlatformRole({
          code: draft.code,
          label: draft.label,
          description: draft.description || null,
          permissions: draft.permissions,
          environment,
          reason: draft.reason,
          request_id: crypto.randomUUID(),
        })).data.data;
      }
      return (await platformApi.updatePlatformRole(draft.code, {
        label: draft.label,
        description: draft.description || null,
        permissions: draft.permissions,
        is_active: draft.isActive,
        environment,
        reason: draft.reason,
        request_id: crypto.randomUUID(),
        expected_version: draft.version,
      })).data.data;
    },
    onSuccess: async () => {
      setRoleDraft(null);
      await queryClient.invalidateQueries({ queryKey: ["platform", "roles", environment] });
    },
  });
  const inviteMutation = useMutation({
    mutationFn: async () => (await platformApi.inviteTeamOperator({
      username: invite.username,
      email: invite.email,
      display_name: invite.displayName,
      role_code: invite.roleCode,
      environment,
      reason: invite.reason,
      request_id: crypto.randomUUID(),
    })).data.data,
    onSuccess: (result) => {
      setInviteLink(result.deep_link);
      setInvite({ username: "", email: "", displayName: "", roleCode: "support", reason: "" });
    },
  });
  const action = useMutation({
    mutationFn: async ({ kind, target }: { kind: "assign" | "revoke" | "state" | "review" | "sessions"; target: PlatformTeamOperator }) => {
      const requestId = crypto.randomUUID();
      if (kind === "assign") return (await platformApi.assignTeamRole(target.id, { role_code: roleCode, environment, reason, request_id: requestId, expected_credential_version: target.credential_version })).data.data;
      if (kind === "revoke") return (await platformApi.revokeTeamRole(target.id, { role_code: roleCode, environment, reason, request_id: requestId, expected_credential_version: target.credential_version })).data.data;
      if (kind === "state") return (await platformApi.setTeamOperatorState(target.id, { active: !target.is_active, reason, request_id: requestId, expected_credential_version: target.credential_version })).data.data;
      if (kind === "review") {
        const due = new Date(); due.setDate(due.getDate() + 90);
        return (await platformApi.certifyTeamAccess(target.id, { reason, request_id: requestId, expected_credential_version: target.credential_version, next_review_due_at: due.toISOString() })).data.data;
      }
      await platformApi.revokeTeamSessions(target.id, { environment, reason, request_id: requestId });
      return target;
    },
    onSuccess: async () => { setReason(""); await refreshTeam(); },
  });
  const error = team.error ?? roles.error ?? permissionCatalog.error ?? roleMutation.error ?? inviteMutation.error ?? action.error;
  const permissionDenied = axios.isAxiosError(error) && error.response?.status === 403;

  if (!canView || permissionDenied) {
    return <StatePanel icon={<ShieldAlert className="h-8 w-8" />} title="ไม่มีสิทธิ์ดู Team & Roles" detail="บัญชีนี้ไม่ได้รับ platform.team.view ระบบฝั่งเซิร์ฟเวอร์จะปฏิเสธคำขอโดยอัตโนมัติ" tone="red" />;
  }
  if (!online) {
    return <StatePanel icon={<AlertTriangle className="h-8 w-8" />} title="ออฟไลน์" detail="Team & Roles เป็นข้อมูลความปลอดภัย จึงไม่แสดงข้อมูล cache และไม่อนุญาตให้แก้ไขจนกว่าจะเชื่อมต่อใหม่" tone="amber" />;
  }

  const submitInvite = (event: FormEvent) => { event.preventDefault(); inviteMutation.mutate(); };
  const activeRoleOptions = roles.data?.filter((role) => role.is_active !== false) ?? [];
  const roleOptions = activeRoleOptions.length ? activeRoleOptions : roleFallback;
  const startRoleCreate = (source?: PlatformRoleDefinition) => {
    setRoleDraft({
      mode: "create",
      code: "",
      label: source ? `${source.label} (สำเนา)` : "",
      description: source?.description ?? "",
      permissions: source?.permissions.filter((permission) => permission !== "*") ?? [],
      isActive: true,
      reason: source ? `คัดลอกจาก ${source.label}` : "",
      version: 1,
    });
  };
  const startRoleEdit = (role: PlatformRoleDefinition) => {
    setRoleDraft({
      mode: "edit",
      code: role.code,
      label: role.label,
      description: role.description ?? "",
      permissions: role.permissions,
      isActive: role.is_active,
      reason: "",
      version: role.version,
    });
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-emerald-300">Platform identity · {environment.toUpperCase()}</p>
          <h2 className="mt-1 text-3xl font-bold">Team & Roles</h2>
          <p className="mt-2 text-sm text-slate-400">บัญชีส่วนบุคคล, MFA/session visibility, least privilege และ quarterly access review</p>
        </div>
        <Button variant="outline" onClick={() => void refreshTeam()} disabled={team.isFetching}><RefreshCw className={`h-4 w-4 ${team.isFetching ? "animate-spin" : ""}`} />รีเฟรช</Button>
      </header>

      {error && !permissionDenied ? <StatePanel icon={<AlertTriangle className="h-6 w-6" />} title="โหลดข้อมูลไม่สำเร็จ" detail={platformErrorMessage(error)} tone="red" compact /> : null}
      {team.isLoading ? <div className="grid gap-4 lg:grid-cols-3">{[0, 1, 2].map((item) => <div key={item} className="h-44 animate-pulse rounded-2xl bg-slate-900" />)}</div> : null}

      <section className="rounded-2xl border border-slate-700 bg-slate-900 p-5 md:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <ShieldCheck className="mt-0.5 h-6 w-6 text-emerald-300" />
            <div>
              <h3 className="text-lg font-semibold">Role และสิทธิ์ของเจ้าหน้าที่</h3>
              <p className="mt-1 text-sm text-slate-400">Role มาตรฐานแก้ไม่ได้ แต่คัดลอกเป็น Role ใหม่แล้วเลือกสิทธิ์ให้เหมาะกับงานได้</p>
            </div>
          </div>
          {canManage ? <Button type="button" className="bg-emerald-400 text-slate-950 hover:bg-emerald-300" onClick={() => startRoleCreate()}><Plus className="h-4 w-4" />สร้าง Role ใหม่</Button> : null}
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(roles.data ?? []).map((role) => (
            <article key={role.code} className={`rounded-xl border p-4 ${role.is_active ? "border-slate-700 bg-slate-950" : "border-slate-800 bg-slate-950/40 opacity-70"}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="font-semibold">{role.label}</h4>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${role.is_system ? "bg-sky-950 text-sky-300" : "bg-violet-950 text-violet-300"}`}>{role.is_system ? "มาตรฐาน" : "กำหนดเอง"}</span>
                    {!role.is_active ? <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-300">ปิดใช้งาน</span> : null}
                  </div>
                  <p className="mt-1 font-mono text-[11px] text-slate-500">{role.code}</p>
                </div>
                {canManage ? role.is_system
                  ? <Button type="button" size="sm" variant="outline" onClick={() => startRoleCreate(role)}><CopyPlus className="h-4 w-4" />คัดลอก</Button>
                  : <Button type="button" size="sm" variant="outline" onClick={() => startRoleEdit(role)}><Pencil className="h-4 w-4" />แก้ไข</Button>
                  : null}
              </div>
              <p className="mt-3 min-h-10 text-sm text-slate-400">{role.description || "ไม่มีคำอธิบาย"}</p>
              <p className="mt-3 text-xs text-slate-300">{role.permissions.includes("*") ? "ควบคุมระบบทั้งหมด" : `${role.permissions.length} สิทธิ์`}</p>
            </article>
          ))}
        </div>

        {canManage && roleDraft ? (
          <RoleBuilder
            draft={roleDraft}
            permissions={permissionCatalog.data ?? []}
            saving={roleMutation.isPending}
            onChange={setRoleDraft}
            onCancel={() => setRoleDraft(null)}
            onSave={() => roleMutation.mutate(roleDraft)}
          />
        ) : null}
      </section>

      {canManage ? (
        <section className="rounded-2xl border border-slate-700 bg-slate-900 p-5 md:p-6">
          <div className="flex items-center gap-3"><UserPlus className="h-6 w-6 text-emerald-300" /><div><h3 className="text-lg font-semibold">เชิญ Platform operator</h3><p className="text-sm text-slate-400">ลิงก์จะแสดงครั้งเดียวและหมดอายุใน 24 ชั่วโมง</p></div></div>
          <form onSubmit={submitInvite} className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-6">
            <Field label="ชื่อที่แสดง"><Input value={invite.displayName} onChange={(event) => setInvite({ ...invite, displayName: event.target.value })} required /></Field>
            <Field label="Username"><Input value={invite.username} onChange={(event) => setInvite({ ...invite, username: event.target.value })} required minLength={3} /></Field>
            <Field label="Email"><Input type="email" value={invite.email} onChange={(event) => setInvite({ ...invite, email: event.target.value })} required /></Field>
            <Field label="Role"><select className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 text-sm" value={invite.roleCode} onChange={(event) => setInvite({ ...invite, roleCode: event.target.value as PlatformRoleCode })}>{roleOptions.map((role) => <option key={role.code} value={role.code}>{role.label}</option>)}</select></Field>
            <Field label="เหตุผล"><Input value={invite.reason} onChange={(event) => setInvite({ ...invite, reason: event.target.value })} required /></Field>
            <div className="flex items-end"><Button className="w-full bg-emerald-400 text-slate-950 hover:bg-emerald-300" disabled={inviteMutation.isPending}>สร้างคำเชิญ</Button></div>
          </form>
          {inviteLink ? <div className="mt-4 flex flex-col gap-3 rounded-xl border border-amber-700 bg-amber-950/30 p-4 sm:flex-row sm:items-center"><p className="min-w-0 flex-1 break-all font-mono text-xs text-amber-100">{inviteLink}</p><Button type="button" variant="outline" onClick={() => void navigator.clipboard.writeText(inviteLink)}><Copy className="h-4 w-4" />คัดลอก</Button></div> : null}
        </section>
      ) : null}

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(360px,0.8fr)]">
        <div className="rounded-2xl border border-slate-700 bg-slate-900 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-3"><Users className="h-6 w-6 text-sky-300" /><h3 className="text-lg font-semibold">Operators ({team.data?.length ?? 0})</h3></div><Input className="max-w-xs" placeholder="ค้นหาชื่อ, email หรือ role" value={search} onChange={(event) => setSearch(event.target.value)} /></div>
          {!team.isLoading && filtered.length === 0 ? <StatePanel icon={<Users className="h-7 w-7" />} title="ยังไม่มี operator" detail="สร้างคำเชิญแรกเพื่อเพิ่มผู้ดูแล โดยระบบจะรักษา Platform Owner อย่างน้อยหนึ่งคนเสมอ" tone="slate" compact /> : null}
          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {filtered.map((item) => <button key={item.id} type="button" onClick={() => setSearchParams({ operator: item.id })} className={`rounded-xl border p-4 text-left transition ${selectedId === item.id ? "border-emerald-400 bg-emerald-950/20" : "border-slate-700 bg-slate-950 hover:border-slate-500"}`}>
              <div className="flex items-start justify-between gap-3"><div><p className="font-semibold">{item.display_name}</p><p className="text-xs text-slate-400">@{item.username} · {item.email || "ไม่มี email"}</p></div><span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${item.is_active ? "bg-emerald-950 text-emerald-300" : "bg-slate-800 text-slate-400"}`}>{item.is_active ? "ACTIVE" : "INACTIVE"}</span></div>
              <div className="mt-3 flex flex-wrap gap-2">{item.role_codes.map((role) => <span key={role} className="rounded-full bg-sky-950 px-2 py-1 text-xs text-sky-200">{roleOptions.find((option) => option.code === role)?.label ?? role}</span>)}</div>
              <div className="mt-3 flex flex-wrap gap-3 text-xs"><span className={item.mfa_enabled ? "text-emerald-300" : "text-amber-300"}>MFA {item.mfa_enabled ? "ON" : "OFF"}</span><span className="text-slate-400">{item.active_session_count} sessions</span>{item.review_due ? <span className="text-amber-300">Review due</span> : null}{item.stale_access ? <span className="text-red-300">Stale</span> : null}</div>
            </button>)}
          </div>
        </div>

        <aside className="h-fit rounded-2xl border border-slate-700 bg-slate-900 p-5 xl:sticky xl:top-24">
          {selected ? <>
            <div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wider text-emerald-300">Operator governance</p><h3 className="mt-1 text-xl font-semibold">{selected.display_name}</h3><p className="text-xs text-slate-400">Credential version {selected.credential_version} · {environment.toUpperCase()}</p></div>{selected.mfa_enabled ? <ShieldCheck className="h-7 w-7 text-emerald-300" /> : <ShieldAlert className="h-7 w-7 text-amber-300" />}</div>
            <dl className="mt-5 grid grid-cols-2 gap-3 text-sm"><Metric label="Last login" value={selected.last_login_at ? new Date(selected.last_login_at).toLocaleDateString("th-TH") : "Never"} /><Metric label="Review due" value={selected.access_review_due_at ? new Date(selected.access_review_due_at).toLocaleDateString("th-TH") : "Due now"} /><Metric label="MFA" value={selected.mfa_enabled ? "Enabled" : "Missing"} /><Metric label="Sessions" value={String(selected.active_session_count)} /></dl>
            {canManage || canRevokeSessions ? <div className="mt-5 space-y-4 border-t border-slate-700 pt-5"><Field label="เหตุผลของการเปลี่ยนแปลง"><Input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="จำเป็นสำหรับ audit" /></Field><Field label="Role"><select className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 text-sm" value={roleCode} onChange={(event) => setRoleCode(event.target.value as PlatformRoleCode)}>{roleOptions.map((role) => <option key={role.code} value={role.code}>{role.label}</option>)}</select></Field><div className="grid gap-2 sm:grid-cols-2">
              {canManage ? <><Button variant="outline" disabled={!reason || action.isPending} onClick={() => action.mutate({ kind: "assign", target: selected })}>เพิ่ม role</Button><Button variant="outline" disabled={!reason || action.isPending} onClick={() => action.mutate({ kind: "revoke", target: selected })}>ถอน role</Button><Button variant="outline" disabled={!reason || action.isPending} onClick={() => action.mutate({ kind: "review", target: selected })}><CheckCircle2 className="h-4 w-4" />รับรอง 90 วัน</Button><Button variant={selected.is_active ? "destructive" : "outline"} disabled={!reason || action.isPending} onClick={() => action.mutate({ kind: "state", target: selected })}>{selected.is_active ? "ปิดบัญชี" : "เปิดบัญชี"}</Button></> : null}
              {canRevokeSessions ? <Button className="sm:col-span-2" variant="destructive" disabled={!reason || action.isPending || selected.active_session_count === 0} onClick={() => action.mutate({ kind: "sessions", target: selected })}><KeyRound className="h-4 w-4" />เพิกถอนทุก session</Button> : null}
            </div></div> : <p className="mt-5 rounded-xl bg-slate-950 p-4 text-sm text-slate-400">บัญชีนี้ดูข้อมูลได้อย่างเดียว</p>}
          </> : <StatePanel icon={<Users className="h-7 w-7" />} title="เลือก operator" detail="เลือกจากรายการเพื่อดู MFA, sessions, stale access และ access review" tone="slate" compact />}
        </aside>
      </section>
    </div>
  );
}

function RoleBuilder({
  draft,
  permissions,
  saving,
  onChange,
  onCancel,
  onSave,
}: {
  draft: RoleDraft;
  permissions: PlatformPermissionDefinition[];
  saving: boolean;
  onChange: (draft: RoleDraft) => void;
  onCancel: () => void;
  onSave: () => void;
}): JSX.Element {
  const groups = useMemo(() => {
    const result = new Map<string, { label: string; items: PlatformPermissionDefinition[] }>();
    permissions.forEach((permission) => {
      const group = result.get(permission.group) ?? { label: permission.group_label, items: [] };
      group.items.push(permission);
      result.set(permission.group, group);
    });
    return Array.from(result.entries());
  }, [permissions]);
  const togglePermission = (code: string, selected: boolean) => {
    const next = selected
      ? Array.from(new Set([...draft.permissions, code])).sort()
      : draft.permissions.filter((permission) => permission !== code);
    onChange({ ...draft, permissions: next });
  };
  const codeValid = /^[a-z][a-z0-9_]{2,39}$/.test(draft.code);
  const saveDisabled = saving || !draft.label.trim() || !draft.reason.trim() || draft.permissions.length === 0 || !codeValid;

  return (
    <div className="mt-6 rounded-2xl border border-emerald-700 bg-emerald-950/10 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-emerald-300">{draft.mode === "create" ? "สร้าง Role กำหนดเอง" : "แก้ไข Role กำหนดเอง"}</p>
          <h4 className="mt-1 text-xl font-semibold">กำหนดขอบเขตงาน</h4>
          <p className="mt-1 text-sm text-slate-400">เลือกเฉพาะสิทธิ์ที่ตำแหน่งนี้จำเป็นต้องใช้ การเปลี่ยนสิทธิ์จะบังคับให้ผู้ใช้ Role นี้เข้าสู่ระบบใหม่</p>
        </div>
        <Button type="button" size="icon" variant="outline" aria-label="ปิด" onClick={onCancel}><X className="h-4 w-4" /></Button>
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <Field label="ชื่อ Role ที่แสดง"><Input value={draft.label} onChange={(event) => onChange({ ...draft, label: event.target.value })} placeholder="เช่น เจ้าหน้าที่ดูแลลูกค้า" /></Field>
        <Field label="รหัส Role (อังกฤษ)"><Input value={draft.code} onChange={(event) => onChange({ ...draft, code: event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })} placeholder="เช่น customer_care" disabled={draft.mode === "edit"} /><p className={`text-xs ${codeValid ? "text-slate-500" : "text-amber-300"}`}>ใช้ a-z, 0-9 และ _ ความยาว 3–40 ตัว</p></Field>
        <Field label="คำอธิบาย"><textarea className="min-h-24 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-emerald-400" value={draft.description} onChange={(event) => onChange({ ...draft, description: event.target.value })} placeholder="ตำแหน่งนี้รับผิดชอบงานอะไร" /></Field>
        <Field label="เหตุผลที่สร้างหรือแก้ไข"><textarea className="min-h-24 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-emerald-400" value={draft.reason} onChange={(event) => onChange({ ...draft, reason: event.target.value })} placeholder="บันทึกไว้ใน Audit Log" /></Field>
      </div>

      <div className="mt-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h5 className="font-semibold">สิทธิ์ที่อนุญาต ({draft.permissions.length})</h5>
          <p className="text-xs text-slate-400">สีแดงคือการเปลี่ยนข้อมูลสำคัญ ควรให้เฉพาะผู้รับผิดชอบ</p>
        </div>
        <div className="mt-3 grid gap-4 lg:grid-cols-2">
          {groups.map(([groupCode, group]) => (
            <fieldset key={groupCode} className="rounded-xl border border-slate-700 bg-slate-950 p-4">
              <legend className="px-2 text-sm font-semibold text-sky-200">{group.label}</legend>
              <div className="space-y-3">
                {group.items.map((permission) => {
                  const selected = draft.permissions.includes(permission.code);
                  const riskStyle = permission.risk === "critical" ? "bg-red-950 text-red-300" : permission.risk === "sensitive" ? "bg-amber-950 text-amber-300" : "bg-slate-800 text-slate-300";
                  const riskLabel = permission.risk === "critical" ? "สำคัญมาก" : permission.risk === "sensitive" ? "ข้อมูลสำคัญ" : "ทั่วไป";
                  return <label key={permission.code} className="flex cursor-pointer items-start gap-3 rounded-lg p-2 hover:bg-slate-900">
                    <input type="checkbox" className="mt-1 h-4 w-4 accent-emerald-400" checked={selected} onChange={(event) => togglePermission(permission.code, event.target.checked)} />
                    <span className="min-w-0 flex-1"><span className="text-sm text-slate-100">{permission.label}</span><span className="mt-1 block break-all font-mono text-[10px] text-slate-500">{permission.code}</span></span>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] ${riskStyle}`}>{riskLabel}</span>
                  </label>;
                })}
              </div>
            </fieldset>
          ))}
        </div>
      </div>

      {draft.mode === "edit" ? <label className="mt-5 flex items-start gap-3 rounded-xl border border-slate-700 bg-slate-950 p-4"><input type="checkbox" className="mt-1 h-4 w-4 accent-emerald-400" checked={draft.isActive} onChange={(event) => onChange({ ...draft, isActive: event.target.checked })} /><span><span className="block font-medium">เปิดให้มอบหมาย Role นี้</span><span className="text-xs text-slate-400">หากมีผู้ใช้หรือคำเชิญค้างอยู่ ระบบจะไม่ยอมให้ปิดจนกว่าจะย้าย Role ให้เรียบร้อย</span></span></label> : null}

      <div className="mt-5 flex flex-wrap justify-end gap-3">
        <Button type="button" variant="outline" onClick={onCancel}>ยกเลิก</Button>
        <Button type="button" className="bg-emerald-400 text-slate-950 hover:bg-emerald-300" disabled={saveDisabled} onClick={onSave}>{saving ? "กำลังบันทึก…" : "บันทึก Role"}</Button>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }): JSX.Element { return <div className="space-y-2"><Label>{label}</Label>{children}</div>; }
function Metric({ label, value }: { label: string; value: string }): JSX.Element { return <div className="rounded-xl bg-slate-950 p-3"><dt className="text-xs text-slate-500">{label}</dt><dd className="mt-1 font-medium">{value}</dd></div>; }
function StatePanel({ icon, title, detail, tone, compact = false }: { icon: ReactNode; title: string; detail: string; tone: "red" | "amber" | "slate"; compact?: boolean }): JSX.Element {
  const style = tone === "red" ? "border-red-900 bg-red-950/30 text-red-100" : tone === "amber" ? "border-amber-800 bg-amber-950/30 text-amber-100" : "border-slate-700 bg-slate-950 text-slate-200";
  return <section className={`${compact ? "mt-4 p-5" : "p-8"} rounded-2xl border ${style}`}><div className="flex items-start gap-3">{icon}<div><h3 className="font-semibold">{title}</h3><p className="mt-1 text-sm opacity-80">{detail}</p></div></div></section>;
}
