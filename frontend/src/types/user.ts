export interface User {
  id: string;
  username: string;
  email: string | null;
  phone: string | null;
  first_name: string | null;
  last_name: string | null;
  display_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  company_id: string;
  last_login_at: string | null;
}

export interface Branch {
  id: string;
  company_id: string;
  brand_id?: string | null;
  business_type?: "restaurant" | "retail_pos" | "takeaway" | null;
  target_database?: "restaurant" | "retail_pos" | "takeaway" | null;
  code: string;
  name: string;
  name_en: string | null;
  address?: string | null;
  landmark?: string | null;
  phone?: string | null;
  email?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  google_maps_url?: string | null;
  is_warehouse: boolean;
  is_active: boolean;
  sort_order: number;
}

export interface Permission {
  id: string;
  code: string;
  name: string;
  module: string;
}

export interface Role {
  id: string;
  company_id: string;
  name: string;
  description: string | null;
  is_system: boolean;
  permissions: Permission[];
}

export interface UserBranch {
  branch_id: string;
  branch_name: string;
  branch_code: string;
  brand_id: string | null;
  business_type: "restaurant" | "retail_pos" | "takeaway" | null;
  target_database: "restaurant" | "retail_pos" | "takeaway" | null;
  role_name: string;
  is_default: boolean;
  station_key: string | null;
}
