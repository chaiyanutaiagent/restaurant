import {
  AlertTriangle,
  CloudOff,
  Clock3,
  Inbox,
  Loader2,
  LockKeyhole,
  RefreshCw,
  SearchX,
  ShieldAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type SystemStateKind =
  | "loading"
  | "empty"
  | "no_results"
  | "error"
  | "offline"
  | "stale"
  | "permission_denied"
  | "read_only";

type SystemStateProps = {
  kind: SystemStateKind;
  title?: string;
  description?: string;
  compact?: boolean;
  referenceId?: string | null;
  updatedAt?: string | null;
  actionLabel?: string;
  onAction?: () => void;
};

const defaults: Record<SystemStateKind, { title: string; description: string }> = {
  loading: { title: "กำลังโหลดข้อมูล", description: "ระบบกำลังตรวจบริบท สิทธิ์ และข้อมูลล่าสุด" },
  empty: { title: "ยังไม่มีข้อมูล", description: "ยังไม่มีรายการในบริบทที่เลือก" },
  no_results: { title: "ไม่พบผลลัพธ์", description: "ลองเปลี่ยนคำค้นหาหรือล้างตัวกรอง" },
  error: { title: "โหลดข้อมูลไม่สำเร็จ", description: "คำสั่งที่เกี่ยวข้องถูกปิดไว้จนกว่าจะตรวจสอบข้อมูลได้" },
  offline: { title: "อุปกรณ์ออฟไลน์", description: "ข้อมูลอาจไม่เป็นปัจจุบัน และคำสั่งที่ต้องออนไลน์ถูกปิดไว้" },
  stale: { title: "ข้อมูลล่าช้า", description: "ตรวจสอบเวลาอัปเดตล่าสุดก่อนตัดสินใจ" },
  permission_denied: { title: "ไม่มีสิทธิ์เข้าถึง", description: "ข้อมูลถูกปิดตามบทบาทและขอบเขตที่ Server กำหนด" },
  read_only: { title: "ดูข้อมูลเท่านั้น", description: "การแก้ไขถูกปิดตามสถานะผลิตภัณฑ์หรือสิทธิ์ปัจจุบัน" },
};

const icons = {
  loading: Loader2,
  empty: Inbox,
  no_results: SearchX,
  error: AlertTriangle,
  offline: CloudOff,
  stale: Clock3,
  permission_denied: LockKeyhole,
  read_only: ShieldAlert,
};

const styles: Record<SystemStateKind, string> = {
  loading: "border-blue-200 bg-blue-50/70 text-blue-800",
  empty: "border-slate-200 bg-white text-slate-600",
  no_results: "border-slate-200 bg-white text-slate-600",
  error: "border-red-200 bg-red-50 text-red-800",
  offline: "border-amber-200 bg-amber-50 text-amber-900",
  stale: "border-orange-200 bg-orange-50 text-orange-900",
  permission_denied: "border-slate-300 bg-slate-100 text-slate-700",
  read_only: "border-slate-300 bg-slate-100 text-slate-700",
};

export function SystemState({
  kind,
  title = defaults[kind].title,
  description = defaults[kind].description,
  compact = false,
  referenceId,
  updatedAt,
  actionLabel = "ลองอีกครั้ง",
  onAction,
}: SystemStateProps): JSX.Element {
  const Icon = icons[kind];
  const isAlert = ["error", "offline", "permission_denied"].includes(kind);
  return (
    <section
      className={cn(
        "flex flex-col items-center justify-center rounded-2xl border border-dashed px-5 text-center",
        compact ? "min-h-32 py-6" : "min-h-52 py-10",
        styles[kind],
      )}
      data-system-state={kind}
      role={isAlert ? "alert" : "status"}
      aria-live={kind === "loading" ? "polite" : undefined}
      aria-busy={kind === "loading"}
    >
      <span className="rounded-2xl bg-white/85 p-3 shadow-sm" aria-hidden="true">
        <Icon className={cn("h-6 w-6", kind === "loading" && "animate-spin motion-reduce:animate-none")} />
      </span>
      <h2 className="mt-3 text-base font-black">{title}</h2>
      <p className="mt-1 max-w-lg text-sm leading-6 opacity-80">{description}</p>
      {updatedAt ? <p className="mt-2 text-xs opacity-70">อัปเดตล่าสุด {updatedAt}</p> : null}
      {referenceId ? <p className="mt-1 font-mono text-xs opacity-70">Reference: {referenceId}</p> : null}
      {onAction && kind !== "loading" ? (
        <Button className="mt-4" variant="outline" onClick={onAction}>
          <RefreshCw className="h-4 w-4" />{actionLabel}
        </Button>
      ) : null}
    </section>
  );
}
