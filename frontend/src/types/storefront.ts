export interface StorefrontCompany {
  id: string;
  name: string;
  name_en: string | null;
  tax_id: string | null;
  vat_registered: boolean;
  address: string | null;
  phone: string | null;
  email: string | null;
  logo_url: string | null;
  website: string | null;
  currency: string;
  timezone: string;
}

export interface StorefrontProduct {
  id: string;
  sku: string;
  barcode: string | null;
  name: string;
  name_en: string | null;
  description: string | null;
  selling_price: number;
  vat_type: string;
  vat_rate: number;
  category_id: string | null;
  category_name: string | null;
  unit_code: string | null;
  image_url: string | null;
  is_active: boolean;
  total_qty_available: number;
  in_stock: boolean;
}

export interface StorefrontBranch {
  id: string;
  code: string;
  name: string;
  name_en: string | null;
  address: string | null;
  landmark: string | null;
  phone: string | null;
  email: string | null;
  latitude: number | null;
  longitude: number | null;
  google_maps_url: string | null;
  working_hours: Record<string, { open?: string; close?: string; closed?: boolean }> | null;
  is_active: boolean;
  is_pickup_available: boolean;
}

export interface StorefrontSummary {
  company: StorefrontCompany;
  featured_products: StorefrontProduct[];
  branches: StorefrontBranch[];
}
