export interface Unit {
  id: string;
  company_id: string;
  code: string;
  name: string;
  name_en: string | null;
  decimal_places: number;
  is_active: boolean;
}

export interface Category {
  id: string;
  company_id: string;
  parent_id: string | null;
  code: string | null;
  name: string;
  name_en: string | null;
  sort_order: number;
  is_active: boolean;
  image_url: string | null;
  children: Category[];
}

export interface ProductImage {
  id: string;
  url: string;
  filename: string;
  is_primary: boolean;
  sort_order: number;
}

export interface ProductVariant {
  id: string;
  product_id: string;
  sku: string;
  barcode: string | null;
  name: string;
  attributes: Record<string, string> | null;
  cost_price: string | number | null;
  selling_price: string | number | null;
  is_active: boolean;
  sort_order: number;
  image_url: string | null;
}

export interface Product {
  id: string;
  company_id: string;
  sku: string;
  barcode: string | null;
  name: string;
  name_en: string | null;
  description: string | null;
  description_en?: string | null;
  product_type: ProductType;
  inventory_role?: InventoryRole | null;
  cost_price: string | number;
  selling_price: string | number;
  vat_type: VatType;
  vat_rate: string | number;
  category_id: string | null;
  unit_id: string | null;
  is_active: boolean;
  is_for_sale: boolean;
  is_for_purchase: boolean;
  image_url: string | null;
  min_stock_qty: string | number;
  weight_grams?: number | null;
  category: Category | null;
  unit: Unit | null;
  variants: ProductVariant[];
  images: ProductImage[];
  created_at: string;
  updated_at: string;
}

export interface ProductListItem {
  id: string;
  sku: string;
  barcode: string | null;
  name: string;
  product_type: ProductType | string;
  inventory_role?: InventoryRole | null;
  cost_price: string | number;
  selling_price: string | number;
  vat_type: VatType;
  vat_rate: string | number;
  is_active: boolean;
  image_url: string | null;
  category_id: string | null;
  unit_id: string | null;
  unit: Unit | null;
  brand_id: string | null;
  min_stock_qty?: string | number;
  created_at: string;
}

export interface PriceList {
  id: string;
  company_id: string;
  name: string;
  description: string | null;
  currency: string;
  brand_id?: string | null;
  branch_id?: string | null;
  customer_id?: string | null;
  channel?: string | null;
  priority?: number;
  version?: number;
  price_kind?: "standard" | "promotion";
  promotion_code?: string | null;
  valid_from_at?: string | null;
  valid_until_at?: string | null;
  is_default: boolean;
  is_active: boolean;
}

export type VatType = "included" | "excluded" | "zero" | "exempt";
export type ProductType = "simple" | "variant" | "service" | "bundle" | "menu_item" | "raw_material";
export type InventoryRole = "central_raw" | "central_ready" | "store_local" | "not_stocked";
