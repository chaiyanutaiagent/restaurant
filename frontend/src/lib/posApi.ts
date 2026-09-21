import api from "./api";
import type { ApiResponse } from "@/types/api";
import type { CashMovement, CashierShift, HoldDraftAuditEntry, HoldDraftClaimResult, PosShiftSummary, PricingCalculation, RefundOperation, RefundQuote, SaleOrder, ServerHoldDraft } from "@/types/pos";
import type { StockLocation } from "@/types/stock";

export const posApi = {
  openShift: (data: { location_id: string; opening_cash: number; shift_type?: "staff_cashier" | "operational_cashless"; idempotency_key?: string }) =>
    api.post<ApiResponse<CashierShift>>("/pos/shifts/open", data),
  getCurrentShift: () => api.get<ApiResponse<CashierShift | null>>("/pos/shifts/current"),
  getShiftSummary: (shiftId: string) => api.get<ApiResponse<PosShiftSummary>>(`/pos/shifts/${shiftId}/summary`),
  createCashMovement: (shiftId: string, data: {
    movement_type: "cash_in" | "cash_out";
    amount: number;
    reason_code: "change_fund" | "cash_drop" | "petty_cash" | "supplier_payment" | "correction" | "other";
    reason: string;
    expected_shift_version: number;
    idempotency_key: string;
    approval_token?: string;
  }) => api.post<ApiResponse<CashMovement>>(`/pos/shifts/${shiftId}/cash-movements`, data),
  closeShift: (shiftId: string, data: {
    closing_cash: number;
    reason_code?: "count_short" | "count_over" | "change_error" | "cash_movement" | "other";
    note?: string;
    cash_count?: Array<{ denomination: number; quantity: number }>;
    expected_version?: number;
    idempotency_key?: string;
    approval_token?: string;
  }) => api.post<ApiResponse<CashierShift>>(`/pos/shifts/${shiftId}/close`, data),
  handoverShift: (shiftId: string, data: {
    closing_cash: number;
    reason_code?: "count_short" | "count_over" | "change_error" | "cash_movement" | "other";
    note?: string;
    cash_count?: Array<{ denomination: number; quantity: number }>;
    expected_version?: number;
    idempotency_key?: string;
    approval_token?: string;
  }) => api.post<ApiResponse<{ shift: CashierShift; device_code: string; staff_logout_required: boolean; device_pairing_preserved: boolean }>>(`/pos/shifts/${shiftId}/handover`, data),
  listShifts: (params?: { branch_id?: string; page?: number; limit?: number }) =>
    api.get("/pos/shifts", { params }),
  createSale: (data: object) => api.post<ApiResponse<SaleOrder>>("/pos/sales", data),
  calculatePricing: (data: object) => api.post<ApiResponse<PricingCalculation>>("/pos/pricing/calculate", data),
  syncSales: (orders: object[]) => api.post<ApiResponse<SaleOrder[]>>("/pos/sales/sync", { orders }),
  listSales: (params?: object) => api.get<ApiResponse<SaleOrder[]>>("/pos/sales", { params }),
  getSale: (id: string) => api.get<ApiResponse<SaleOrder>>(`/pos/sales/${id}`),
  voidSale: (id: string, reason: string, approvalToken?: string) =>
    api.post(`/pos/sales/${id}/void`, { void_reason: reason, approval_token: approvalToken }),
  refundSale: (id: string, reason: string, approvalToken?: string) =>
    api.post(`/pos/sales/${id}/refund`, { refund_reason: reason, approval_token: approvalToken }),
  partialRefundSale: (id: string, data: { refund_reason: string; items: Array<{ order_item_id: string; qty: number }>; approval_token?: string }) =>
    api.post<ApiResponse<SaleOrder>>(`/pos/sales/${id}/refund/partial`, data),
  createRefundQuote: (data: object) => api.post<ApiResponse<RefundQuote>>("/pos/refunds/quotes", data),
  executeRefund: (data: object) => api.post<ApiResponse<RefundOperation>>("/pos/refunds", data),
  listRefunds: (params?: { order_id?: string }) => api.get<ApiResponse<RefundOperation[]>>("/pos/refunds", { params }),
  getRefund: (id: string) => api.get<ApiResponse<RefundOperation>>(`/pos/refunds/${id}`),
  confirmCashRefund: (id: string, data: object) => api.post<ApiResponse<RefundOperation>>(`/pos/refunds/${id}/cash-confirm`, data),
  inquireRefund: (id: string, data: object) => api.post<ApiResponse<RefundOperation>>(`/pos/refunds/${id}/inquire`, data),
  retryRefund: (id: string, data: object) => api.post<ApiResponse<RefundOperation>>(`/pos/refunds/${id}/retry`, data),
  retryRefundTax: (id: string, data: object) => api.post<ApiResponse<RefundOperation>>(`/pos/refunds/${id}/tax-retry`, data),
  getPromptPayQR: (amount?: number, target?: string) => api.get("/pos/promptpay/qr", { params: { amount, target } }),
  listLocations: (branchId?: string) =>
    api.get("/stock/locations", { params: { branch_id: branchId } }) as Promise<{ data: { data: StockLocation[] } }>,
  listHoldDrafts: (params?: { status?: string; mine?: boolean; this_counter?: boolean; search?: string; include_history?: boolean }) =>
    api.get<ApiResponse<ServerHoldDraft[]>>("/pos/drafts", { params }),
  getHoldDraft: (id: string) => api.get<ApiResponse<ServerHoldDraft>>(`/pos/drafts/${id}`),
  getHoldDraftAudit: (id: string) => api.get<ApiResponse<HoldDraftAuditEntry[]>>(`/pos/drafts/${id}/audit`),
  createHoldDraft: (data: object) => api.post<ApiResponse<ServerHoldDraft>>("/pos/drafts", data),
  updateHoldDraft: (id: string, data: object) => api.patch<ApiResponse<ServerHoldDraft>>(`/pos/drafts/${id}`, data),
  claimHoldDraft: (id: string, data: object) => api.post<ApiResponse<HoldDraftClaimResult>>(`/pos/drafts/${id}/claim`, data),
  resumeHoldDraft: (id: string, data: object) => api.post<ApiResponse<ServerHoldDraft>>(`/pos/drafts/${id}/resume`, data),
  releaseHoldDraft: (id: string, data: object) => api.post<ApiResponse<ServerHoldDraft>>(`/pos/drafts/${id}/release`, data),
  discardHoldDraft: (id: string, data: object) => api.post<ApiResponse<ServerHoldDraft>>(`/pos/drafts/${id}/discard`, data),
  reopenHoldDraft: (id: string, data: object) => api.post<ApiResponse<ServerHoldDraft>>(`/pos/drafts/${id}/reopen`, data),
};
