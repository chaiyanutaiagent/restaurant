import api from "@/lib/api";
import type { ApiResponse } from "@/types/api";

export type BrandNavigationBranch = {
  branch_id: string;
  branch_code: string;
  branch_name: string;
  branch_type: "company_owned" | "franchise" | string;
  store_location_configured: boolean;
  landing_path: string;
  is_current: boolean;
};

export type BrandNavigationItem = {
  id: string;
  slug: string;
  name: string;
  business_type: "restaurant";
  target_database: "restaurant";
  central_branch_id: string | null;
  central_landing_path: string | null;
  branches: BrandNavigationBranch[];
};

export const brandNavigationApi = {
  mine: () =>
    api.get<ApiResponse<BrandNavigationItem[]>>(
      "/restaurant/me/brand-navigation"
    )
};
