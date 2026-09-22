import type { SupplyChainRelease } from "@/types/supplyChainRelease";

export type CompanyKitchen = {
  id: string;
  name: string;
  branch_id: string;
  branch_name: string;
  raw_location_id: string;
  raw_location_name: string;
  timezone: string;
  costing_method: "fifo";
  allow_negative_stock: false;
  is_active: boolean;
};

export type CompanyIngredient = {
  id: string;
  code: string;
  name: string;
  canonical_product_id: string;
  base_unit_code: string;
  unit_dimension: "mass" | "volume" | "count";
  qty_on_hand: number | string;
  is_active: boolean;
};

export type CompanyIngredientAlias = {
  id: string;
  ingredient_id: string;
  ingredient_name: string;
  brand_id: string;
  brand_name: string;
  source_product_id: string;
  source_product_name: string;
  source_unit_code: string;
  conversion_factor: number | string;
  supplier_sku: string | null;
};

export type CompanyProductionDemand = {
  id: string;
  brand_id: string;
  brand_name: string;
  branch_id: string;
  branch_name: string;
  output_product_id: string;
  output_product_name: string;
  needed_on: string;
  requested_qty: number | string;
  unit_code: string;
  status: "submitted" | "converted" | "cancelled";
  source_type: string;
  source_id: string;
  note: string | null;
};

export type CompanyProductionInput = {
  id: string;
  ingredient_id: string;
  ingredient_name: string;
  planned_qty: number | string;
  actual_qty: number | string | null;
  base_unit_code: string;
  actual_cost: number | string;
};

export type CompanyProductionOrder = {
  id: string;
  order_number: string;
  brand_id: string;
  brand_name: string;
  output_product_id: string;
  output_product_name: string;
  planned_date: string;
  status: "planned" | "in_progress" | "completed" | "reversed" | "cancelled";
  planned_qty: number | string;
  actual_output_qty: number | string | null;
  waste_qty: number | string;
  output_unit_code: string;
  total_input_cost: number | string;
  output_cost_per_unit: number | string;
  demand_id: string | null;
  recipe_id: string;
  note: string | null;
  inputs: CompanyProductionInput[];
};

export type CompanyKitchenDashboard = {
  kitchen: CompanyKitchen | null;
  ingredients: CompanyIngredient[];
  aliases: CompanyIngredientAlias[];
  demands: CompanyProductionDemand[];
  orders: CompanyProductionOrder[];
  write_enabled: boolean;
  release: SupplyChainRelease;
  setup_options: {
    branches: Array<{ id: string; name: string; code: string }>;
    locations: Array<{ id: string; branch_id: string; name: string; code: string }>;
    brands: Array<{ id: string; name: string; business_type: string }>;
    brand_branches: Array<{ brand_id: string; branch_id: string }>;
    products: Array<{
      id: string;
      name: string;
      sku: string;
      brand_id: string | null;
      inventory_role: "central_raw" | "central_ready";
      unit_code: string | null;
    }>;
  };
};

export type CompanyKitchenReport = {
  date_from: string;
  date_to: string;
  production_by_brand: Array<{
    brand_id: string;
    brand_name: string;
    order_count: number;
    completed_count: number;
    output_qty: number | string;
    waste_qty: number | string;
    input_cost: number | string;
  }>;
  ingredient_usage: Array<{
    brand_id: string;
    brand_name: string;
    ingredient_id: string;
    ingredient_name: string;
    consumed_qty: number | string;
    reversed_qty: number | string;
    net_cost: number | string;
    unit_code: string;
  }>;
  orders: CompanyProductionOrder[];
};
