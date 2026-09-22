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

export type CompanyErpReadinessState = "ready" | "attention" | "blocked" | "hold" | "permission_denied";

export type CompanyErpReadinessArea = {
  key: "purchasing" | "inventory" | "finance_tax" | "reporting";
  title: string;
  state: CompanyErpReadinessState;
  open_items: number;
  permission_required: string;
  deep_link: string | null;
  read_only: boolean;
  message: string;
};

export type CompanyErpException = {
  id: string;
  source: "purchase" | "transfer" | "stock_count" | "payable" | "tax";
  title: string;
  reference: string;
  severity: "info" | "warning" | "error" | "blocker";
  branch_id: string | null;
  branch_name: string | null;
  owner_id: string | null;
  age_hours: number;
  due_at: string | null;
  deep_link: string;
  permission_required: string;
  evidence_reference: string;
  created_at: string;
};

export type CompanyErpReadiness = {
  contract_version: string;
  context: CompanyContext;
  areas: CompanyErpReadinessArea[];
  exceptions: CompanyErpException[];
  finance: {
    period_year: number;
    period_month: number;
    period_status: "not_started" | "open" | "review" | "closed" | "locked";
    tax_configured: boolean;
    open_blockers: number;
    open_warnings: number;
    pending_reconciliation: number;
    accountant_signoff: "pending" | "recorded";
    ready_to_close: boolean;
    deep_link: string | null;
  } | null;
  controls: Array<{
    key: string;
    label: string;
    state: "enforced" | "hold";
    detail: string;
  }>;
  summary: Record<"open_exceptions" | "blockers" | "errors" | "overdue" | "holds", number>;
  source_system: "operational_database";
  source_updated_at: string | null;
  stale_after_seconds: number;
  generated_at: string;
};
