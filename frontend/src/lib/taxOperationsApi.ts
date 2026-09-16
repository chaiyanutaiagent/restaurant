import api from "./api";
import type { ApiResponse } from "@/types/api";
import type { TaxExportRow, TaxExportType, TaxOperationsDashboard } from "@/types/taxOperations";

export const taxOperationsApi = {
  dashboard: (year: number, month: number, branchId?: string | null) =>
    api.get<ApiResponse<TaxOperationsDashboard>>("/tax-operations/dashboard", { params: { year, month, branch_id: branchId || undefined } }),
  syncLegacy: (year: number, month: number, branchId?: string | null) =>
    api.post<ApiResponse<{ sales: number; purchases: number }>>("/tax-operations/sync/legacy", { year, month, branch_id: branchId || null }),
  reconcile: (year: number, month: number, branchId?: string | null) =>
    api.post<ApiResponse<{ detected: number; blockers: number }>>("/tax-operations/reconcile", { year, month, branch_id: branchId || null }),
  changePeriod: (action: "review" | "close" | "reopen", year: number, month: number, branchId?: string | null, reason?: string) =>
    api.post<ApiResponse<TaxOperationsDashboard["period"]>>(`/tax-operations/periods/${action}`, { year, month, branch_id: branchId || null, reason: reason || null }),
  resolveIssue: (id: string, status: "resolved" | "ignored", note: string) =>
    api.patch<ApiResponse<unknown>>(`/tax-operations/issues/${id}`, { status, note }),
  createExport: (year: number, month: number, exportType: TaxExportType, branchId?: string | null) =>
    api.post<ApiResponse<TaxExportRow>>("/tax-operations/exports", { year, month, branch_id: branchId || null, export_type: exportType, reason: "จัดทำชุดข้อมูลภาษีประจำงวด" }),
  download: (id: string) => api.get<Blob>(`/tax-operations/exports/${id}/download`, { responseType: "blob" }),
};
