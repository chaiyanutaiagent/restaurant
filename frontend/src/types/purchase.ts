export type POStatus =
  | "draft"
  | "pending_approval"
  | "approved"
  | "partially_received"
  | "fully_received"
  | "cancelled";

export interface Supplier {
  id: string;
  company_id: string;
  code: string;
  name: string;
  name_en: string | null;
  tax_id: string | null;
  branch_code: string | null;
  address: string | null;
  phone: string | null;
  email: string | null;
  contact_person: string | null;
  payment_term_days: number;
  wht_rate: number;
  wht_type: string | null;
  credit_limit: number;
  bank_name: string | null;
  bank_account: string | null;
  bank_account_name: string | null;
  note: string | null;
  is_active: boolean;
}

export interface POItem {
  id: string;
  po_id: string;
  product_id: string;
  variant_id: string | null;
  product_name: string;
  sku: string;
  unit_code: string | null;
  qty_ordered: number;
  qty_received: number;
  unit_cost: number;
  discount_amount: number;
  vat_type: string;
  vat_rate: number;
  vat_amount: number;
  subtotal: number;
}

export interface PurchaseOrder {
  id: string;
  po_number: string;
  status: POStatus;
  branch_id: string;
  supplier_id: string;
  created_by: string;
  approved_by: string | null;
  order_date: string;
  expected_date: string | null;
  approved_at: string | null;
  subtotal: number;
  discount_amount: number;
  vat_amount: number;
  wht_amount: number;
  total_amount: number;
  paid_amount: number;
  remaining_amount: number;
  vat_type: string;
  vat_rate: number;
  wht_rate: number;
  note: string | null;
  created_at: string;
  updated_at: string;
  items: POItem[];
  supplier: Supplier;
}

export interface POListItem {
  id: string;
  po_number: string;
  status: POStatus;
  order_date: string;
  expected_date: string | null;
  supplier_id: string;
  supplier_name: string;
  total_amount: number;
  paid_amount: number;
  remaining_amount: number;
  item_count: number;
}

export interface GRItem {
  id: string;
  gr_id: string;
  po_item_id: string;
  product_id: string;
  variant_id: string | null;
  qty_received: number;
  unit_cost: number;
  note: string | null;
}

export interface GoodsReceipt {
  id: string;
  gr_number: string;
  po_id: string;
  branch_id: string;
  location_id: string;
  received_by: string;
  received_date: string;
  note: string | null;
  created_at: string;
  items: GRItem[];
}
