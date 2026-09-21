export type PaymentMethod = "cash" | "promptpay" | "credit_card" | "bank_transfer" | "other";
export type ShiftStatus = "open" | "closed";
export type OrderStatus = "completed" | "voided" | "partially_refunded" | "refunded" | "pending_sync";

export interface CashierShift {
  id: string;
  shift_number: string;
  shift_type: "staff_cashier" | "operational_cashless";
  version: number;
  status: ShiftStatus;
  branch_id: string;
  location_id: string;
  user_id: string;
  opened_at: string;
  closed_at: string | null;
  opening_cash: number;
  closing_cash: number | null;
  expected_cash: number | null;
  cash_difference: number | null;
  total_sales: number;
  total_orders: number;
  total_voids: number;
  close_reason_code: string | null;
  cash_count_json: Array<{ denomination: number; quantity: number }> | null;
  opened_device_id: string | null;
  opened_device_code: string | null;
  closed_device_id: string | null;
  closed_device_code: string | null;
  closed_by_user_id: string | null;
  close_snapshot_json: PosShiftSummary | null;
}

export interface ShiftBlocker {
  code: string;
  count: number;
  message: string;
  action_path: string;
}

export interface ShiftCashMovement {
  id: string;
  movement_type: "cash_in" | "cash_out";
  amount: string;
  reason_code: string;
  reason: string;
  requester_id: string;
  approver_id: string | null;
  posted_at: string;
  journal_entry_id: string | null;
}

export interface PosShiftSummary {
  shift_id: string;
  shift_number: string;
  shift_type: string;
  status: ShiftStatus;
  version: number;
  company_id: string;
  branch_id: string;
  location_id: string;
  operator_user_id: string;
  opened_at: string;
  opening_cash: string;
  gross_sales: string;
  net_sales: string;
  refund_total: string;
  void_total: string;
  order_count: number;
  void_count: number;
  payment_totals: Record<string, string>;
  cash_received_net: string;
  change_total: string;
  cash_in_total: string;
  cash_out_total: string;
  expected_cash: string;
  cash_movements: ShiftCashMovement[];
  pending: {
    hold_drafts: number;
    refunds: number;
    offline_operations: number;
    unresolved_payments: number;
  };
  journal: {
    state: "matched" | "needs_reconciliation" | "not_applicable";
    missing_sales: number;
    missing_cash_movements: number;
  };
  blockers: ShiftBlocker[];
  can_close: boolean;
  reopen_allowed: false;
}

export interface CashMovement {
  id: string;
  shift_id: string;
  movement_type: "cash_in" | "cash_out";
  amount: number;
  reason_code: string;
  reason: string;
  status: "posted";
  shift_version: number;
  requester_id: string;
  approver_id: string | null;
  device_code: string | null;
  journal_entry_id: string | null;
  posted_at: string;
}

export interface CartItem {
  product_id: string;
  variant_id: string | null;
  product_name: string;
  variant_name: string | null;
  sku: string;
  unit_code: string | null;
  qty: number;
  unit_price: number;
  original_price: number;
  discount_amount: number;
  discount_type: "amount" | "percent";
  vat_type: string;
  vat_rate: number;
  subtotal: number;
  vat_amount: number;
  expected_price_version?: string | null;
  price_override?: {
    requested_unit_price: number;
    reason_code?: "customer_recovery" | "price_match" | "manager_comp" | "damaged_item" | "manual_correction" | "other";
    reason: string;
  } | null;
}

export interface Cart {
  items: CartItem[];
  discount_amount: number;
  discount_type: "amount" | "percent";
  subtotal: number;
  order_discount: number;
  vat_amount: number;
  total_amount: number;
}

export interface SaleOrderItem {
  id: string;
  product_id: string;
  variant_id: string | null;
  product_name: string;
  variant_name: string | null;
  sku: string;
  unit_code: string | null;
  qty: number;
  unit_price: number;
  original_price: number;
  discount_amount: number;
  vat_type: string;
  vat_rate: number;
  vat_amount: number;
  subtotal: number;
  refunded_qty?: number;
  refunded_amount?: number;
  price_source?: string | null;
  price_list_id?: string | null;
  price_list_version?: number | null;
  price_version?: string | null;
  price_snapshot?: Record<string, unknown> | null;
  order_discount_share?: number;
  line_total?: number;
  price_override_applied?: boolean;
  price_override_reason?: string | null;
}

export interface Payment {
  id: string;
  payment_method: PaymentMethod;
  amount: number;
  reference_no: string | null;
  original_payment_id?: string | null;
  currency?: string;
  provider_name?: string | null;
  provider_payment_ref?: string | null;
  settlement_state?: string;
  refund_operation_id?: string | null;
  provider_refund_state?: string | null;
  paid_at: string;
}

export type RefundOperationStatus =
  | "requested"
  | "processing"
  | "cash_due"
  | "succeeded"
  | "failed"
  | "unknown"
  | "needs_reconciliation"
  | "tax_pending"
  | "completed";

export interface RefundQuote {
  id: string;
  order_id: string;
  shift_id: string;
  status: string;
  currency: string;
  order_version: number;
  quote_hash: string;
  items: Array<{
    sale_order_item_id: string;
    product_name: string;
    quantity: string;
    subtotal_amount: string;
    discount_amount: string;
    vat_amount: string;
    total_amount: string;
    stock_disposition: "none" | "sellable";
  }>;
  payment_allocations: Array<{
    original_payment_id: string;
    payment_method: string;
    leg_type: "cash" | "provider";
    provider_name: string | null;
    amount: string;
    currency: string;
  }>;
  totals: {
    subtotal_amount: string;
    discount_amount: string;
    vat_amount: string;
    rounding_amount: string;
    total_amount: string;
    remaining_refundable_before: string;
    rounding_rule: string;
  };
  policy: Record<string, unknown>;
  expires_at: string;
}

export interface RefundOperation {
  id: string;
  order_id: string;
  quote_id: string;
  shift_id: string;
  status: RefundOperationStatus;
  reason_code: string;
  reason_note: string | null;
  currency: string;
  subtotal_amount: number;
  discount_amount: number;
  vat_amount: number;
  rounding_amount: number;
  total_amount: number;
  stock_disposition: string;
  provider_scenario: string;
  row_version: number;
  failure_code: string | null;
  failure_message: string | null;
  finalized_at: string | null;
  tax_completed_at: string | null;
  items: Array<Record<string, unknown>>;
  payment_legs: Array<{
    id: string;
    payment_method: string;
    leg_type: "cash" | "provider";
    provider_name: string | null;
    amount: number;
    currency: string;
    status: string;
    provider_refund_ref: string | null;
    attempt_count: number;
    last_error_code: string | null;
  }>;
  tax: {
    status: string;
    original_document_id: string | null;
    credit_note_id: string | null;
    retry_count: number;
    last_error: string | null;
  } | null;
  created_at: string;
}

export interface PaymentDraft {
  payment_method: PaymentMethod;
  amount: number;
  reference_no?: string | null;
}

export interface ExchangeContextDraft {
  source_order_id: string;
  source_order_number: string;
  refund_amount: number;
  refunded_items: string[];
  source_items?: Array<{
    product_id: string;
    product_name: string;
    qty?: number;
  }>;
  refund_reason: string;
}

export interface ReplacementRuleDraft {
  id: string;
  branch_id: string | null;
  source_product_id: string;
  source_product_name: string;
  replacement_product_id: string;
  replacement_product_name: string;
  created_at: number;
}

export interface SaleOrder {
  id: string;
  order_number: string;
  status: OrderStatus;
  branch_id: string;
  location_id: string;
  shift_id: string;
  user_id: string;
  customer_name: string | null;
  customer_phone: string | null;
  customer_tax_id?: string | null;
  subtotal: number;
  discount_amount: number;
  vat_amount: number;
  total_amount: number;
  refund_amount?: number;
  paid_amount: number;
  change_amount: number;
  is_offline: boolean;
  note: string | null;
  created_at: string;
  synced_at?: string | null;
  items: SaleOrderItem[];
  payments: Payment[];
  pricing_quote_id?: string | null;
  pricing_request_hash?: string | null;
  pricing_calculation_hash?: string | null;
  pricing_calculation_version?: string | null;
  pricing_context?: Record<string, unknown> | null;
  pricing_snapshot?: Record<string, unknown> | null;
  row_version?: number;
}

export interface PricingLineResult {
  product_id: string;
  variant_id: string | null;
  authoritative_unit_price: number;
  applied_unit_price: number;
  promotion_code?: string | null;
  promotion_discount_amount?: number;
  price_version: string;
  effective_at?: string;
  rounding_rule?: string;
  line_total: number;
  discrepancy: boolean;
  override_requested: boolean;
  override_requires_approval: boolean;
}

export interface PricingCalculation {
  quote_id: string;
  idempotency_key: string;
  calculation_hash: string;
  calculation_version: string;
  cart_version: number;
  subtotal: number;
  discount_amount: number;
  promotion_discount_amount?: number;
  discount_percentage: number;
  vat_amount: number;
  total_amount: number;
  rounding_rule?: string;
  effective_at?: string;
  expires_at: string;
  requires_price_override_approval: boolean;
  has_price_discrepancy: boolean;
  lines: PricingLineResult[];
}

export interface PendingSale {
  client_order_id: string;
  shift_id: string;
  location_id: string;
  items: CartItem[];
  customer_id?: string | null;
  discount_amount: number;
  discount_type: string;
  payment_method: PaymentMethod;
  payments?: PaymentDraft[];
  payment_reference?: string | null;
  paid_amount: number;
  customer_name: string | null;
  customer_phone?: string | null;
  customer_tax_id?: string | null;
  note?: string | null;
  exchange_context?: ExchangeContextDraft | null;
  total_amount: number;
  change_amount: number;
  created_at: number;
  synced: boolean;
  approval_token?: string | null;
}

export interface HeldSaleDraft {
  id: string;
  shift_id: string;
  location_id: string;
  branch_id: string | null;
  sales_channel?: "walk_in" | "takeaway";
  label: string;
  items: CartItem[];
  order_discount: number;
  loyalty_discount: number;
  payment_method: PaymentMethod;
  paid_amount: number;
  payment_reference: string | null;
  split_payment_enabled?: boolean;
  secondary_payment_method?: PaymentMethod;
  secondary_payment_amount?: number;
  secondary_payment_reference?: string | null;
  customer_name: string;
  customer_phone: string;
  customer_tax_id: string;
  customer_search: string;
  selected_customer: import("@/types/crm").Customer | null;
  note: string;
  exchange_context?: ExchangeContextDraft | null;
  held_at: number;
  sync_state?: "local_only" | "pending_sync" | "synced" | "needs_review";
  server_id?: string;
  draft_no?: string;
  status?: "active" | "claimed" | "resumed" | "expired" | "converted" | "cancelled";
  version?: number;
  expires_at?: string;
  owner_user_id?: string;
  owner_display?: string | null;
  assignee_user_id?: string | null;
  assignee_display?: string | null;
  origin_device_id?: string | null;
  origin_device_code?: string | null;
  origin_shift_number?: string | null;
  location_name?: string | null;
  table_id?: string | null;
  queue_label?: string | null;
  claim_id?: string | null;
  claimed_by?: string | null;
  claim_expires_at?: string | null;
  last_revalidation?: Record<string, unknown> | null;
  resumed_at?: string | null;
  expired_at?: string | null;
  cancelled_at?: string | null;
  converted_at?: string | null;
  cancel_reason?: string | null;
  server_backed?: boolean;
}

export interface ServerHoldDraft {
  id: string;
  draft_no: string;
  company_id: string;
  brand_id: string | null;
  branch_id: string;
  location_id: string;
  origin_shift_id: string;
  owner_user_id: string;
  owner_display: string | null;
  assignee_user_id: string | null;
  assignee_display: string | null;
  origin_device_id: string | null;
  origin_device_code: string | null;
  origin_shift_number: string | null;
  location_name: string | null;
  parent_draft_id: string | null;
  converted_order_id: string | null;
  label: string;
  source_type: "walk_in" | "takeaway" | "restaurant_table" | "restaurant_quick_service";
  table_id: string | null;
  queue_label: string | null;
  customer_id: string | null;
  customer_display: string | null;
  note: string | null;
  content: {
    items: CartItem[];
    order_discount: string;
    loyalty_discount_intent: string;
    currency: string;
    cart_version: number;
  };
  pricing_context: Record<string, unknown>;
  pricing_snapshot: Record<string, unknown>;
  last_revalidation: Record<string, unknown> | null;
  status: "active" | "claimed" | "resumed" | "expired" | "converted" | "cancelled";
  version: number;
  claim_id: string | null;
  claimed_by: string | null;
  claimed_device_id: string | null;
  claim_expires_at: string | null;
  expires_at: string;
  resumed_at: string | null;
  resumed_by: string | null;
  expired_at: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  converted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface HoldDraftAuditEntry {
  id: string;
  action: string;
  from_status: ServerHoldDraft["status"] | null;
  to_status: ServerHoldDraft["status"];
  from_version: number | null;
  to_version: number;
  actor_user_id: string;
  actor_display: string | null;
  device_id: string | null;
  shift_id: string | null;
  reason: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface HoldDraftClaimResult {
  draft: ServerHoldDraft;
  resume_cart: {
    items: CartItem[];
    pricing: PricingCalculation & Record<string, unknown>;
  };
  price_changes: Array<Record<string, unknown>>;
  requires_review: boolean;
}
