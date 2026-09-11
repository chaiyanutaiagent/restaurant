export type PrivacyRequest = {
  id: string;
  company_id: string;
  requester_user_id: string;
  request_type: "access" | "export" | "correction" | "deletion" | "restriction" | "objection" | "consent_withdrawal";
  subject_email: string;
  description: string | null;
  status: string;
  identity_verification: string;
  target_at: string;
  response_summary: string | null;
  decision_reason: string | null;
  reviewed_by: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type SupportMessage = {
  id: string;
  ticket_id: string;
  company_id: string;
  sender_type: "tenant_owner" | "platform_operator";
  sender_user_id: string | null;
  sender_operator_id: string | null;
  body: string;
  created_at: string;
};

export type SupportAccessGrant = {
  id: string;
  ticket_id: string;
  company_id: string;
  requested_by_operator_id: string;
  requested_scopes: Array<"account_state" | "saas_controls" | "aggregate_usage" | "billing_state">;
  purpose: string;
  duration_minutes: number;
  status: "pending" | "approved" | "denied" | "revoked";
  decided_by_user_id: string | null;
  decision_reason: string | null;
  decided_at: string | null;
  expires_at: string | null;
  last_accessed_at: string | null;
  revoked_at: string | null;
  revoked_by_type: string | null;
  revoke_reason: string | null;
  created_at: string;
  updated_at: string;
};

export type SupportTicket = {
  id: string;
  ticket_number: string;
  company_id: string;
  requester_user_id: string;
  category: "account" | "billing" | "technical" | "privacy" | "other";
  priority: "low" | "normal" | "high" | "urgent";
  status: "open" | "in_progress" | "waiting_tenant" | "resolved" | "closed";
  subject: string;
  assigned_operator_id: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  messages: SupportMessage[];
  access_grants: SupportAccessGrant[];
};

export type SupportContext = {
  grant_id: string;
  company_id: string;
  ticket_id: string;
  expires_at: string;
  scopes: string[];
  context: Record<string, unknown>;
};
