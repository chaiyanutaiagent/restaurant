import type { PlatformModuleAvailability, PlatformModuleKey } from "@/config/platformModules";

export type CompanyModuleReasonCode =
  | "enabled"
  | "company_inactive"
  | "lifecycle_planned"
  | "not_in_plan"
  | "company_disabled"
  | "runtime_unavailable"
  | "permission_denied";

export type CompanyModuleAccess = {
  module_key: Exclude<PlatformModuleKey, "company_admin">;
  lifecycle: PlatformModuleAvailability;
  readiness: "production" | "pilot" | "dark_launch" | "read_only" | "legacy" | "planned";
  environment: "production" | "uat";
  company_enabled: boolean;
  plan_included: boolean;
  runtime_ready: boolean;
  user_permitted: boolean;
  effective_access: boolean;
  reason_code: CompanyModuleReasonCode;
  allowed_actions: Array<"view" | "create" | "update" | "approve" | "refund" | "export" | "suspend" | "execute">;
  enabled_branch_ids: string[];
  branch_scope: "all" | "selected" | "none";
  feature_flags: Record<string, boolean>;
  data_source: string;
  status_reason: string | null;
  updated_at: string;
  updated_by: string | null;
  audit_id: string | null;
};
