export type AccessReviewOutcome = "retain" | "reduce" | "revoke" | "investigate";

export interface CompanyAccessReviewUser {
  id: string;
  username: string;
  display_name: string;
  email: string | null;
  is_active: boolean;
  is_superuser: boolean;
  credential_version: number;
  mfa_state: "enabled" | "not_configured";
  last_login_at: string | null;
  active_session_count: number;
  role_names: string[];
  risk_flags: string[];
  access_reviewed_at: string | null;
  access_review_due_at: string | null;
  access_review_outcome: AccessReviewOutcome | null;
  review_due: boolean;
  stale_access: boolean;
}

export interface CompanyTenantSession {
  id: string;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
  ip_address: string | null;
  user_agent: string | null;
  state: "active" | "revoked" | "expired";
}

export interface CompanyTenantSecurity {
  tenant_mfa_policy: "hold";
  tenant_mfa_enforcement_enabled: false;
  session_management_enabled: boolean;
  recovery_process_state: "product_owner_decision_required";
  suspicious_login_alert_state: "planned";
  note: string;
}

export interface CompanyAuditEvent {
  id: string;
  company_id: string | null;
  branch_id: string | null;
  user_id: string | null;
  action: string;
  resource: string | null;
  resource_id: string | null;
  old_value: unknown;
  new_value: unknown;
  deep_link: string | null;
  created_at: string;
}

export interface CompanyAuditPage {
  items: CompanyAuditEvent[];
  total: number;
  page: number;
  limit: number;
}
