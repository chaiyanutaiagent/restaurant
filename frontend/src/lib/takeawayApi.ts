import axios from "axios";
import api from "@/lib/api";
import type { ApiResponse } from "@/types/api";

export type TakeawayRecord = Record<string, unknown> & { id: string };

export type TakeawayContext = {
  enabled: boolean;
  company_id: string;
  brand_id: string | null;
  branch_id: string | null;
};

export type TakeawayCatalogRow = {
  item: TakeawayRecord & {
    name: string;
    sku: string;
    category_id: string | null;
    price: string;
    unit: string;
  };
  effective_price: string;
  is_available: boolean;
};

export type TakeawaySalesSummary = {
  date_from: string;
  date_to: string;
  order_count: number;
  gross_sales: string;
  tax_amount: string;
  discount_amount: string;
};

export type TakeawayPickupStatus = {
  order_number: string;
  queue_number: number;
  status: string;
  fulfillment_status: "awaiting_payment" | "queued" | "preparing" | "ready" | "picked_up" | "cancelled";
  paid_at: string | null;
  picked_up_at: string | null;
  total_amount: string;
};

export type TakeawayPublicMenu = {
  branch_name: string;
  expires_at: string;
  categories: TakeawayRecord[];
  items: TakeawayCatalogRow[];
};

export type TakeawayPublicOrderResult = {
  order_number: string;
  queue_number: number;
  total_amount: string;
  fulfillment_status: string;
  pickup_token: string | null;
};

const configuredApiOrigin = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/$/, "");
const publicApiOrigin = configuredApiOrigin?.endsWith("/api/v1")
  ? configuredApiOrigin.slice(0, -"/api/v1".length)
  : configuredApiOrigin ?? "";

export const takeawayApi = {
  status: () => api.get<ApiResponse<TakeawayContext>>("/takeaway/status"),
  categories: (brandId: string) =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/catalog/categories", { params: { brand_id: brandId } }),
  catalog: (brandId: string, branchId?: string | null) =>
    api.get<ApiResponse<TakeawayCatalogRow[]>>("/takeaway/catalog/items", {
      params: { brand_id: brandId, branch_id: branchId || undefined },
    }),
  shifts: () => api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/shifts"),
  openShift: (payload: { business_date: string; opening_cash: string }) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/shifts/open", payload),
  closeShift: (id: string, payload: { counted_cash: string; note?: string }) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/shifts/${id}/close`, payload),
  createSale: (payload: Record<string, unknown>, offline = false) =>
    api.post<ApiResponse<{ order: TakeawayRecord; pickup_token: string | null }>>(
      offline ? "/takeaway/sales/offline-sync" : "/takeaway/sales",
      payload,
    ),
  createOrderingLink: (expiresInHours = 12) =>
    api.post<ApiResponse<{ token: string; expires_at: string }>>("/takeaway/ordering-links", {
      expires_in_hours: expiresInHours,
    }),
  captureOrderPayment: (id: string, payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/orders/${id}/capture-payment`, payload),
  orders: (params?: Record<string, unknown>) =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/orders", { params }),
  tickets: (params?: Record<string, unknown>) =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/kitchen/tickets", { params }),
  updateTicket: (id: string, nextStatus: "preparing" | "ready") =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/kitchen/tickets/${id}/${nextStatus}`),
  markPickedUp: (id: string) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/orders/${id}/picked-up`),
  centralOrders: (params?: Record<string, unknown>) =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/central/orders", { params }),
  createCentralRound: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/central/rounds", payload),
  createCentralOrder: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/central/orders", payload),
  updateCentralOrder: (id: string, status: string) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/central/orders/${id}/status`, { status }),
  productionBatches: (params?: Record<string, unknown>) =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/production/batches", { params }),
  createProduction: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/production/batches", payload),
  completeProduction: (id: string, payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/production/batches/${id}/complete`, payload),
  stock: (locationId?: string) =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/stock", { params: { location_id: locationId || undefined } }),
  stockLocations: () => api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/stock/locations"),
  stockMovement: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/stock/movements", payload),
  transfers: (params?: Record<string, unknown>) =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/transfers", { params }),
  createTransfer: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/transfers", payload),
  updateTransfer: (id: string, payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/transfers/${id}/status`, payload),
  credits: (params?: Record<string, unknown>) =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/credit/accounts", { params }),
  setCredit: (payload: Record<string, unknown>) =>
    api.put<ApiResponse<TakeawayRecord>>("/takeaway/credit/accounts", payload),
  addCreditEntry: (id: string, payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/credit/accounts/${id}/entries`, payload),
  salesSummary: (dateFrom: string, dateTo: string) =>
    api.get<ApiResponse<TakeawaySalesSummary>>("/takeaway/reports/sales-summary", {
      params: { date_from: dateFrom, date_to: dateTo },
    }),
  dryRunImport: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/imports/dry-run", payload),
  applySyntheticImport: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/imports/synthetic-apply", payload),
  erpEvents: (status = "pending") =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/integrations/erp/events", { params: { status } }),
  acknowledgeErpEvent: (id: string, payload: { idempotency_key: string; erp_reference: string }) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/integrations/erp/events/${id}/acknowledge`, payload),
  erpReconciliation: () =>
    api.get<ApiResponse<Record<string, unknown>>>("/takeaway/integrations/erp/reconciliation"),
};

export const takeawayPublicApi = {
  pickupStatus: (token: string) =>
    axios.get<ApiResponse<TakeawayPickupStatus>>(
      `${publicApiOrigin}/api/public/takeaway/pickup/${encodeURIComponent(token)}`,
    ),
  orderingMenu: (token: string) =>
    axios.get<ApiResponse<TakeawayPublicMenu>>(
      `${publicApiOrigin}/api/public/takeaway/ordering/${encodeURIComponent(token)}`,
    ),
  createOrder: (token: string, payload: Record<string, unknown>) =>
    axios.post<ApiResponse<TakeawayPublicOrderResult>>(
      `${publicApiOrigin}/api/public/takeaway/ordering/${encodeURIComponent(token)}/orders`,
      payload,
    ),
};
