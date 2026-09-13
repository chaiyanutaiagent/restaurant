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
  company_enabled: boolean;
  plan_included: boolean;
  runtime_ready: boolean;
  user_permitted: boolean;
  effective_access: boolean;
  reason_code: CompanyModuleReasonCode;
  updated_at: string;
  updated_by: string | null;
  audit_id: string | null;
};
