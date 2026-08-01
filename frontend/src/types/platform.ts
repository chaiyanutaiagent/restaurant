export type PlatformOperator = {
  id: string;
  username: string;
  email: string | null;
  display_name: string;
  is_superuser: boolean;
  last_login_at: string | null;
};

export type PlatformTokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
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
  key: "company" | "brand" | "branch" | "menu" | "payment" | "staff" | "device";
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
