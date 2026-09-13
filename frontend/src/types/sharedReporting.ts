export type ReportingModuleKey = "restaurant_pos" | "takeaway_pos" | "retail_pos";

export type MoneyValue = number | string;

export type SharedSalesMetrics = {
  order_count: number;
  void_count: number;
  refund_count: number;
  gross_sales: MoneyValue;
  discount_amount: MoneyValue;
  tax_amount: MoneyValue;
  refund_amount: MoneyValue;
  net_sales: MoneyValue;
};

export type SharedSalesModuleSummary = SharedSalesMetrics & {
  module_key: ReportingModuleKey;
};

export type SharedSalesWorkspaceSummary = SharedSalesMetrics & {
  module_key: ReportingModuleKey;
  brand_id: string;
  brand_name: string;
  branch_id: string;
  branch_name: string;
};

export type SharedSalesDailySummary = SharedSalesMetrics & {
  business_date: string;
};

export type SharedSalesDocument = {
  module_key: ReportingModuleKey;
  brand_id: string;
  brand_name: string;
  branch_id: string;
  branch_name: string;
  business_date: string;
  source_document_type: string;
  source_document_id: string;
  document_number: string | null;
  source_status: string;
  gross_sales: MoneyValue;
  refund_amount: MoneyValue;
  net_sales: MoneyValue;
  entry_route: string;
};

export type SharedReportingFreshness = {
  status: "disabled" | "no_data" | "current" | "stale" | "degraded";
  projector_enabled: boolean;
  projection_mode: "shadow";
  is_source_of_truth: false;
  last_projected_at: string | null;
  last_polled_at: string | null;
  lag_seconds: number | null;
  failed_sources: string[];
};

export type SharedSalesReport = {
  company_id: string;
  date_from: string;
  date_to: string;
  generated_at: string;
  freshness: SharedReportingFreshness;
  totals: SharedSalesMetrics;
  modules: SharedSalesModuleSummary[];
  workspaces: SharedSalesWorkspaceSummary[];
  daily: SharedSalesDailySummary[];
  recent_documents: SharedSalesDocument[];
};

export type SharedSalesReportFilters = {
  date_from: string;
  date_to: string;
  module_key?: ReportingModuleKey;
  brand_id?: string;
  branch_id?: string;
};
