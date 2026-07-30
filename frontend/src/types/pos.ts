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
}

export interface Payment {
  id: string;
  payment_method: PaymentMethod;
  amount: number;
  reference_no: string | null;
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
}

export interface HeldSaleDraft {
  id: string;
  shift_id: string;
  location_id: string;
  branch_id: string | null;
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
}
