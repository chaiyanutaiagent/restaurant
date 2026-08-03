export type PlatformOperator = {
  id: string;
  username: string;
  email: string | null;
  display_name: string;
  is_superuser: boolean;
  mfa_enabled: boolean;
  last_login_at: string | null;
};

export type PlatformTokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  csrf_token: string;
  session_id: string;
  operator: PlatformOperator;
};

export type PlatformSession = {
  id: string;
  current: boolean;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  mfa_verified_at: string | null;
  revoked_at: string | null;
  ip_address: string | null;
  user_agent: string | null;
};

export type PlatformMfaSetup = {
  secret: string;
  provisioning_uri: string;
};

export type PlatformMfaConfirm = {
  recovery_codes: string[];
  operator: PlatformOperator;
};

export type PlatformCompanyListItem = {
  id: string;
  name: string;
  name_en: string | null;
  tax_id: string | null;
  email: string | null;
  is_active: boolean;
  credential_version: number;
  plan_code: string;
  created_at: string;
  suspended_at: string | null;
};

export type PlatformOnboardingStep = {
  key: "product" | "company" | "brand" | "branch" | "menu" | "payment" | "staff" | "device";
  label: string;
  complete: boolean;
  count: number;
  target: number;
};

export type PlatformCompanyDetail = PlatformCompanyListItem & {
  phone: string | null;
  currency: string;
  timezone: string;
  controls: {
    plan_code: string;
    feature_flags: Record<string, boolean>;
    plan_limits: Record<string, number>;
  };
  onboarding: {
    complete: boolean;
    completed_steps: number;
    total_steps: number;
    steps: PlatformOnboardingStep[];
  };
  suspension_reason: string | null;
  reactivated_at: string | null;
  reactivation_reason: string | null;
  updated_at: string;
};

export type PlatformCompanyCreate = {
  name: string;
  name_en?: string | null;
  tax_id?: string | null;
  email?: string | null;
  phone?: string | null;
  currency: string;
  timezone: string;
  plan_code: string;
  feature_flags: Record<string, boolean>;
  plan_limits: Record<string, number>;
  owner: {
    username: string;
    password: string;
    email?: string | null;
    display_name: string;
  };
  reason: string;
};

export type PlatformTenantExport = {
  format: "restaurant-tenant-export";
  format_version: number;
  generated_at: string;
  company_id: string;
  content_sha256: string;
  request: { reason: string; requested_by: string };
  redaction: {
    policy: string;
    marker: string;
    redacted_cells: number;
  };
  summary: {
    boundary_count: number;
    table_count: number;
    row_count: number;
  };
  boundaries: Record<
    string,
    {
      aliases: string[];
      table_count: number;
      tables: Record<
        string,
        {
          row_count: number;
          redacted_columns: string[];
          rows: Array<Record<string, unknown>>;
        }
      >;
    }
  >;
};

export type PlatformAuditEvent = {
  id: string;
  company_id: string | null;
  operator_id: string | null;
  action: string;
  resource: string | null;
  resource_id: string | null;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
};

export type PlatformDashboardCompany = PlatformCompanyListItem & {
  onboarding_complete: boolean;
  completed_steps: number;
  total_steps: number;
  last_activity_at: string | null;
  attention_codes: string[];
};

export type PlatformLimitState = {
  resource_key: string;
  current: number;
  limit: number | null;
  unlimited: boolean;
  exceeded: boolean;
  remaining: number | null;
  utilization_percent: number | null;
};

export type PlatformTenantUsage = {
  company_id: string;
  generated_at: string;
  plan_code: string;
  feature_flags: Record<string, boolean>;
  plan_limits: Record<string, number>;
  usage: Record<string, number>;
  limit_state: Record<string, PlatformLimitState>;
  attention_codes: string[];
  last_activity_at: string | null;
  onboarding_completed_steps: number;
  onboarding_total_steps: number;
};

export type PlatformTenantUsageSnapshot = Omit<PlatformTenantUsage, "generated_at"> & {
  id: string;
  captured_on: string;
  created_at: string;
  updated_at: string;
};

export type PlatformDashboard = {
  generated_at: string;
  totals: {
    companies: number;
    active_companies: number;
    suspended_companies: number;
    brands: number;
    branches: number;
    enabled_user_accounts: number;
    devices: number;
    paired_devices: number;
  };
  onboarding: {
    ready_companies: number;
    pending_companies: number;
    total_active_companies: number;
  };
  product_status: Record<string, "pilot" | "planned">;
  attention_summary: Record<string, number>;
  feature_usage: Record<string, number>;
  plan_usage: Record<string, number>;
  recent_companies: PlatformDashboardCompany[];
  recent_events: PlatformAuditEvent[];
};
