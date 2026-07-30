export type TOStatus =
  | "draft"
  | "pending_approval"
  | "approved"
  | "in_transit"
  | "partially_received"
  | "completed"
  | "cancelled";

export interface TOItem {
  id: string;
  to_id: string;
  product_id: string;
  variant_id: string | null;
  product_name: string;
  sku: string;
  unit_code: string | null;
  qty_requested: number;
  qty_approved: number | null;
  qty_sent: number | null;
  qty_received: number | null;
  unit_cost: number;
  qty_in_transit: number;
  qty_discrepancy: number;
}

export interface TransferOrder {
  id: string;
  to_number: string;
  status: TOStatus;
  from_branch_id: string;
  to_branch_id: string;
  from_location_id: string;
  to_location_id: string;
  from_branch_name: string;
  to_branch_name: string;
  from_location_name: string;
  to_location_name: string;
  requested_by: string;
  requested_by_name: string;
  approved_by: string | null;
  received_by: string | null;
  request_date: string;
  expected_date: string | null;
  approved_at: string | null;
  shipped_at: string | null;
  last_received_at: string | null;
  completed_at: string | null;
  has_discrepancy: boolean;
  discrepancy_note: string | null;
  note: string | null;
  created_at: string;
  updated_at: string;
  items: TOItem[];
}

export interface TOListItem {
  id: string;
  to_number: string;
  status: TOStatus;
  from_branch_name: string;
  to_branch_name: string;
  request_date: string;
  expected_date: string | null;
  item_count: number;
  requested_by_name: string;
}

export interface BranchStockSummary {
  branch_id: string;
  branch_name: string;
  location_count: number;
  product_count: number;
  total_value: number;
  low_stock_count: number;
  zero_stock_count: number;
}

export interface MultiBranchStockResponse {
  branches: BranchStockSummary[];
  grand_total_value: number;
  grand_low_stock_count: number;
}
