export interface StorefrontCompany {
  id: string;
  name: string;
  business_slug: string;
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

export interface PublicExperienceCapabilities {
  catalog: boolean;
  branch_locator: boolean;
  ecommerce: boolean;
  checkout: boolean;
  payment: boolean;
  member_portal: boolean;
  digital_receipt: boolean;
}

export interface PublicExperience {
  mode: "catalog_locator";
  release_stage: "public_read_only";
  generated_at: string;
  stale_after_seconds: number;
  capabilities: PublicExperienceCapabilities;
  hard_holds: string[];
}

export interface StorefrontSummary {
  company: StorefrontCompany;
  featured_products: StorefrontProduct[];
  branches: StorefrontBranch[];
  experience: PublicExperience;
}
