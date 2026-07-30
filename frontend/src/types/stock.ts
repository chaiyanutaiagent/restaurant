export interface StockLocation {
  id: string;
  company_id: string;
  branch_id: string;
  code: string;
  name: string;
  description: string | null;
  is_active: boolean;
}

export interface StockLocationPayload {
  branch_id: string;
  code: string;
  name: string;
  description?: string | null;
  is_active: boolean;
}

export type StockLocationUpdatePayload = Partial<StockLocationPayload>;

export interface StockBalance {
  id: string;
  product_id: string;
  variant_id: string | null;
  location_id: string;
  branch_id: string;
  qty_on_hand: number;
  qty_reserved: number;
  qty_available: number;
  cost_per_unit: number;
  last_movement_at: string | null;
  product_name: string;
  product_sku: string;
  unit_code: string | null;
  variant_name: string | null;
  location_name?: string | null;
  min_stock_qty?: number;
}

export interface StockMovement {
  id: string;
  product_id: string;
  variant_id: string | null;
  location_id: string;
  branch_id: string;
  movement_type: string;
  qty: number;
  qty_before: number;
  qty_after: number;
  cost_per_unit: number;
  note: string | null;
  reference_type: string | null;
  reference_id: string | null;
  user_id: string;
  user_name?: string | null;
  created_at: string;
  product_name: string;
  product_sku: string;
  variant_name: string | null;
}

export interface StockSummary {
  total_skus: number;
  total_value: number;
  low_stock_count: number;
  zero_stock_count: number;
}

export type MovementType =
  | "receive"
  | "issue"
  | "adjust"
  | "transfer_in"
  | "transfer_out"
  | "sale"
  | "sale_return"
  | "purchase_return"
  | "opening"
  | "waste";
