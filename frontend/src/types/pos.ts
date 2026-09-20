export type PaymentMethod = "cash" | "promptpay" | "credit_card" | "bank_transfer" | "other";
export type ShiftStatus = "open" | "closed";
export type OrderStatus = "completed" | "voided" | "partially_refunded" | "refunded" | "pending_sync";

export interface CashierShift {
  id: string;
  shift_number: string;
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
  paid_at: string;
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
  assignee_user_id?: string | null;
  origin_device_id?: string | null;
  origin_device_code?: string | null;
  claim_id?: string | null;
  claimed_by?: string | null;
  claim_expires_at?: string | null;
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
  assignee_user_id: string | null;
  origin_device_id: string | null;
  origin_device_code: string | null;
  label: string;
  source_type: "walk_in" | "takeaway" | "restaurant_table" | "restaurant_quick_service";
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
  pricing_snapshot: Record<string, unknown>;
  status: "active" | "claimed" | "resumed" | "expired" | "converted" | "cancelled";
  version: number;
  claim_id: string | null;
  claimed_by: string | null;
  claimed_device_id: string | null;
  claim_expires_at: string | null;
  expires_at: string;
  resumed_at: string | null;
  resumed_by: string | null;
  cancel_reason: string | null;
  created_at: string;
  updated_at: string;
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
