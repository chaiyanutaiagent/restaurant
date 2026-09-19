import type { CompanyModuleAccess } from "@/types/moduleAccess";

export type RuntimeEnvironment = "production" | "uat";
export type OperationalState = "online" | "offline" | "degraded" | "pending_sync" | "stale" | "error" | "disabled";

export type CompanyContext = {
  contract_version: string;
  environment: RuntimeEnvironment;
  company: { id: string; code: string | null; name: string };
  brand: { id: string; code: string | null; name: string } | null;
  branch: { id: string; code: string | null; name: string } | null;
  station_or_device_id: string | null;
  business_type: string | null;
  target_database: string | null;
  timezone: string;
  currency: string;
  tax: {
    scope: "company" | "branch";
    configured: boolean;
    vat_registered: boolean;
    tax_id: string | null;
    tax_branch_code: string | null;
    price_vat_type: string;
    vat_rate: number;
  };
  all_scope_allowed: Record<"brand" | "branch" | "station", boolean>;
  transport: {
    authoritative_source: "signed_token";
    company_header: string;
    branch_header: string;
    client_context_is_trusted: false;
    switch_requires_new_token: true;
  };
  updated_at: string;
};

export type EffectiveAccess = {
  contract_version: string;
  company_id: string;
  user_id: string;
  scope_types: string[];
  assignment_ids: string[];
  permissions: string[];
  default_route: string;
  modules: CompanyModuleAccess[];
};

export type CompanyWorkItem = {
  id: string;
  type: string;
  source_app: string;
  severity: "info" | "warning" | "error" | "blocker";
  title: string;
  company_id: string;
  brand_id: string | null;
  branch_id: string | null;
  owner_id: string | null;
  due_at: string | null;
  status: "open" | "acknowledged" | "completed" | "dismissed";
  permission_required: string;
  available_actions: Array<"assign" | "acknowledge" | "approve" | "return" | "complete" | "dismiss">;
  deep_link: string;
  unread: boolean;
  business_impact: number;
  created_at: string;
  updated_at: string;
};

export type CompanyActionCenter = {
  contract_version: string;
  items: CompanyWorkItem[];
  total: number;
  unread: number;
  generated_at: string;
};

export type CompanyOverviewMetric = {
  key: string;
  label: string;
  value: number | string;
  severity: "info" | "warning" | "error" | "blocker";
  deep_link: string | null;
};

export type CompanyOverviewSection = {
  module_key: CompanyModuleAccess["module_key"];
  title: string;
  readiness: CompanyModuleAccess["readiness"];
  data_source: string;
  status: OperationalState;
  metrics: CompanyOverviewMetric[];
  updated_at: string;
  stale: boolean;
  error_code: string | null;
};

export type CompanyOverview = {
  contract_version: string;
  context: CompanyContext;
  task_summary: Record<string, number>;
  sections: CompanyOverviewSection[];
  generated_at: string;
};

export type OperationalComponent = {
  id: string;
  component_type: string;
  name: string;
  state: OperationalState;
  company_id: string;
  branch_id: string | null;
  station_key: string | null;
  last_seen_at: string | null;
  last_sync_at: string | null;
  queue_size: number;
  error_code: string | null;
  retryable: boolean;
  source_system: string;
  updated_at: string;
};

export type OperationalStatus = {
  contract_version: string;
  components: OperationalComponent[];
  summary: Record<OperationalState, number>;
  generated_at: string;
};
