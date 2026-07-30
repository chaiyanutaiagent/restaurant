export type CountStatus = "draft" | "in_progress" | "completed" | "cancelled";

export interface CountItem {
  id: string;
  session_id: string;
  product_id: string;
  variant_id: string | null;
  product_name: string;
  sku: string;
  unit_code: string | null;
  expected_qty: number;
  actual_qty: number | null;
  variance_qty: number | null;
  cost_per_unit: number;
  variance_value: number | null;
  counted_at: string | null;
  counted_by: string | null;
  note: string | null;
  is_adjusted: boolean;
}

export interface CountSession {
  id: string;
  session_number: string;
  status: CountStatus;
  branch_id: string;
  location_id: string;
  count_date: string;
  started_at: string | null;
  completed_at: string | null;
  created_by: string;
  completed_by: string | null;
  note: string | null;
  total_items: number;
  items_matched: number;
  items_over: number;
  items_short: number;
  total_variance_value: number;
  items: CountItem[];
}

export interface CountSessionListItem {
  id: string;
  session_number: string;
  status: CountStatus;
  branch_id: string;
  location_id: string;
  count_date: string;
  created_by: string;
  completed_by: string | null;
  total_items: number;
  items_matched: number;
  items_over: number;
  items_short: number;
  total_variance_value: number;
}

export interface VarianceReportItem {
  product_name: string;
  sku: string;
  unit_code: string | null;
  expected_qty: number;
  actual_qty: number;
  variance_qty: number;
  variance_value: number;
  variance_pct: number;
}

export interface VarianceReport {
  session_number: string;
  location_name: string;
  branch_name: string;
  count_date: string;
  count_date_thai: string;
  completed_by_name: string;
  items_matched: number;
  items_over: number;
  items_short: number;
  total_variance_value: number;
  variances: VarianceReportItem[];
  matched_items: VarianceReportItem[];
}
