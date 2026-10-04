export type SaasPlan = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  currency: string;
  billing_interval: "month" | "year";
  unit_amount_satang: number | null;
  feature_flags: Record<string, boolean>;
  plan_limits: Record<string, number>;
  is_public: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type SaasSubscription = {
  id: string;
  company_id: string;
  plan_id: string;
  status: "incomplete" | "trialing" | "active" | "past_due" | "paused" | "cancelled";
  current_period_start: string | null;
  current_period_end: string | null;
  trial_started_at: string | null;
  trial_ends_at: string | null;
  cancel_at_period_end: boolean;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
};

export type SaasInvoice = {
  id: string;
  subscription_id: string;
  company_id: string;
  invoice_number: string;
  status: "draft" | "open" | "paid" | "void" | "uncollectible";
  currency: string;
  subtotal_satang: number;
  tax_satang: number;
  total_satang: number;
  paid_satang: number;
  period_start: string | null;
  period_end: string | null;
  due_at: string | null;
  paid_at: string | null;
  memo: string | null;
  created_at: string;
  updated_at: string;
};

export type SaasBillingSummary = {
  company_id: string;
  provider: string;
  live_charging_enabled: boolean;
  collection_available: boolean;
  plan: SaasPlan | null;
  subscription: SaasSubscription | null;
  invoices: SaasInvoice[];
};

export type SaasBillingOverview = {
  provider: string;
  live_charging_enabled: boolean;
  collection_available: boolean;
  plans: SaasPlan[];
  subscription_counts: Record<string, number>;
  invoice_counts: Record<string, number>;
};
