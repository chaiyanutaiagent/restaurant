import api from "@/lib/api";

export const reportApi = {
  dashboard: (branchId?: string) =>
    api.get("/reports/dashboard", { params: { branch_id: branchId } }),
  dailySales: (date?: string, branchId?: string) =>
    api.get("/reports/sales/daily", { params: { date, branch_id: branchId } }),
  salesRange: (dateFrom: string, dateTo: string, branchId?: string) =>
    api.get("/reports/sales/range", {
      params: { date_from: dateFrom, date_to: dateTo, branch_id: branchId }
    }),
  hourlySales: (date?: string, branchId?: string) =>
    api.get("/reports/sales/hourly", { params: { date, branch_id: branchId } }),
  topProducts: (dateFrom: string, dateTo: string, branchId?: string, limit = 20) =>
    api.get("/reports/products/top", {
      params: { date_from: dateFrom, date_to: dateTo, branch_id: branchId, limit }
    }),
  shiftSummary: (shiftId: string) => api.get(`/reports/shifts/${shiftId}`),
  shiftPdf: (shiftId: string) =>
    api.get(`/reports/shifts/${shiftId}/pdf`, { responseType: "blob" })
};
