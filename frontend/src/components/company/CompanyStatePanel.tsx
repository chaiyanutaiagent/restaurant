import {
  AlertTriangle,
  CloudOff,
  Inbox,
  Loader2,
  LockKeyhole,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type CompanyStateKind =
  | "loading"
  | "empty"
  | "error"
  | "offline"
  | "permission_denied";

type CompanyStatePanelProps = {
  kind: CompanyStateKind;
  title?: string;
  description?: string;
  compact?: boolean;
  onRetry?: () => void;
};

const defaults: Record<CompanyStateKind, { title: string; description: string }> = {
  loading: {
    title: "กำลังโหลดข้อมูล",
    description: "ระบบกำลังตรวจบริบท สิทธิ์ และข้อมูลล่าสุด",
  },
  empty: {
    title: "ยังไม่มีข้อมูล",
    description: "ไม่พบรายการในบริบทที่เลือก",
  },
  error: {
    title: "โหลดข้อมูลไม่สำเร็จ",
    description: "บางส่วนของหน้านี้ใช้งานไม่ได้ชั่วคราว โดย action ที่เกี่ยวข้องจะถูกปิดไว้",
  },
  offline: {
    title: "อุปกรณ์ออฟไลน์",
    description: "ตรวจสอบเครือข่ายแล้วลองใหม่ ระบบจะไม่ส่ง action ขณะไม่มีการเชื่อมต่อ",
  },
  permission_denied: {
    title: "ไม่มีสิทธิ์ดูข้อมูลส่วนนี้",
    description: "ข้อมูลถูกปิดตามบทบาทและขอบเขตที่ Server กำหนด",
  },
};

const icons = {
  loading: Loader2,
  empty: Inbox,
  error: AlertTriangle,
  offline: CloudOff,
  permission_denied: LockKeyhole,
};

const styles: Record<CompanyStateKind, string> = {
  loading: "border-blue-200 bg-blue-50/70 text-blue-800",
  empty: "border-slate-200 bg-white text-slate-600",
  error: "border-red-200 bg-red-50 text-red-800",
  offline: "border-amber-200 bg-amber-50 text-amber-900",
  permission_denied: "border-slate-300 bg-slate-100 text-slate-700",
};

export default function CompanyStatePanel({
  kind,
  title = defaults[kind].title,
  description = defaults[kind].description,
  compact = false,
  onRetry,
}: CompanyStatePanelProps): JSX.Element {
  const Icon = icons[kind];
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-2xl border border-dashed px-5 text-center",
        compact ? "min-h-32 py-6" : "min-h-52 py-10",
        styles[kind],
      )}
      data-company-state={kind}
      role={kind === "error" || kind === "offline" ? "alert" : "status"}
    >
      <span className="rounded-2xl bg-white/80 p-3 shadow-sm">
        <Icon className={cn("h-6 w-6", kind === "loading" && "animate-spin")} />
      </span>
      <p className="mt-3 font-black">{title}</p>
      <p className="mt-1 max-w-lg text-sm leading-6 opacity-80">{description}</p>
      {onRetry && kind !== "loading" ? (
        <Button className="mt-4" variant="outline" onClick={onRetry}>
          <RefreshCw className="h-4 w-4" />ลองอีกครั้ง
        </Button>
      ) : null}
    </div>
  );
}
