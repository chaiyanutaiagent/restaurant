export type SaasMembership = {
  company_id: string;
  owner_email: string;
  status: "pending_verification" | "trial_active" | "trial_expired" | "active" | "suspended" | "cancelled";
  onboarding_state: "awaiting_verification" | "setup_required" | "ready";
  email_verified_at: string | null;
  trial_started_at: string | null;
  trial_ends_at: string | null;
  trial_days_remaining: number | null;
};

export type SaasSignupResponse = {
  company_id: string;
  business_slug: string;
  status: string;
  verification_required: boolean;
  message: string;
};

export type SaasBusiness = {
  company_id: string;
  business_slug: string;
  name: string;
  logo_url: string | null;
};

export type SaasActionResponse = {
  message: string;
  membership: SaasMembership | null;
};
