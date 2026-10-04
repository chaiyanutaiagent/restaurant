import api from "./api";
import type { ApiResponse } from "@/types/api";
import type { TakeawayRecord, TakeawayContext, TakeawayCatalogRow, TakeawaySalePayload,
  TakeawayReceipt, TakeawayShiftSummary, TakeawayCentralOrder, TakeawayCatalogItemPayload } from "../lib/takeawayApi";
export type * from "../lib/takeawayApi";

export const takeawayApi = {
  status: () => api.get<ApiResponse<TakeawayContext>>("/takeaway/status"),
  categories: (brandId: string) => api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/catalog/categories", { params: { brand_id: brandId } }),
  catalog: (brandId: string, branchId?: string | null) => api.get<ApiResponse<TakeawayCatalogRow[]>>("/takeaway/catalog/items", { params: { brand_id: brandId, branch_id: branchId } }),
  createCatalogItem: async (_payload: TakeawayCatalogItemPayload & { brand_id: string }): Promise<never> => {
    throw new Error("การแก้ข้อมูลหลักสินค้าให้ทำจากระบบหลังบ้าน");
  },
  updateCatalogItem: async (_id: string, _payload: Omit<TakeawayCatalogItemPayload, "brand_id">): Promise<never> => {
    throw new Error("การแก้ข้อมูลหลักสินค้าให้ทำจากระบบหลังบ้าน");
  },
  shifts: () => api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/shifts"),
  openShift: (payload: { business_date: string; opening_cash: string }) => api.post<ApiResponse<TakeawayRecord>>("/takeaway/shifts/open", payload),
  closeShift: (id: string, payload: { counted_cash: string; note?: string }) => api.post<ApiResponse<TakeawayRecord>>(`/takeaway/shifts/${id}/close`, payload),
  shiftSummary: (id: string) => api.get<ApiResponse<TakeawayShiftSummary>>(`/takeaway/shifts/${id}/summary`),
  createSale: (payload: TakeawaySalePayload, offline = false) => api.post<ApiResponse<{ order: TakeawayRecord; pickup_token: string | null }>>(offline ? "/takeaway/sales/offline-sync" : "/takeaway/sales", payload),
  createOrderingLink: (hours = 12) => api.post<ApiResponse<{ token: string; expires_at: string }>>("/takeaway/ordering-links", { expires_in_hours: hours }),
  orders: (params?: Record<string, unknown>) => api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/orders", { params }),
  captureOrderPayment: (id: string, payload: Record<string, unknown>) => api.post<ApiResponse<TakeawayRecord>>(`/takeaway/orders/${id}/capture-payment`, payload),
  receipt: (id: string) => api.get<ApiResponse<TakeawayReceipt>>(`/takeaway/orders/${id}/receipt`),
  markReceiptPrinted: (id: string, copy: "customer" | "merchant", key: string) => api.post<ApiResponse<TakeawayReceipt>>(`/takeaway/orders/${id}/receipt/prints`, { copy_type: copy, idempotency_key: key }),
  updateFulfillmentOrder: (id: string, next: "preparing" | "ready") => api.post<ApiResponse<TakeawayRecord>>(`/takeaway/fulfillment/orders/${id}/${next}`),
  markPickedUp: (id: string) => api.post<ApiResponse<TakeawayRecord>>(`/takeaway/orders/${id}/picked-up`),
  stock: (id?: string) => api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/stock", { params: { location_id: id } }),
  stockLocations: () => api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/stock/locations"),
  stockMovements: (id?: string) => api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/stock/movements", { params: { location_id: id } }),
  stockMovement: (payload: Record<string, unknown>) => api.post<ApiResponse<TakeawayRecord>>("/takeaway/stock/movements", payload),
  centralOrders: (params?: Record<string, unknown>) => api.get<ApiResponse<TakeawayCentralOrder[]>>("/takeaway/store/central-orders", { params }),
  createStoreCentralOrder: (payload: Record<string, unknown>) => api.post<ApiResponse<TakeawayRecord>>("/takeaway/store/central-orders", payload),
  receiveStoreCentralOrder: (id: string) => api.post<ApiResponse<TakeawayRecord>>(`/takeaway/store/central-orders/${id}/receive`),
  receiveStoreCentralOrderQuantities: (id: string, payload: Record<string, unknown>) => api.post<ApiResponse<TakeawayRecord>>(`/takeaway/store/central-orders/${id}/receive-quantities`, payload),
};
