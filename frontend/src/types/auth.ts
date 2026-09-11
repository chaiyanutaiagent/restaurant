import type { User } from "@/types/user";

export interface LoginRequest {
  username: string;
  password: string;
  company_id?: string;
  branch_id?: string;
  station_key?: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  business_slug: string;
  user: User;
}

export interface MeResponse {
  user: User;
  company_id: string;
  business_slug: string;
  branch_id: string | null;
  brand_id: string | null;
  business_type: "restaurant" | "retail_pos" | "takeaway" | null;
  target_database: "restaurant" | "retail_pos" | "takeaway" | null;
  station_key: string | null;
  assignment_ids: string[];
  scope_types: Array<"company" | "brand" | "branch" | "station">;
  permissions: string[];
}
