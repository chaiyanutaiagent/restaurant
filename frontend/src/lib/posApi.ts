import api from "./api";
import type { ApiResponse } from "@/types/api";
import type { SaleOrder } from "@/types/pos";
import type { StockLocation } from "@/types/stock";

export const posApi = {
  openShift: (data: { location_id: string; opening_cash: number }) => api.post("/pos/shifts/open", data),
  getCurrentShift: () => api.get("/pos/shifts/current"),
  closeShift: (shiftId: string, data: { closing_cash: number; note?: string }) =>
    api.post(`/pos/shifts/${shiftId}/close`, data),
  listShifts: (params?: { branch_id?: string; page?: number; limit?: number }) =>
    api.get("/pos/shifts", { params }),
  createSale: (data: object) => api.post<ApiResponse<SaleOrder>>("/pos/sales", data),
  syncSales: (orders: object[]) => api.post<ApiResponse<SaleOrder[]>>("/pos/sales/sync", { orders }),
  listSales: (params?: object) => api.get<ApiResponse<SaleOrder[]>>("/pos/sales", { params }),
  getSale: (id: string) => api.get<ApiResponse<SaleOrder>>(`/pos/sales/${id}`),
  voidSale: (id: string, reason: string, approvalToken?: string) =>
    api.post(`/pos/sales/${id}/void`, { void_reason: reason, approval_token: approvalToken }),
  refundSale: (id: string, reason: string, approvalToken?: string) =>
    api.post(`/pos/sales/${id}/refund`, { refund_reason: reason, approval_token: approvalToken }),
  partialRefundSale: (id: string, data: { refund_reason: string; items: Array<{ order_item_id: string; qty: number }>; approval_token?: string }) =>
    api.post<ApiResponse<SaleOrder>>(`/pos/sales/${id}/refund/partial`, data),
  getPromptPayQR: (amount?: number, target?: string) => api.get("/pos/promptpay/qr", { params: { amount, target } }),
  listLocations: (branchId?: string) =>
    api.get("/stock/locations", { params: { branch_id: branchId } }) as Promise<{ data: { data: StockLocation[] } }>,
};
