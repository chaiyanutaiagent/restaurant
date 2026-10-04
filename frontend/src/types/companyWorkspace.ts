import type { CompanyModuleAccess } from "@/types/moduleAccess";

type CompanyModuleKey = CompanyModuleAccess["module_key"];

export type WorkspaceModuleKey = "restaurant_pos" | "takeaway_pos" | "retail_pos";
export type WorkspaceBusinessType = "restaurant" | "takeaway" | "retail_pos";

export type CompanyWorkspace = {
  workspace_id: string;
  module_key: WorkspaceModuleKey;
  business_type: WorkspaceBusinessType;
  brand_id: string;
  brand_slug: string;
  brand_name: string;
  branch_id: string;
  branch_code: string;
  branch_name: string;
  branch_type: string;
  storefront_mode: string;
  is_active: boolean;
  can_open: boolean;
  entry_route: string;
};

export type CompanyWorkspaceModule = {
  module_key: CompanyModuleKey;
  kind: "shared_service" | "workspace_collection" | "planned";
  entry_route: string | null;
  can_provision: boolean;
  access: CompanyModuleAccess;
  workspaces: CompanyWorkspace[];
};

export type CompanyWorkspaceDirectory = {
  company_id: string;
  generated_at: string;
  modules: CompanyWorkspaceModule[];
};

export type CompanyWorkspaceProvisionRequest = {
  idempotency_key: string;
  module_key: WorkspaceModuleKey;
  brand_slug: string;
  brand_name: string;
  branch_code: string;
  branch_name: string;
  branch_type: "company_owned" | "franchise";
  storefront_mode: "food_stall" | "drink_shop";
};

export type CompanyWorkspaceProvisionResult = {
  created: boolean;
  created_resources: Array<"brand" | "branch" | "workspace">;
  workspace: CompanyWorkspace;
};
