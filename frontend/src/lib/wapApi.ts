import api from "@/lib/api";
import type { ApiResponse } from "@/types/api";
import type { Branch } from "@/types/user";
import type { StockLocation } from "@/types/stock";
import type { CashierShift } from "@/types/pos";

export type WapMenuProduct = {
  id: string;
  sku: string;
  name: string;
  description: string | null;
  selling_price: number;
  category_id: string | null;
  category_name: string | null;
  image_url: string | null;
  is_available: boolean;
  menu_recipe?: {
    id: string;
    name: string;
    recipe_type: "menu_recipe" | string;
    yield_qty: number;
    yield_unit: string;
    ingredients: Array<{
      ingredient_id: string;
      ingredient_name: string;
      ingredient_sku: string;
      quantity: number;
      unit: string;
    }>;
  } | null;
};

export type WapMenu = {
  brand_slug?: string | null;
  brand_name?: string | null;
  branch_name: string;
  shift_id?: string | null;
  location_id?: string | null;
  queue_prefix: string;
  promptpay_name?: string | null;
  promptpay_payload?: string | null;
  offline_policy_version?: number;
  offline_authorization?: string;
  offline_authorization_expires_at?: string;
  offline_device_id?: string | null;
  categories: { id: string; name: string }[];
  products: WapMenuProduct[];
};

export type WapOrder = {
  session_id: string;
  order_id: string;
  sale_order_id: string;
  sale_order_number: string;
  opened_by: string | null;
  cashier_user_id: string | null;
  queue_number: number | null;
  queue_display: string | null;
  status: string;
  customer_name: string | null;
  customer_phone: string | null;
  subtotal: string | number;
  total_amount: string | number;
  paid_amount: string | number;
  change_amount: string | number;
  payment_method: string;
  customer_slip_printed_at: string | null;
  kitchen_slip_printed_at: string | null;
  kitchen_sent_at: string | null;
  recipe_stock_status?: string | null;
  recipe_stock_warnings?: string[];
  created_at: string | null;
  client_order_id?: string | null;
  is_offline_pending?: boolean;
  items: Array<{
    product_id: string;
    product_name: string;
    qty: number;
    unit_price: string | number;
    special_request: string | null;
  }>;
};

export type WapPaidOrderPayload = {
  items: Array<{
    product_id: string;
    qty: number;
    special_request?: string | null;
    expected_unit_price?: number;
    expected_price_version?: string;
  }>;
  payment_method: string;
  paid_amount: number;
  payments?: Array<{ payment_method: string; amount: number; reference_no?: string | null }>;
  customer_name?: string | null;
  customer_phone?: string | null;
  customer_tax_id?: string | null;
  note?: string | null;
  shift_id?: string | null;
  location_id?: string | null;
  client_order_id?: string;
  local_created_at?: string;
  local_customer_slip_printed_at?: string;
  local_kitchen_slip_printed_at?: string;
  offline_policy_version?: number;
  offline_authorization?: string;
  is_offline?: boolean;
};

export type WapOfflineSyncResult = {
  client_order_id: string;
  status: "synced" | "needs_review";
  order: WapOrder | null;
  error: string | null;
};

export type WapOfflineSyncResponse = {
  results: WapOfflineSyncResult[];
};

export type WapShiftCloseProduct = {
  product_id: string | null;
  product_name: string;
  sku: string;
  qty: number;
  unit?: string;
  amount: number;
  source?: string;
};

export type WapCashierSales = {
  user_id: string;
  employee_name: string;
  username: string;
  order_count: number;
  total_amount: number;
};

export type WapShiftClosure = {
  id: string;
  brand_id: string | null;
  branch_id: string;
  business_date: string;
  round_no?: number;
  closed_by: string;
  closed_by_name: string | null;
  closed_at: string | null;
  total_orders: number;
  total_amount: number;
  central_order_id?: string | null;
  central_order_number?: string | null;
  central_order_status?: string | null;
  items?: Array<WapShiftCloseProduct & { id: string; item_type: "sold_product" | "purchase_item" | string }>;
};

export type WapShiftCloseSummary = {
  date: string;
  total_orders: number;
  total_amount: number;
  products: WapShiftCloseProduct[];
  purchase_items: WapShiftCloseProduct[];
  cashier_sales?: WapCashierSales[];
  closure_id?: string;
  closed_at?: string;
  current_round_no?: number;
  existing_closure?: WapShiftClosure | null;
  previous_closure?: WapShiftClosure | null;
};

export type CentralOrderItem = {
  id?: string;
  product_id: string | null;
  sku: string;
  product_name: string;
  unit: string;
  unit_cost?: number;
  system_qty: number;
  requested_qty: number;
  approved_qty?: number;
  shipped_qty?: number;
  received_qty?: number;
  in_transit_qty?: number;
  discrepancy_qty?: number;
  requested_amount?: number;
  approved_amount?: number;
  shipped_amount?: number;
  source?: string | null;
};

export type CentralOrder = {
  id: string;
  order_number: string;
  status: string;
  branch_id: string;
  branch_name: string | null;
  shift_closure_id?: string;
  transfer_order_id?: string | null;
  transfer_order_number?: string | null;
  transfer_order_status?: string | null;
  transfer_has_discrepancy?: boolean;
  transfer_discrepancy_note?: string | null;
  business_date: string;
  submitted_by?: string;
  approved_by?: string | null;
  packed_by?: string | null;
  shipped_by?: string | null;
  received_by?: string | null;
  submitted_at: string | null;
  approved_at?: string | null;
  packed_at?: string | null;
  shipped_at?: string | null;
  received_at?: string | null;
  credit_reserved_amount?: number;
  credit_captured_amount?: number;
  credit_released_amount?: number;
  note?: string | null;
  item_count?: number;
  closure_count?: number;
  closure_ids?: string[];
  closure_rounds?: Array<{
    id: string;
    round_no: number;
    total_orders: number;
    total_amount: number;
    closed_at: string | null;
  }>;
  items?: CentralOrderItem[];
};

export type CentralOrderReceivePayload = {
  items: Array<{ item_id: string; qty_received: number }>;
  finalize: boolean;
  note?: string | null;
};

export type DailyCentralOrderSummary = {
  date: string;
  branch_name: string | null;
  closure_count: number;
  total_orders: number;
  total_amount: number;
  purchase_items: WapShiftCloseProduct[];
  closures: WapShiftClosure[];
  existing_order: CentralOrder | null;
};

export type CentralProductionSummaryItem = {
  product_id: string | null;
  sku: string;
  product_name: string;
  unit: string;
  requested_qty: number;
  ready_available?: number;
  in_production_qty?: number;
  production_required?: number;
  order_count: number;
};

export type CentralProductionIngredientItem = {
  product_id: string | null;
  sku: string;
  product_name: string;
  unit: string;
  required_qty: number;
  order_count: number;
  sources: string[];
};

export type ProductionBatchLine = {
  id: string;
  line_type: "input" | "output";
  product_id: string;
  product_name: string;
  product_sku: string;
  source_location_id: string | null;
  source_location_name: string | null;
  destination_location_id: string | null;
  destination_location_name: string | null;
  planned_qty: number;
  actual_qty: number | null;
  unit_code: string;
  cost_per_unit: number;
  sort_order: number;
};

export type ProductionBatch = {
  id: string;
  company_id: string;
  brand_id: string;
  batch_number: string;
  planned_date: string;
  status: "draft" | "planned" | "in_progress" | "completed" | "cancelled";
  raw_location_id: string;
  raw_location_name: string;
  ready_location_id: string;
  ready_location_name: string;
  planned_by: string;
  started_by: string | null;
  completed_by: string | null;
  planned_at: string;
  started_at: string | null;
  completed_at: string | null;
  note: string | null;
  lines: ProductionBatchLine[];
};

export type BrandOperationsReport = {
  brand_id: string;
  brand_slug: string;
  date_from: string;
  date_to: string;
  dashboard_totals: {
    sales_amount: number;
    payment_amount: number;
    estimated_recipe_cogs: number;
    waste_qty: number;
    waste_cost: number;
    shift_closure_amount: number;
    missing_recipe_product_count: number;
  };
  reconciliation: {
    sales: {
      source_order_total: number;
      branch_rows_total: number;
      delta: number;
      is_reconciled: boolean;
    };
    payments: {
      source_payment_total: number;
      source_order_total: number;
      delta: number;
      is_reconciled: boolean;
    };
  };
  sales_by_branch: Array<{
    branch_id: string;
    branch_name: string;
    order_count: number;
    total_amount: number;
  }>;
  sales_by_cashier: Array<{
    user_id: string;
    cashier_name: string;
    order_count: number;
    total_amount: number;
  }>;
  central_orders_by_status: Array<{
    status: string;
    order_count: number;
    reserved_amount: number;
    captured_amount: number;
    released_amount: number;
  }>;
  production_by_date: Array<{
    business_date: string;
    order_count: number;
    requested_qty: number;
    shipped_qty: number;
  }>;
  shift_closures_by_branch: Array<{
    branch_id: string;
    branch_name: string;
    closure_count: number;
    order_count: number;
    total_amount: number;
  }>;
  delivery_by_branch: Array<{
    branch_id: string;
    branch_name: string;
    shipped_order_count: number;
    shipped_amount: number;
    received_order_count: number;
    received_qty: number;
  }>;
  sales_vs_replenishment: Array<{
    branch_id: string;
    branch_name: string;
    sales_amount: number;
    requested_amount: number;
    shipped_amount: number;
    delta_amount: number;
  }>;
  recipe_costs: Array<{
    recipe_id: string;
    product_id: string;
    product_name: string;
    recipe_name: string;
    recipe_type: string;
    total_cost: number;
    cost_per_yield: number;
    selling_price: number;
    gross_margin_pct: number;
  }>;
  credit_balances: Array<{
    branch_id: string;
    branch_name: string;
    balance: number;
    reserved_amount: number;
    available_credit: number;
  }>;
};

export type StockCutoverIssue = {
  code: string;
  message: string;
  details: Record<string, unknown>;
};

export type StockCutoverLocation = {
  id: string;
  branch_id: string;
  code: string;
  name: string;
  is_active: boolean;
};

export type StockCutoverCandidate = {
  source_balance_id: string;
  product_id: string;
  variant_id: string | null;
  sku: string;
  product_name: string;
  unit: string | null;
  qty: number;
  qty_reserved: number;
  cost_per_unit: number;
  destination_qty_before: number;
};

export type StockCutoverRun = {
  id: string;
  brand_id: string;
  source_location_id: string;
  destination_location_id: string;
  status: "running" | "completed" | "failed";
  preview_token: string;
  item_count: number;
  total_qty: number;
  executed_by: string;
  executed_at: string | null;
  created_at: string | null;
  note: string | null;
  items: Array<{
    id: string;
    product_id: string;
    sku: string | null;
    product_name: string | null;
    variant_id: string | null;
    qty: number;
    cost_per_unit: number;
    source_qty_before: number;
    source_qty_after: number;
    destination_qty_before: number;
    destination_qty_after: number;
    source_movement_id: string;
    destination_movement_id: string;
  }>;
};

export type StockCutoverPreview = {
  brand_id: string;
  brand_slug: string;
  brand_name: string;
  central_branch_id: string | null;
  raw_location: StockCutoverLocation | null;
  ready_location: StockCutoverLocation | null;
  store_locations: Array<{
    branch_id: string;
    branch_code: string;
    branch_name: string;
    branch_type: string;
    store_location_id: string | null;
    store_location_code: string | null;
    store_location_name: string | null;
    is_valid: boolean;
  }>;
  product_audit: Array<{
    product_id: string;
    sku: string;
    product_name: string;
    inventory_role: string | null;
    is_production_output: boolean;
    is_production_ingredient: boolean;
    is_menu_ingredient: boolean;
    balances: Array<{
      balance_id: string;
      branch_id: string;
      location_id: string;
      location_code: string | null;
      location_name: string | null;
      qty_on_hand: number;
      qty_reserved: number;
      cost_per_unit: number;
    }>;
  }>;
  transfer_candidates: StockCutoverCandidate[];
  candidate_count: number;
  candidate_total_qty: number;
  candidate_total_value: number;
  active_documents: Record<string, number>;
  blockers: StockCutoverIssue[];
  warnings: StockCutoverIssue[];
  is_ready: boolean;
  preview_token: string;
  required_confirmation: string;
  completed_run: StockCutoverRun | null;
};

export type BrandStockDashboard = {
  brand_id: string;
  brand_slug: string;
  generated_at: string;
  central: {
    raw: StockSummary;
    ready: StockSummary;
  };
  stores: Array<{
    branch_id: string;
    branch_code: string;
    branch_name: string;
    branch_type: string;
    store_location_id: string | null;
    store_location_code: string | null;
    store_location_name: string | null;
    is_valid: boolean;
    sku_count: number;
    total_qty: number;
    total_value: number;
    negative_count: number;
  }>;
  in_transit: {
    order_count: number;
    total_qty: number;
    items: Array<{
      transfer_order_id: string;
      transfer_order_number: string;
      branch_id: string;
      branch_name: string;
      product_id: string;
      sku: string;
      product_name: string;
      unit: string;
      qty_in_transit: number;
      expected_date: string | null;
    }>;
  };
  data_quality: {
    blocker_count: number;
    warning_count: number;
    unconfigured_store_count: number;
    negative_store_count: number;
  };
  cutover: {
    is_ready: boolean;
    candidate_count: number;
    candidate_total_qty: number;
    completed_run: StockCutoverRun | null;
  };
};

type StockSummary = {
  location: StockCutoverLocation | null;
  sku_count: number;
  total_qty: number;
  total_reserved: number;
  total_value: number;
  negative_count: number;
  items: Array<{
    product_id: string;
    sku: string;
    product_name: string;
    inventory_role: string | null;
    qty_on_hand: number;
    qty_reserved: number;
    cost_per_unit: number;
    stock_value: number;
  }>;
};

export type CreditAccount = {
  id: string;
  brand_id: string;
  branch_id: string;
  branch_name: string | null;
  branch_type: string;
  store_location_id?: string | null;
  credit_limit: number;
  balance: number;
  reserved_amount: number;
  available_credit: number;
  is_active: boolean;
};

export type CreditLedgerEntry = {
  id: string;
  entry_type: string;
  amount: number;
  balance_after: number;
  reserved_after: number;
  reference_type: string | null;
  reference_id: string | null;
  note: string | null;
  created_by: string;
  created_at: string | null;
};

export type CreditTopupRequest = {
  id: string;
  brand_id: string;
  branch_id: string;
  branch_name: string | null;
  account_id: string;
  amount: number;
  status: "pending" | "approved" | "rejected" | string;
  slip_url: string;
  note: string | null;
  requested_by: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  created_at: string | null;
};

export type BrandCreditPaymentConfig = {
  credit_topup_qr_url: string | null;
};

export type BrandTransferConfig = {
  central_branch_id: string | null;
  central_location_id: string | null;
  central_ready_location_id: string | null;
};

export type StoreStockDailyItem = {
  product_id: string;
  sku: string;
  product_name: string;
  inventory_role: string | null;
  unit_code: string | null;
  opening_qty: number;
  received_qty: number;
  used_sales_qty: number;
  sale_return_qty: number;
  waste_qty: number;
  adjustment_qty: number;
  other_net_qty: number;
  expected_closing_qty: number;
  physical_qty: number | null;
  variance_qty: number | null;
  current_qty: number;
  is_negative: boolean;
};

export type StoreStockDailySummary = {
  date: string;
  brand_id: string;
  branch_id: string;
  location_id: string;
  stock_count_session_id: string | null;
  stock_count_status: string | null;
  negative_count: number;
  items: StoreStockDailyItem[];
};

export type ReplenishmentSuggestionItem = {
  product_id: string;
  sku: string;
  product_name: string;
  unit: string;
  inventory_role: "central_ready" | string;
  store_on_hand_qty: number;
  received_today_qty: number;
  yesterday_usage_qty: number;
  average_7_day_qty: number;
  forecast_qty: number;
  confirmed_incoming_qty: number;
  safety_stock_percent: number;
  fixed_safety_stock_qty: number;
  safety_stock_qty: number;
  target_qty: number;
  raw_suggested_qty: number;
  suggested_qty: number;
  pack_size: number;
  minimum_order_qty: number;
  lead_time_days: number;
  target_date: string;
  configured_forecast_method: "auto" | "latest_day" | "average_7_open_days" | string;
  forecast_method: "latest_day" | "average_7_open_days" | string;
  open_day_count: number;
  policy_id: string | null;
  is_enabled: boolean;
  uses_default_policy: boolean;
  source: string;
};

export type ReplenishmentSuggestion = {
  date: string;
  default_target_date: string;
  brand_id: string;
  branch_id: string;
  location_id: string;
  open_business_dates: string[];
  formula: string;
  items: ReplenishmentSuggestionItem[];
};

export type ReplenishmentPolicyPayload = {
  is_enabled: boolean;
  safety_stock_percent: number;
  safety_stock_qty: number;
  pack_size: number;
  lead_time_days: number;
  forecast_method: "auto" | "latest_day" | "average_7_open_days";
  minimum_order_qty: number;
};

export type StoreStockAdjustmentPayload = {
  product_id: string;
  qty: number;
  kind: "waste" | "adjustment";
  reason: "prep_waste" | "expired" | "staff_sample" | "return_central" | "count_higher" | "count_lower" | "other";
  note?: string | null;
};

export type CentralOrderSubmitPayload = {
  items: Array<{
    product_id: string | null;
    sku: string;
    product_name: string;
    unit: string;
    system_qty: number;
    requested_qty: number;
    source?: string | null;
  }>;
  note?: string | null;
};

export type CentralOrderQtyPayload = {
  items: Array<{ item_id: string; qty: number }>;
};

export const wapApi = {
  menu: (brandSlug?: string) =>
    api.get<ApiResponse<WapMenu>>(brandSlug ? `/restaurant/store/${brandSlug}/menu` : "/restaurant/wap/menu"),
  storeStockDaily: (brandSlug: string, date?: string) =>
    api.get<ApiResponse<StoreStockDailySummary>>(`/restaurant/store/${brandSlug}/stock/daily`, { params: { date } }),
  replenishmentSuggestion: (brandSlug: string, date?: string) =>
    api.get<ApiResponse<ReplenishmentSuggestion>>(`/restaurant/store/${brandSlug}/replenishment-suggestion`, { params: { date } }),
  adjustStoreStock: (brandSlug: string, data: StoreStockAdjustmentPayload) =>
    api.post<ApiResponse<unknown>>(`/restaurant/store/${brandSlug}/stock/adjustments`, data),
  shiftCloseSummary: (date?: string, brandSlug?: string) =>
    api.get<ApiResponse<WapShiftCloseSummary>>(
      brandSlug ? `/restaurant/store/${brandSlug}/shift-close-summary` : "/restaurant/wap/shift-close-summary",
      { params: { date } }
    ),
  closeShift: (brandSlug?: string) =>
    api.post<ApiResponse<WapShiftCloseSummary>>(brandSlug ? `/restaurant/store/${brandSlug}/shift-close` : "/restaurant/wap/shift-close"),
  handoverCounterShift: (data: { closing_cash: number; note?: string | null }) =>
    api.post<ApiResponse<CashierShift>>("/restaurant/wap/staff-shift/handover", data),
  shiftClosures: (brandSlug?: string) =>
    api.get<ApiResponse<WapShiftClosure[]>>(brandSlug ? `/restaurant/store/${brandSlug}/shift-closures` : "/restaurant/wap/shift-closures"),
  cashierSales: (date?: string, brandSlug?: string) =>
    api.get<ApiResponse<WapCashierSales[]>>(
      brandSlug ? `/restaurant/store/${brandSlug}/reports/cashiers` : "/restaurant/wap/reports/cashiers",
      { params: { date } }
    ),
  submitCentralOrder: (closureId: string, data: CentralOrderSubmitPayload, brandSlug?: string) =>
    api.post<ApiResponse<CentralOrder>>(
      brandSlug ? `/restaurant/store/${brandSlug}/shift-closures/${closureId}/central-order` : `/restaurant/wap/shift-closures/${closureId}/central-order`,
      data
    ),
  dailyCentralOrderSummary: (date?: string, brandSlug?: string) =>
    api.get<ApiResponse<DailyCentralOrderSummary>>(
      brandSlug ? `/restaurant/store/${brandSlug}/daily-central-order-summary` : "/restaurant/wap/daily-central-order-summary",
      { params: { date } }
    ),
  submitDailyCentralOrder: (data: CentralOrderSubmitPayload, brandSlug?: string, date?: string) =>
    api.post<ApiResponse<CentralOrder>>(
      brandSlug ? `/restaurant/store/${brandSlug}/daily-central-order` : "/restaurant/wap/daily-central-order",
      data,
      { params: { date } }
    ),
  centralOrders: (brandSlug?: string) =>
    api.get<ApiResponse<CentralOrder[]>>(brandSlug ? `/restaurant/central/${brandSlug}/orders` : "/restaurant/central/orders"),
  centralOrder: (orderId: string, brandSlug?: string) =>
    api.get<ApiResponse<CentralOrder>>(brandSlug ? `/restaurant/central/${brandSlug}/orders/${orderId}` : `/restaurant/central/orders/${orderId}`),
  approveCentralOrder: (orderId: string, data: CentralOrderQtyPayload) =>
    api.post<ApiResponse<CentralOrder>>(`/restaurant/central/orders/${orderId}/approve`, data),
  packCentralOrder: (orderId: string, data: CentralOrderQtyPayload) =>
    api.post<ApiResponse<CentralOrder>>(`/restaurant/central/orders/${orderId}/pack`, data),
  shipCentralOrder: (orderId: string) =>
    api.post<ApiResponse<CentralOrder>>(`/restaurant/central/orders/${orderId}/ship`),
  cancelCentralOrder: (orderId: string, reason: string) =>
    api.post<ApiResponse<CentralOrder>>(`/restaurant/central/orders/${orderId}/cancel`, { reason }),
  centralProductionSummary: (brandSlug?: string, params?: { date_from?: string; date_to?: string; status?: string }) =>
    api.get<ApiResponse<CentralProductionSummaryItem[]>>(
      brandSlug ? `/restaurant/central/${brandSlug}/production-summary` : "/restaurant/central/production-summary",
      { params }
    ),
  centralProductionIngredients: (brandSlug?: string, params?: { date_from?: string; date_to?: string; status?: string }) =>
    api.get<ApiResponse<CentralProductionIngredientItem[]>>(
      brandSlug ? `/restaurant/central/${brandSlug}/production-ingredients` : "/restaurant/central/production-ingredients",
      { params }
    ),
  productionBatches: (brandSlug: string, params?: { date_from?: string; date_to?: string; status?: string }) =>
    api.get<ApiResponse<ProductionBatch[]>>(`/restaurant/central/${brandSlug}/production-batches`, { params }),
  productionBatch: (brandSlug: string, batchId: string) =>
    api.get<ApiResponse<ProductionBatch>>(`/restaurant/central/${brandSlug}/production-batches/${batchId}`),
  createProductionBatch: (brandSlug: string, data: {
    planned_date: string;
    inputs?: Array<{ product_id: string; planned_qty: number; unit_code?: string; cost_per_unit?: number }>;
    outputs: Array<{ product_id: string; planned_qty: number; unit_code?: string; cost_per_unit?: number }>;
    note?: string | null;
  }) => api.post<ApiResponse<ProductionBatch>>(`/restaurant/central/${brandSlug}/production-batches`, data),
  startProductionBatch: (brandSlug: string, batchId: string) =>
    api.post<ApiResponse<ProductionBatch>>(`/restaurant/central/${brandSlug}/production-batches/${batchId}/start`),
  completeProductionBatch: (brandSlug: string, batchId: string, data: {
    lines: Array<{ line_id: string; actual_qty: number }>;
    note?: string | null;
  }) => api.post<ApiResponse<ProductionBatch>>(
    `/restaurant/central/${brandSlug}/production-batches/${batchId}/complete`,
    data
  ),
  cancelProductionBatch: (brandSlug: string, batchId: string, reason: string) =>
    api.post<ApiResponse<ProductionBatch>>(
      `/restaurant/central/${brandSlug}/production-batches/${batchId}/cancel`,
      { reason }
    ),
  completeCentralProduction: (brandSlug: string, data: {
    location_id: string;
    date_from?: string;
    date_to?: string;
    status?: string;
    outputs: Array<{ product_id: string; qty: number; cost_per_unit?: number }>;
    inputs: Array<{ product_id: string; qty: number; cost_per_unit?: number }>;
    note?: string | null;
  }) => api.post<ApiResponse<{ input_count: number; output_count: number; movement_count: number }>>(
    `/restaurant/central/${brandSlug}/production-complete`,
    data
  ),
  brandOperationsReport: (brandSlug: string, params?: { date_from?: string; date_to?: string }) =>
    api.get<ApiResponse<BrandOperationsReport>>(`/restaurant/central/${brandSlug}/reports/operations`, { params }),
  brandFeatures: (brandSlug: string) =>
    api.get<ApiResponse<{ central_production: boolean }>>(`/restaurant/central/${brandSlug}/features`),
  brandStockDashboard: (brandSlug: string) =>
    api.get<ApiResponse<BrandStockDashboard>>(`/restaurant/central/${brandSlug}/stock-dashboard`),
  stockCutoverPreview: (brandSlug: string) =>
    api.get<ApiResponse<StockCutoverPreview>>(`/restaurant/central/${brandSlug}/cutover/preview`),
  executeStockCutover: (brandSlug: string, data: {
    preview_token: string;
    confirmation_text: string;
    note?: string | null;
  }) => api.post<ApiResponse<StockCutoverRun>>(`/restaurant/central/${brandSlug}/cutover/execute`, data),
  stockCutoverRuns: (brandSlug: string) =>
    api.get<ApiResponse<StockCutoverRun[]>>(`/restaurant/central/${brandSlug}/cutover/runs`),
  creditAccounts: (brandSlug: string) =>
    api.get<ApiResponse<CreditAccount[]>>(`/restaurant/central/${brandSlug}/credits`),
  topupCredit: (brandSlug: string, data: { branch_id: string; amount: number; note?: string | null }) =>
    api.post<ApiResponse<CreditAccount>>(`/restaurant/central/${brandSlug}/credits/topup`, data),
  adjustCredit: (brandSlug: string, data: { branch_id: string; amount: number; note?: string | null }) =>
    api.post<ApiResponse<CreditAccount>>(`/restaurant/central/${brandSlug}/credits/adjust`, data),
  refundCredit: (brandSlug: string, data: { branch_id: string; amount: number; note?: string | null }) =>
    api.post<ApiResponse<CreditAccount>>(`/restaurant/central/${brandSlug}/credits/refund`, data),
  updateBrandBranchType: (brandSlug: string, branchId: string, branchType: "company_owned" | "franchise") =>
    api.patch<ApiResponse<CreditAccount>>(`/restaurant/central/${brandSlug}/branches/${branchId}`, { branch_type: branchType }),
  transferConfig: (brandSlug: string) =>
    api.get<ApiResponse<BrandTransferConfig>>(`/restaurant/central/${brandSlug}/transfer-config`),
  updateTransferConfig: (brandSlug: string, data: {
    central_branch_id?: string | null;
    central_location_id?: string | null;
    central_ready_location_id?: string | null;
  }) =>
    api.patch<ApiResponse<BrandTransferConfig>>(`/restaurant/central/${brandSlug}/transfer-config`, data),
  updateBranchTransferConfig: (brandSlug: string, branchId: string, data: { store_location_id?: string | null }) =>
    api.patch<ApiResponse<CreditAccount>>(`/restaurant/central/${brandSlug}/branches/${branchId}/transfer-config`, data),
  centralReplenishmentPolicies: (brandSlug: string, branchId: string, date?: string) =>
    api.get<ApiResponse<ReplenishmentSuggestion>>(
      `/restaurant/central/${brandSlug}/branches/${branchId}/replenishment-policies`,
      { params: { date } }
    ),
  updateReplenishmentPolicy: (
    brandSlug: string,
    branchId: string,
    productId: string,
    data: ReplenishmentPolicyPayload,
  ) => api.put<ApiResponse<unknown>>(
    `/restaurant/central/${brandSlug}/branches/${branchId}/replenishment-policies/${productId}`,
    data,
  ),
  branches: () => api.get<ApiResponse<Branch[]>>("/system/branches"),
  stockLocations: (branchId?: string) => api.get<ApiResponse<StockLocation[]>>("/stock/locations", { params: { branch_id: branchId } }),
  creditLedger: (brandSlug: string, accountId: string) =>
    api.get<ApiResponse<CreditLedgerEntry[]>>(`/restaurant/central/${brandSlug}/credits/${accountId}/ledger`),
  storeCreditPaymentConfig: (brandSlug: string) =>
    api.get<ApiResponse<BrandCreditPaymentConfig>>(`/restaurant/store/${brandSlug}/credits/payment-config`),
  centralCreditPaymentConfig: (brandSlug: string) =>
    api.get<ApiResponse<BrandCreditPaymentConfig>>(`/restaurant/central/${brandSlug}/credits/payment-config`),
  uploadCentralCreditPaymentQr: (brandSlug: string, data: FormData) =>
    api.post<ApiResponse<BrandCreditPaymentConfig>>(`/restaurant/central/${brandSlug}/credits/payment-config/qr`, data, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  storeCreditTopupRequests: (brandSlug: string) =>
    api.get<ApiResponse<CreditTopupRequest[]>>(`/restaurant/store/${brandSlug}/credits/topup-requests`),
  createStoreCreditTopupRequest: (brandSlug: string, data: FormData) =>
    api.post<ApiResponse<CreditTopupRequest>>(`/restaurant/store/${brandSlug}/credits/topup-requests`, data, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  centralCreditTopupRequests: (brandSlug: string, status?: string) =>
    api.get<ApiResponse<CreditTopupRequest[]>>(`/restaurant/central/${brandSlug}/credits/topup-requests`, { params: { status } }),
  approveCreditTopupRequest: (brandSlug: string, requestId: string, note?: string | null) =>
    api.post<ApiResponse<CreditTopupRequest>>(`/restaurant/central/${brandSlug}/credits/topup-requests/${requestId}/approve`, { note }),
  rejectCreditTopupRequest: (brandSlug: string, requestId: string, note?: string | null) =>
    api.post<ApiResponse<CreditTopupRequest>>(`/restaurant/central/${brandSlug}/credits/topup-requests/${requestId}/reject`, { note }),
  branchCentralOrders: (brandSlug?: string) =>
    api.get<ApiResponse<CentralOrder[]>>(brandSlug ? `/restaurant/store/${brandSlug}/central-orders` : "/restaurant/wap/central-orders"),
  receiveBranchCentralOrder: (orderId: string, brandSlug?: string, data?: CentralOrderReceivePayload) =>
    api.post<ApiResponse<CentralOrder>>(
      brandSlug ? `/restaurant/store/${brandSlug}/central-orders/${orderId}/receive` : `/restaurant/wap/central-orders/${orderId}/receive`,
      data,
    ),
  createPaidOrder: (data: WapPaidOrderPayload, brandSlug?: string) =>
    api.post<ApiResponse<WapOrder>>(brandSlug ? `/restaurant/store/${brandSlug}/orders` : "/restaurant/wap/orders", data),
  syncPaidOrders: (brandSlug: string | undefined, orders: WapPaidOrderPayload[]) =>
    api.post<ApiResponse<WapOfflineSyncResponse>>(
      brandSlug ? `/restaurant/store/${brandSlug}/orders/sync` : "/restaurant/wap/orders/sync",
      { orders },
      { timeout: 8000 }
    ),
  getOrder: (sessionId: string) =>
    api.get<ApiResponse<WapOrder>>(`/restaurant/wap/orders/${sessionId}`),
  markCustomerSlip: (sessionId: string) =>
    api.post<ApiResponse<WapOrder>>(`/restaurant/wap/orders/${sessionId}/customer-slip`),
  markKitchenSlip: (sessionId: string) =>
    api.post<ApiResponse<WapOrder>>(`/restaurant/wap/orders/${sessionId}/kitchen-slip`),
};
