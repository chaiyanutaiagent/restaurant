import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDownUp,
  Clock3,
  History,
  Loader2,
  RefreshCw,
  Search,
  Server,
  UserRound,
  WifiOff,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { userApi } from "@/lib/adminApi";
import { formatThaiCurrency } from "@/lib/cartUtils";
import { posApi } from "@/lib/posApi";
import type { UserDetail } from "@/types/admin";
import type { HeldSaleDraft, HoldDraftAuditEntry } from "@/types/pos";

type HoldFilter = "active" | "mine" | "counter" | "history";
type HoldSort = "updated_desc" | "oldest" | "expiring";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  drafts: HeldSaleDraft[];
  isLoading: boolean;
  isError: boolean;
  isOnline: boolean;
  canView: boolean;
  canCreate: boolean;
  canResume: boolean;
  canDiscard: boolean;
  canReassign: boolean;
  currentUserId?: string;
  branchId?: string | null;
  hasCounter: boolean;
  busyId: string | null;
  search: string;
  onSearchChange: (value: string) => void;
  filter: HoldFilter;
  onFilterChange: (value: HoldFilter) => void;
  onRetry: () => void;
  onCreate: () => void;
  onResume: (draft: HeldSaleDraft) => Promise<void>;
  onRelease: (draft: HeldSaleDraft) => Promise<void>;
  onDiscard: (draft: HeldSaleDraft, reason: string) => Promise<void>;
  onReassign: (draft: HeldSaleDraft, userId: string, reason: string) => Promise<void>;
  onReopen: (draft: HeldSaleDraft) => Promise<void>;
};

const statusLabels: Record<string, string> = {
  active: "พร้อมเรียกกลับ",
  claimed: "มีผู้กำลังเปิด",
  resumed: "เรียกกลับแล้ว",
  expired: "หมดอายุ",
  converted: "ขายสำเร็จแล้ว",
  cancelled: "ยกเลิกแล้ว",
};

const actionLabels: Record<string, string> = {
  create: "สร้างบิลพัก",
  update: "แก้ไข",
  reassign: "มอบหมายใหม่",
  claim: "เริ่มเรียกกลับ",
  release: "ปล่อยสิทธิ์เรียกกลับ",
  resume: "เรียกกลับสำเร็จ",
  discard: "ยกเลิก",
  reopen: "สร้างบิลกู้คืน",
  expire: "หมดอายุ",
  claim_expire: "สิทธิ์เรียกกลับหมดเวลา",
  convert: "แปลงเป็นบิลขาย",
};

function totalOf(draft: HeldSaleDraft): number {
  const subtotal = draft.items.reduce((sum, item) => sum + Number(item.subtotal), 0);
  return Math.max(subtotal - Number(draft.order_discount) - Number(draft.loyalty_discount), 0);
}

function itemCountOf(draft: HeldSaleDraft): number {
  return draft.items.reduce((sum, item) => sum + Number(item.qty), 0);
}

function ageLabel(value: number): string {
  const minutes = Math.max(Math.floor((Date.now() - value) / 60_000), 0);
  if (minutes < 60) return `${minutes} นาที`;
  const hours = Math.floor(minutes / 60);
  return `${hours} ชม. ${minutes % 60} นาที`;
}

function expiryLabel(value?: string): string {
  if (!value) return "ไม่ระบุ";
  const minutes = Math.ceil((new Date(value).getTime() - Date.now()) / 60_000);
  if (minutes <= 0) return "หมดอายุแล้ว";
  if (minutes < 60) return `อีก ${minutes} นาที`;
  return `อีก ${Math.floor(minutes / 60)} ชม. ${minutes % 60} นาที`;
}

function lifecycleAt(draft: HeldSaleDraft): string | null {
  return draft.converted_at ?? draft.cancelled_at ?? draft.expired_at ?? draft.resumed_at ?? null;
}

export default function HoldDraftWorkspaceDialog(props: Props): JSX.Element {
  const [sort, setSort] = useState<HoldSort>("updated_desc");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [assigneeId, setAssigneeId] = useState("");

  const sortedDrafts = useMemo(() => [...props.drafts].sort((left, right) => {
    if (sort === "oldest") return left.held_at - right.held_at;
    if (sort === "expiring") {
      return new Date(left.expires_at ?? "9999-12-31").getTime() - new Date(right.expires_at ?? "9999-12-31").getTime();
    }
    return right.held_at - left.held_at;
  }), [props.drafts, sort]);

  const selected = sortedDrafts.find((draft) => draft.id === selectedId) ?? sortedDrafts[0] ?? null;

  useEffect(() => {
    if (!props.open) return;
    if (selectedId && props.drafts.some((draft) => draft.id === selectedId)) return;
    setSelectedId(props.drafts[0]?.id ?? null);
  }, [props.drafts, props.open, selectedId]);

  useEffect(() => {
    setReason("");
    setAssigneeId(selected?.assignee_user_id ?? "");
  }, [selected?.id, selected?.assignee_user_id]);

  const auditQuery = useQuery({
    queryKey: ["pos", "hold-draft-audit", selected?.server_id],
    queryFn: async () => (await posApi.getHoldDraftAudit(selected?.server_id ?? "")).data.data,
    enabled: props.open && props.isOnline && Boolean(selected?.server_backed && selected.server_id && props.canView),
  });

  const usersQuery = useQuery({
    queryKey: ["pos", "hold-draft-assignees", props.branchId],
    queryFn: async () => (await userApi.list({ branch_id: props.branchId ?? undefined, is_active: true, page: 1, limit: 100 })).data.data,
    enabled: props.open && props.isOnline && props.canReassign && Boolean(props.branchId),
    retry: false,
  });

  const active = selected && (!selected.status || selected.status === "active");
  const claimedByMe = selected?.status === "claimed" && selected.claimed_by === props.currentUserId;
  const historical = selected?.status === "resumed" || selected?.status === "expired" || selected?.status === "cancelled";
  const auditRows = (auditQuery.data ?? []) as HoldDraftAuditEntry[];
  const users = (usersQuery.data ?? []) as UserDetail[];

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className="max-h-[94vh] max-w-7xl overflow-hidden p-0">
        <DialogHeader className="border-b border-slate-200 px-5 py-4">
          <DialogTitle className="flex flex-wrap items-center gap-2 text-xl">
            บิลที่พักไว้
            <span className={`rounded-full px-3 py-1 text-xs font-bold ${props.isOnline ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-900"}`}>
              {props.isOnline ? "Server เป็นข้อมูลหลัก · ทุก Counter" : "ออฟไลน์ · เฉพาะเครื่องนี้"}
            </span>
          </DialogTitle>
          <DialogDescription>
            บิลพักยังไม่ส่ง KDS ไม่ตัดสต๊อก ไม่สร้างภาษี และยังไม่รับชำระ
          </DialogDescription>
        </DialogHeader>

        <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(340px,0.9fr)_minmax(420px,1.1fr)]">
          <section className="min-h-0 border-b border-slate-200 p-4 lg:border-b-0 lg:border-r" aria-label="รายการบิลที่พักไว้">
            <div className="grid gap-2 sm:grid-cols-[1fr_180px]">
              <label className="relative">
                <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
                <Input
                  className="h-12 pl-11"
                  placeholder="ค้นหา Draft ชื่อ ลูกค้า โต๊ะ หรือคิว"
                  value={props.search}
                  onChange={(event) => props.onSearchChange(event.target.value)}
                />
              </label>
              <label className="relative">
                <ArrowDownUp className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <select
                  className="h-12 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm"
                  value={sort}
                  onChange={(event) => setSort(event.target.value as HoldSort)}
                  aria-label="เรียงบิลพัก"
                >
                  <option value="updated_desc">ล่าสุดก่อน</option>
                  <option value="oldest">เก่าสุดก่อน</option>
                  <option value="expiring">ใกล้หมดอายุก่อน</option>
                </select>
              </label>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4" role="tablist" aria-label="กรองบิลที่พักไว้">
              {([
                ["active", "ใช้งานได้"],
                ["mine", "ของฉัน"],
                ["counter", "Counter นี้"],
                ["history", "ประวัติ"],
              ] as const).map(([value, label]) => (
                <Button
                  key={value}
                  type="button"
                  variant={props.filter === value ? "default" : "outline"}
                  className="h-11 px-2"
                  disabled={value === "counter" && !props.hasCounter}
                  onClick={() => props.onFilterChange(value)}
                  role="tab"
                  aria-selected={props.filter === value}
                >
                  {label}
                </Button>
              ))}
            </div>

            {!props.isOnline ? (
              <div className="mt-3 flex gap-2 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
                <WifiOff className="mt-0.5 h-5 w-5 shrink-0" />
                <span>แสดงเฉพาะ Local shadow เครื่องนี้ ห้ามชำระเงิน ตัดสต๊อก หรือส่งครัวจนกว่าจะเชื่อมต่อและตรวจสอบ</span>
              </div>
            ) : null}

            <div className="mt-3 max-h-[52vh] space-y-2 overflow-y-auto pr-1 lg:max-h-[62vh]">
              {!props.canView && props.isOnline ? (
                <StateBox icon={<AlertTriangle className="h-6 w-6" />} text="ไม่มีสิทธิ์ดูบิลพักของสาขา" />
              ) : props.isLoading ? (
                [1, 2, 3].map((item) => <div key={item} className="h-28 animate-pulse rounded-2xl bg-slate-100" />)
              ) : props.isError ? (
                <StateBox
                  icon={<AlertTriangle className="h-6 w-6" />}
                  text="โหลดข้อมูลล่าสุดไม่สำเร็จ ตะกร้าปัจจุบันไม่ถูกเปลี่ยน"
                  action={<Button className="h-11" variant="outline" onClick={props.onRetry}><RefreshCw className="h-4 w-4" />ลองใหม่</Button>}
                />
              ) : sortedDrafts.length === 0 ? (
                <StateBox icon={<Server className="h-6 w-6" />} text={props.search ? "ไม่พบบิลที่ตรงกับคำค้น" : "ยังไม่มีบิลที่พักไว้ในมุมมองนี้"} />
              ) : sortedDrafts.map((draft) => {
                const isSelected = selected?.id === draft.id;
                return (
                  <button
                    key={draft.id}
                    type="button"
                    onClick={() => setSelectedId(draft.id)}
                    className={`min-h-28 w-full rounded-2xl border p-4 text-left transition ${isSelected ? "border-blue-500 bg-blue-50 ring-2 ring-blue-100" : "border-slate-200 bg-white hover:border-slate-300"}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate font-bold text-slate-950">{draft.label}</div>
                        <div className="mt-1 flex flex-wrap gap-1.5 text-xs">
                          <span className="rounded-full bg-slate-100 px-2 py-1 font-semibold text-slate-700">{draft.draft_no ?? "LOCAL"}</span>
                          <span className="rounded-full bg-blue-100 px-2 py-1 font-semibold text-blue-800">{statusLabels[draft.status ?? "active"] ?? draft.status}</span>
                          <span className={`rounded-full px-2 py-1 font-semibold ${draft.server_backed ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-900"}`}>
                            {draft.server_backed ? "ทุก Counter" : draft.sync_state === "needs_review" ? "รอตรวจสอบ" : "เครื่องนี้"}
                          </span>
                        </div>
                      </div>
                      <span className="shrink-0 text-sm font-black text-slate-950">{formatThaiCurrency(totalOf(draft))}</span>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600">
                      <span>{itemCountOf(draft)} ชิ้น · อายุ {ageLabel(draft.held_at)}</span>
                      <span className="text-right">หมดอายุ {expiryLabel(draft.expires_at)}</span>
                      <span className="truncate">{draft.owner_display ?? "เจ้าของไม่ระบุ"}</span>
                      <span className="truncate text-right">{draft.origin_device_code ?? "ไม่ระบุ Counter"} · v{draft.version ?? "-"}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="min-h-0 overflow-y-auto p-4 lg:max-h-[75vh]" aria-label="รายละเอียดบิลที่พักไว้">
            {!selected ? (
              <StateBox icon={<Server className="h-6 w-6" />} text="เลือกบิลเพื่อดูรายละเอียดและประวัติ" />
            ) : (
              <div className="space-y-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">{selected.draft_no ?? "LOCAL"}</div>
                    <h3 className="mt-1 text-xl font-black text-slate-950">{selected.label}</h3>
                    <div className="mt-2 inline-flex rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-700">
                      {statusLabels[selected.status ?? "active"] ?? selected.status}
                    </div>
                  </div>
                  <div className="text-left sm:text-right">
                    <div className="text-2xl font-black text-slate-950">{formatThaiCurrency(totalOf(selected))}</div>
                    <div className="text-xs text-slate-500">{itemCountOf(selected)} ชิ้น · version {selected.version ?? "local"}</div>
                  </div>
                </div>

                <div className="grid gap-2 sm:grid-cols-2">
                  <Info label="เจ้าของ" value={selected.owner_display ?? selected.owner_user_id ?? "ไม่ระบุ"} />
                  <Info label="ผู้รับผิดชอบ" value={selected.assignee_display ?? "ยังไม่มอบหมาย"} />
                  <Info label="Counter" value={selected.origin_device_code ?? "ไม่ระบุ"} />
                  <Info label="กะ / จุดเก็บ" value={[selected.origin_shift_number, selected.location_name].filter(Boolean).join(" · ") || "ไม่ระบุ"} />
                  <Info label="ลูกค้า" value={selected.customer_name || "ลูกค้าทั่วไป"} />
                  <Info label="โต๊ะ / คิว" value={[selected.table_id ? `โต๊ะ ${selected.table_id.slice(0, 8)}` : "", selected.queue_label].filter(Boolean).join(" · ") || "ไม่ระบุ"} />
                  <Info label="พักไว้ / หมดอายุ" value={`${new Date(selected.held_at).toLocaleString("th-TH")} · ${expiryLabel(selected.expires_at)}`} />
                  <Info label="เหตุการณ์ล่าสุด" value={lifecycleAt(selected) ? new Date(lifecycleAt(selected) ?? "").toLocaleString("th-TH") : "ยังใช้งานได้"} />
                </div>

                {selected.note ? <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm"><span className="font-bold">หมายเหตุ:</span> {selected.note}</div> : null}
                {selected.cancel_reason ? <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800"><span className="font-bold">เหตุผล:</span> {selected.cancel_reason}</div> : null}

                <div>
                  <h4 className="mb-2 font-bold text-slate-900">รายการในบิล</h4>
                  <div className="max-h-48 space-y-2 overflow-y-auto rounded-2xl border border-slate-200 p-3">
                    {selected.items.map((item, index) => (
                      <div key={`${item.product_id}-${item.variant_id ?? ""}-${index}`} className="flex items-start justify-between gap-3 rounded-xl bg-slate-50 p-3 text-sm">
                        <div>
                          <div className="font-semibold text-slate-900">{item.product_name}</div>
                          <div className="text-xs text-slate-500">{item.variant_name || item.sku} · {formatThaiCurrency(Number(item.unit_price))}</div>
                        </div>
                        <div className="text-right font-bold">×{Number(item.qty)}<div>{formatThaiCurrency(Number(item.subtotal))}</div></div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 p-3">
                  <div className="flex items-center gap-2 font-bold text-slate-900"><History className="h-5 w-5" />ประวัติ Server</div>
                  {!selected.server_backed ? (
                    <p className="mt-2 text-sm text-slate-500">Local shadow ยังไม่มีประวัติร่วมจนกว่าจะซิงก์และตรวจสอบสำเร็จ</p>
                  ) : auditQuery.isLoading ? (
                    <div className="mt-3 flex items-center gap-2 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" />กำลังโหลดประวัติ</div>
                  ) : auditRows.length === 0 ? (
                    <p className="mt-2 text-sm text-slate-500">ยังไม่มีเหตุการณ์ที่แสดงได้</p>
                  ) : (
                    <ol className="mt-3 space-y-2">
                      {auditRows.map((entry) => (
                        <li key={entry.id} className="flex gap-3 text-sm">
                          <div className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-blue-500" />
                          <div>
                            <div className="font-semibold text-slate-800">{actionLabels[entry.action] ?? entry.action} · v{entry.to_version}</div>
                            <div className="text-xs text-slate-500">{entry.actor_display ?? entry.actor_user_id.slice(0, 8)} · {new Date(entry.created_at).toLocaleString("th-TH")}</div>
                            {entry.reason ? <div className="text-xs text-slate-600">{entry.reason}</div> : null}
                          </div>
                        </li>
                      ))}
                    </ol>
                  )}
                </div>

                {props.canReassign && active && selected.server_backed ? (
                  <div className="rounded-2xl border border-slate-200 p-3">
                    <div className="mb-2 flex items-center gap-2 font-bold"><UserRound className="h-5 w-5" />มอบหมายบิล</div>
                    <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                      <select className="h-12 rounded-md border border-input bg-background px-3 text-sm" value={assigneeId} onChange={(event) => setAssigneeId(event.target.value)}>
                        <option value="">ไม่มอบหมาย</option>
                        {users.map((person) => <option key={person.id} value={person.id}>{person.display_name ?? person.username}</option>)}
                      </select>
                      <Input className="h-12" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="เหตุผลอย่างน้อย 3 ตัวอักษร" />
                      <Button
                        className="h-12"
                        variant="outline"
                        disabled={!assigneeId || reason.trim().length < 3 || props.busyId === selected.id || usersQuery.isError}
                        onClick={() => void props.onReassign(selected, assigneeId, reason.trim())}
                      >มอบหมาย</Button>
                    </div>
                    {usersQuery.isError ? <p className="mt-2 text-xs text-rose-700">โหลดรายชื่อพนักงานไม่ได้ จึงยังไม่เปิดให้มอบหมายจากหน้านี้</p> : null}
                  </div>
                ) : null}

                {active && props.canDiscard ? (
                  <div className="rounded-2xl border border-rose-200 bg-rose-50 p-3">
                    <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                      <Input className="h-12 bg-white" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="เหตุผลยกเลิกอย่างน้อย 3 ตัวอักษร" />
                      <Button className="h-12" variant="destructive" disabled={reason.trim().length < 3 || props.busyId === selected.id} onClick={() => void props.onDiscard(selected, reason.trim())}>ยกเลิกบิลพัก</Button>
                    </div>
                  </div>
                ) : null}

                <div className="flex flex-wrap justify-end gap-2 border-t border-slate-200 pt-4">
                  {claimedByMe ? <Button className="h-12" variant="outline" disabled={!props.isOnline || props.busyId === selected.id} onClick={() => void props.onRelease(selected)}>ปล่อยสิทธิ์</Button> : null}
                  {historical && selected.status !== "converted" ? <Button className="h-12" variant="outline" disabled={!props.isOnline || props.busyId === selected.id || !props.canCreate} onClick={() => void props.onReopen(selected)}>สร้างบิลกู้คืน</Button> : null}
                  {active ? <Button className="h-12 min-w-40" disabled={!props.canResume || !props.isOnline || props.busyId === selected.id} onClick={() => void props.onResume(selected)}>{props.busyId === selected.id ? <Loader2 className="h-4 w-4 animate-spin" /> : null}เรียกบิลกลับ</Button> : null}
                  {selected.status === "claimed" && !claimedByMe ? <Button className="h-12" variant="outline" onClick={props.onRetry}><RefreshCw className="h-4 w-4" />รีเฟรชผู้ถือสิทธิ์</Button> : null}
                </div>
                {!active && !claimedByMe && !historical ? <p className="text-right text-xs text-slate-500">สถานะนี้อ่านอย่างเดียว ไม่มี Action ที่ Contract รองรับ</p> : null}
              </div>
            )}
          </section>
        </div>

        <DialogFooter className="border-t border-slate-200 px-5 py-4">
          <Button className="h-12" variant="outline" onClick={() => props.onOpenChange(false)}>ปิด</Button>
          <Button className="h-12 min-w-44" disabled={!props.canCreate} onClick={props.onCreate}>พักบิลปัจจุบัน</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Info({ label, value }: { label: string; value: string }): JSX.Element {
  return <div className="rounded-xl border border-slate-200 bg-white p-3"><div className="text-xs font-semibold text-slate-400">{label}</div><div className="mt-1 break-words text-sm font-semibold text-slate-800">{value}</div></div>;
}

function StateBox({ icon, text, action }: { icon: JSX.Element; text: string; action?: JSX.Element }): JSX.Element {
  return <div className="flex min-h-40 flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-slate-300 p-5 text-center text-sm text-slate-500">{icon}<span>{text}</span>{action}</div>;
}
