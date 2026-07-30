import type { CashierShift, SaleOrder } from "@/types/pos";

export interface DailySalesSummary {
  date: string;
  date_thai: string;
  total_orders: number;
  total_amount: number;
  total_vat: number;
  total_discount: number;
  avg_order_value: number;
  by_payment_method: Record<string, number>;
}

export interface SalesRangeSummary {
  date_from: string;
  date_to: string;
  days: DailySalesSummary[];
  grand_total_orders: number;
  grand_total_amount: number;
  grand_total_vat: number;
  grand_total_discount: number;
  by_payment_method: Record<string, number>;
}

export interface TopProductItem {
  product_id: string;
  product_name: string;
  sku: string;
  total_qty: number;
  total_amount: number;
  order_count: number;
}

export interface TopProductsReport {
  date_from: string;
  date_to: string;
  items: TopProductItem[];
}

export interface HourlySales {
  hour: number;
  total_orders: number;
  total_amount: number;
}

export interface DashboardStats {
  today_orders: number;
  today_sales: number;
  today_vat: number;
  today_avg_order: number;
  open_shifts_count: number;
  low_stock_count: number;
  total_products: number;
  compared_yesterday_pct: number | null;
}

export interface ShiftSummary {
  shift: CashierShift;
  sales: SaleOrder[];
  voided: SaleOrder[];
  cashier_name: string;
  branch_name: string;
  location_name: string;
  by_payment_method: Record<string, number>;
  daily_summary: DailySalesSummary;
}
