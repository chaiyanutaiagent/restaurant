import axios from "axios";
import api from "@/lib/api";
import type { ApiResponse } from "@/types/api";

export type TakeawayRecord = Record<string, unknown> & { id: string };

export type TakeawayContext = {
  enabled: boolean;
  writes_enabled: boolean;
  release_stage: "dark_launch" | "uat_synthetic";
  hard_holds: string[];
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

export type TakeawaySalePayload = {
  brand_id: string;
  branch_id: string;
  shift_id: string;
  idempotency_key: string;
  channel: "counter" | "qr" | "online";
  items: Array<{ catalog_item_id: string; quantity: string; note?: string }>;
  discount_amount: string;
  payment: {
    method: "cash" | "promptpay" | "card" | "credit" | "other";
    amount: string;
    reference?: string;
    idempotency_key: string;
  };
  customer_name?: string;
  customer_phone?: string;
  note?: string;
  offline_device_id?: string;
  offline_sequence?: number;
};

export type TakeawayReceiptLine = {
  sku: string;
  name: string;
  quantity: string;
  line_total: string;
};

export type TakeawayReceipt = TakeawayRecord & {
  order_id: string;
  receipt_number: string;
  payload: {
    order_number: string;
    queue_number: number | null;
    items: TakeawayReceiptLine[];
    subtotal: string;
    discount_amount: string;
    tax_amount: string;
    total_amount: string;
    payment_method: string;
  };
  issued_at: string;
  print_count: number;
  last_printed_at: string | null;
  last_printed_copy: "customer" | "merchant" | null;
};

export type TakeawayShiftSummary = {
  shift: TakeawayRecord;
  paid: { order_count: number; amount: string; tax_amount: string; discount_amount: string };
  refunded: { order_count: number; amount: string; tax_amount: string; discount_amount: string };
  payment_totals: Record<string, string>;
  refunded_payments: Record<string, string>;
  expected_cash: string;
  counted_cash: string | null;
  cash_variance: string | null;
};

export type TakeawayCentralOrderItem = TakeawayRecord & {
  catalog_item_id: string | null;
  sku: string | null;
  item_name: string;
  quantity: string;
  unit: string;
  source_kind: "catalog" | "extra" | "unlisted";
};

export type TakeawayCentralOrder = TakeawayRecord & {
  order_number: string;
  order_type: "regular" | "extra" | "unlisted";
  status: string;
  requested_delivery_date: string | null;
  note: string | null;
  items: TakeawayCentralOrderItem[];
};

export type TakeawaySalesSummary = {
  date_from: string;
  date_to: string;
  order_count: number;
  gross_sales: string;
  tax_amount: string;
  discount_amount: string;
};

export type TakeawayOperationalSummary = TakeawaySalesSummary & {
  central_orders: number;
  central_discrepancies: number;
  production_batches: number;
  production_completed: number;
  transfers: number;
  transfer_discrepancies: number;
  credit_balance: string;
  credit_limit: string;
  erp_events_pending: number;
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
  writes_enabled: boolean;
  release_stage: "dark_launch" | "uat_synthetic";
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
  shiftSummary: (id: string) =>
    api.get<ApiResponse<TakeawayShiftSummary>>(`/takeaway/shifts/${id}/summary`),
  createSale: (payload: TakeawaySalePayload, offline = false) =>
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
  receipt: (orderId: string) =>
    api.get<ApiResponse<TakeawayReceipt>>(`/takeaway/orders/${orderId}/receipt`),
  markReceiptPrinted: (orderId: string, copyType: "customer" | "merchant", idempotencyKey: string) =>
    api.post<ApiResponse<TakeawayReceipt>>(`/takeaway/orders/${orderId}/receipt/prints`, {
      copy_type: copyType,
      idempotency_key: idempotencyKey,
    }),
  tickets: (params?: Record<string, unknown>) =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/kitchen/tickets", { params }),
  updateTicket: (id: string, nextStatus: "preparing" | "ready") =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/kitchen/tickets/${id}/${nextStatus}`),
  markPickedUp: (id: string) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/orders/${id}/picked-up`),
  recipes: (params?: Record<string, unknown>) =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/recipes", { params }),
  createRecipe: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/recipes", payload),
  replenishmentPolicies: (params?: Record<string, unknown>) =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/replenishment/policies", { params }),
  setReplenishmentPolicy: (payload: Record<string, unknown>) =>
    api.put<ApiResponse<TakeawayRecord>>("/takeaway/replenishment/policies", payload),
  replenishmentSuggestions: (brandId: string, branchId: string, lookbackDays = 7) =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/replenishment/suggestions", {
      params: { brand_id: brandId, branch_id: branchId, lookback_days: lookbackDays },
    }),
  generateReplenishmentOrder: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/replenishment/generate-order", payload),
  centralOrders: (params?: Record<string, unknown>) =>
    api.get<ApiResponse<TakeawayCentralOrder[]>>("/takeaway/central/orders", { params }),
  createCentralRound: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/central/rounds", payload),
  createCentralOrder: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/central/orders", payload),
  createStoreCentralOrder: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/store/central-orders", payload),
  receiveStoreCentralOrder: (id: string) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/store/central-orders/${id}/receive`),
  receiveStoreCentralOrderQuantities: (id: string, payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/store/central-orders/${id}/receive-quantities`, payload),
  updateCentralOrder: (id: string, status: string) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/central/orders/${id}/status`, { status }),
  updateCentralOrderItem: (id: string, payload: Record<string, unknown>) =>
    api.put<ApiResponse<TakeawayRecord>>(`/takeaway/central/order-items/${id}`, payload),
  fulfilCentralOrder: (id: string, stage: "packed" | "shipped", payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/central/orders/${id}/${stage}`, payload),
  resolveCentralDiscrepancy: (id: string, payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/central/orders/${id}/resolve-discrepancy`, payload),
  productionBatches: (params?: Record<string, unknown>) =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/production/batches", { params }),
  createProduction: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/production/batches", payload),
  completeProduction: (id: string, payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/production/batches/${id}/complete`, payload),
  updateProductionStatus: (id: string, payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/production/batches/${id}/status`, payload),
  stock: (locationId?: string) =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/stock", { params: { location_id: locationId || undefined } }),
  stockLocations: () => api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/stock/locations"),
  stockMovements: (locationId?: string) =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/stock/movements", {
      params: { location_id: locationId || undefined },
    }),
  stockMovement: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/stock/movements", payload),
  transfers: (params?: Record<string, unknown>) =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/transfers", { params }),
  createTransfer: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/transfers", payload),
  updateTransfer: (id: string, payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/transfers/${id}/status`, payload),
  fulfilTransfer: (id: string, stage: "ship" | "receive", payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/transfers/${id}/${stage}`, payload),
  resolveTransferDiscrepancy: (id: string, payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/transfers/${id}/resolve-discrepancy`, payload),
  credits: (params?: Record<string, unknown>) =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/credit/accounts", { params }),
  setCredit: (payload: Record<string, unknown>) =>
    api.put<ApiResponse<TakeawayRecord>>("/takeaway/credit/accounts", payload),
  addCreditEntry: (id: string, payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/credit/accounts/${id}/entries`, payload),
  creditEntries: (id: string) =>
    api.get<ApiResponse<TakeawayRecord[]>>(`/takeaway/credit/accounts/${id}/entries`),
  creditTopups: (params?: Record<string, unknown>) =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/credit/topups", { params }),
  createCreditTopup: (id: string, payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/credit/accounts/${id}/topups`, payload),
  reviewCreditTopup: (id: string, payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>(`/takeaway/credit/topups/${id}/review`, payload),
  creditPaymentConfig: (brandId: string) =>
    api.get<ApiResponse<TakeawayRecord | null>>("/takeaway/credit/payment-config", { params: { brand_id: brandId } }),
  setCreditPaymentConfig: (payload: Record<string, unknown>) =>
    api.put<ApiResponse<TakeawayRecord>>("/takeaway/credit/payment-config", payload),
  salesSummary: (dateFrom: string, dateTo: string) =>
    api.get<ApiResponse<TakeawaySalesSummary>>("/takeaway/reports/sales-summary", {
      params: { date_from: dateFrom, date_to: dateTo },
    }),
  operationalSummary: (dateFrom: string, dateTo: string) =>
    api.get<ApiResponse<TakeawayOperationalSummary>>("/takeaway/reports/operational-summary", {
      params: { date_from: dateFrom, date_to: dateTo },
    }),
  dryRunImport: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/imports/dry-run", payload),
  applySyntheticImport: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/imports/synthetic-apply", payload),
  previewCutover: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/cutover/preview", payload),
  executeCutover: (payload: Record<string, unknown>) =>
    api.post<ApiResponse<TakeawayRecord>>("/takeaway/cutover/execute", payload),
  cutoverRuns: () =>
    api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/cutover/runs"),
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
