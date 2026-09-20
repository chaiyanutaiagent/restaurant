import axios from "axios";
import type { OperationalState } from "@/types/companyFoundation";
import type { CompanyModuleAccess } from "@/types/moduleAccess";

export const readinessLabel: Record<CompanyModuleAccess["readiness"], string> = {
  production: "Back-office candidate",
  pilot: "นำร่อง",
  dark_launch: "Dark launch",
  read_only: "ดูข้อมูลเท่านั้น",
  legacy: "ระบบเดิม",
  planned: "แผนงาน",
};

export const readinessClass: Record<CompanyModuleAccess["readiness"], string> = {
  production: "border-emerald-200 bg-emerald-50 text-emerald-800",
  pilot: "border-blue-200 bg-blue-50 text-blue-800",
  dark_launch: "border-amber-200 bg-amber-50 text-amber-800",
  read_only: "border-slate-300 bg-slate-100 text-slate-700",
  legacy: "border-violet-200 bg-violet-50 text-violet-800",
  planned: "border-slate-200 bg-slate-50 text-slate-500",
};

export const operationalStateLabel: Record<OperationalState, string> = {
  online: "ออนไลน์",
  offline: "ออฟไลน์",
  degraded: "ต้องตรวจสอบ",
  pending_sync: "รอซิงก์",
  stale: "ข้อมูลเก่า",
  error: "ผิดพลาด",
  disabled: "ปิดใช้งาน",
};

export const operationalStateClass: Record<OperationalState, string> = {
  online: "border-emerald-200 bg-emerald-50 text-emerald-800",
  offline: "border-slate-300 bg-slate-100 text-slate-700",
  degraded: "border-amber-200 bg-amber-50 text-amber-800",
  pending_sync: "border-blue-200 bg-blue-50 text-blue-800",
  stale: "border-orange-200 bg-orange-50 text-orange-800",
  error: "border-red-200 bg-red-50 text-red-800",
  disabled: "border-slate-200 bg-slate-50 text-slate-500",
};

export type CompanyRequestState = "error" | "offline" | "permission_denied";

export function companyRequestState(error: unknown): CompanyRequestState {
  if (!navigator.onLine) return "offline";
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 401 || error.response?.status === 403) {
      return "permission_denied";
    }
    if (!error.response) return "offline";
  }
  return "error";
}

export function formatCompanyDateTime(value: string | null | undefined): string {
  if (!value) return "ยังไม่มีข้อมูล";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "ไม่ทราบเวลา";
  return new Intl.DateTimeFormat("th-TH", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

export function formatCompanyTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return new Intl.DateTimeFormat("th-TH", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

export function dataSourceLabel(source: string): string {
  const labels: Record<string, string> = {
    platform_core: "Platform Core",
    legacy: "Legacy Production",
    restaurant: "Restaurant Database",
    retail: "Retail Database",
    takeaway: "Takeaway Database",
  };
  return labels[source] ?? source;
}
