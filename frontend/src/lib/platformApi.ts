import axios, { type AxiosError } from "axios";
import type { SaasBillingOverview, SaasBillingSummary, SaasInvoice, SaasPlan } from "@/types/billing";
import type { PrivacyRequest, SupportAccessGrant, SupportContext, SupportMessage, SupportTicket } from "@/types/privacySupport";
import type { CompanyModuleAccess } from "@/types/moduleAccess";
import { usePlatformAuthStore } from "@/stores/platform-auth.store";
import type {
  PlatformAuditEvent,
  PlatformCompanyCreate,
  PlatformCompanyDetail,
  PlatformCompanyListItem,
  PlatformDashboard,
  PlatformMfaConfirm,
  PlatformMfaSetup,
  PlatformOperator,
  PlatformOperationsSnapshot,
  PlatformOperationsSummary,
  PlatformSession,
  PlatformTenantUsage,
  PlatformTenantUsageSnapshot,
  PlatformTenantExport,
  PlatformTokenResponse
} from "@/types/platform";

type PlatformApiResponse<T> = {
  data: T;
  meta: {
    version: string;
    identity_database: string;
    pagination?: { page: number; limit: number; total: number };
  };
  error: null;
};

const configuredApiOrigin = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/$/, "");
const apiBaseUrl = configuredApiOrigin
  ? configuredApiOrigin.endsWith("/api/v1")
    ? configuredApiOrigin
    : `${configuredApiOrigin}/api/v1`
  : "/api/v1";

const platformApiClient = axios.create({
  baseURL: `${apiBaseUrl}/platform`,
  withCredentials: true,
});

platformApiClient.interceptors.request.use((config) => {
  const token = usePlatformAuthStore.getState().accessToken;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let refreshRequest: Promise<PlatformTokenResponse> | null = null;

platformApiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const request = error.config;
    const isAuthEndpoint = request?.url?.includes("/auth/login") || request?.url?.includes("/auth/refresh");
    const alreadyRetried = Boolean((request as (typeof request & { _platformRetried?: boolean }) | undefined)?._platformRetried);
    if (error.response?.status === 401 && request && !isAuthEndpoint && !alreadyRetried) {
      const csrfToken = usePlatformAuthStore.getState().csrfToken;
      if (csrfToken) {
        try {
          refreshRequest ??= platformApiClient
            .post<PlatformApiResponse<PlatformTokenResponse>>(
              "/auth/refresh",
              null,
              { headers: { "X-Platform-CSRF": csrfToken } },
            )
            .then((response) => response.data.data)
            .finally(() => { refreshRequest = null; });
          const session = await refreshRequest;
          usePlatformAuthStore.getState().setSession(session);
          (request as typeof request & { _platformRetried?: boolean })._platformRetried = true;
          request.headers.Authorization = `Bearer ${session.access_token}`;
          return platformApiClient(request);
        } catch {
          // The shared failure path below clears the browser session.
        }
      }
      usePlatformAuthStore.getState().clearSession();
      const current = `${window.location.pathname}${window.location.search}`;
      window.location.href = `/platform/login?next=${encodeURIComponent(current)}`;
    }
    return Promise.reject(error);
  }
);

export const platformApi = {
  login: (username: string, password: string, mfaCode?: string) =>
    platformApiClient.post<PlatformApiResponse<PlatformTokenResponse>>("/auth/login", {
      username,
      password,
      mfa_code: mfaCode || null,
    }),
  refresh: (csrfToken: string) =>
    platformApiClient.post<PlatformApiResponse<PlatformTokenResponse>>(
      "/auth/refresh",
      null,
      { headers: { "X-Platform-CSRF": csrfToken } },
    ),
  logout: () => platformApiClient.post("/auth/logout"),
  logoutAll: () => platformApiClient.post("/auth/logout-all"),
  sessions: () => platformApiClient.get<PlatformApiResponse<PlatformSession[]>>("/auth/sessions"),
  revokeSession: (sessionId: string) => platformApiClient.delete(`/auth/sessions/${sessionId}`),
  setupMfa: () => platformApiClient.post<PlatformApiResponse<PlatformMfaSetup>>("/auth/mfa/setup"),
  confirmMfa: (code: string) =>
    platformApiClient.post<PlatformApiResponse<PlatformMfaConfirm>>("/auth/mfa/confirm", { code }),
  regenerateRecoveryCodes: (code: string) =>
    platformApiClient.post<PlatformApiResponse<{ recovery_codes: string[] }>>(
      "/auth/mfa/recovery-codes",
      { code },
    ),
  disableMfa: (password: string, code: string) =>
    platformApiClient.post<PlatformApiResponse<PlatformOperator>>("/auth/mfa/disable", { password, code }),
  changePassword: (currentPassword: string, newPassword: string, mfaCode?: string) =>
    platformApiClient.post("/auth/password", {
      current_password: currentPassword,
      new_password: newPassword,
      mfa_code: mfaCode || null,
    }),
  me: () => platformApiClient.get<PlatformApiResponse<PlatformOperator>>("/auth/me"),
  dashboard: () =>
    platformApiClient.get<PlatformApiResponse<PlatformDashboard>>("/dashboard"),
  captureUsageSnapshots: () =>
    platformApiClient.post<PlatformApiResponse<PlatformTenantUsageSnapshot[]>>("/usage/snapshots"),
  operationsSummary: () =>
    platformApiClient.get<PlatformApiResponse<PlatformOperationsSummary>>("/operations/summary"),
  operationsHistory: () =>
    platformApiClient.get<PlatformApiResponse<PlatformOperationsSnapshot[]>>("/operations/history"),
  captureOperations: () =>
    platformApiClient.post<PlatformApiResponse<PlatformOperationsSnapshot>>("/operations/capture"),
  billingOverview: () =>
    platformApiClient.get<PlatformApiResponse<SaasBillingOverview>>("/billing/overview"),
  upsertBillingPlan: (payload: {
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
    reason: string;
  }) => platformApiClient.post<PlatformApiResponse<SaasPlan>>("/billing/plans", payload),
  privacyRequests: () => platformApiClient.get<PlatformApiResponse<PrivacyRequest[]>>("/privacy/requests"),
  updatePrivacyRequest: (requestId: string, payload: { status: "identity_verified" | "in_review" | "fulfilled" | "rejected" | "cancelled"; response_summary: string | null; reason: string }) =>
    platformApiClient.put<PlatformApiResponse<PrivacyRequest>>(`/privacy/requests/${requestId}`, payload),
  supportTickets: () => platformApiClient.get<PlatformApiResponse<SupportTicket[]>>("/support/tickets"),
  updateSupportTicket: (ticketId: string, payload: { status: SupportTicket["status"]; priority: SupportTicket["priority"]; reason: string }) =>
    platformApiClient.put<PlatformApiResponse<SupportTicket>>(`/support/tickets/${ticketId}`, payload),
  addSupportMessage: (ticketId: string, body: string) =>
    platformApiClient.post<PlatformApiResponse<SupportMessage>>(`/support/tickets/${ticketId}/messages`, { body }),
  requestSupportAccess: (ticketId: string, payload: { requested_scopes: SupportAccessGrant["requested_scopes"]; purpose: string; duration_minutes: number; reason: string }) =>
    platformApiClient.post<PlatformApiResponse<SupportAccessGrant>>(`/support/tickets/${ticketId}/access`, payload),
  revokeSupportAccess: (grantId: string, reason: string) =>
    platformApiClient.post<PlatformApiResponse<SupportAccessGrant>>(`/support/access/${grantId}/revoke`, { reason }),
  supportContext: (grantId: string) =>
    platformApiClient.get<PlatformApiResponse<SupportContext>>(`/support/access/${grantId}/context`),
  companies: (search?: string) =>
    platformApiClient.get<PlatformApiResponse<PlatformCompanyListItem[]>>("/companies", {
      params: search ? { search } : undefined
    }),
  company: (companyId: string) =>
    platformApiClient.get<PlatformApiResponse<PlatformCompanyDetail>>(`/companies/${companyId}`),
  companyModules: (companyId: string) =>
    platformApiClient.get<PlatformApiResponse<CompanyModuleAccess[]>>(`/companies/${companyId}/modules`),
  updateCompanyModule: (
    companyId: string,
    moduleKey: CompanyModuleAccess["module_key"],
    payload: { enabled: boolean; reason: string },
  ) => platformApiClient.put<PlatformApiResponse<CompanyModuleAccess>>(
    `/companies/${companyId}/modules/${moduleKey}`,
    payload,
  ),
  companyUsage: (companyId: string) =>
    platformApiClient.get<PlatformApiResponse<PlatformTenantUsage>>(`/companies/${companyId}/usage`),
  companyUsageHistory: (companyId: string) =>
    platformApiClient.get<PlatformApiResponse<PlatformTenantUsageSnapshot[]>>(`/companies/${companyId}/usage/history`),
  companyBilling: (companyId: string) =>
    platformApiClient.get<PlatformApiResponse<SaasBillingSummary>>(`/companies/${companyId}/billing`),
  updateSubscription: (companyId: string, payload: {
    plan_code: string;
    status: "incomplete" | "trialing" | "active" | "past_due" | "paused" | "cancelled";
    current_period_start: string | null;
    current_period_end: string | null;
    cancel_at_period_end: boolean;
    reason: string;
  }) => platformApiClient.put<PlatformApiResponse<SaasBillingSummary>>(
    `/companies/${companyId}/billing/subscription`, payload
  ),
  createInvoice: (companyId: string, payload: {
    status: "draft" | "open";
    currency: string;
    subtotal_satang: number;
    tax_satang: number;
    memo: string | null;
    reason: string;
  }) => platformApiClient.post<PlatformApiResponse<SaasInvoice>>(
    `/companies/${companyId}/billing/invoices`, payload
  ),
  createCompany: (payload: PlatformCompanyCreate) =>
    platformApiClient.post<PlatformApiResponse<PlatformCompanyDetail>>("/companies", payload),
  suspendCompany: (companyId: string, reason: string) =>
    platformApiClient.post<PlatformApiResponse<PlatformCompanyDetail>>(
      `/companies/${companyId}/suspend`,
      { reason }
    ),
  reactivateCompany: (companyId: string, reason: string) =>
    platformApiClient.post<PlatformApiResponse<PlatformCompanyDetail>>(
      `/companies/${companyId}/reactivate`,
      { reason }
    ),
  updateControls: (
    companyId: string,
    payload: {
      plan_code: string;
      feature_flags: Record<string, boolean>;
      plan_limits: Record<string, number>;
      reason: string;
    }
  ) =>
    platformApiClient.put<PlatformApiResponse<PlatformCompanyDetail>>(
      `/companies/${companyId}/controls`,
      payload
    ),
  exportCompany: (companyId: string, reason: string) =>
    platformApiClient.post<PlatformApiResponse<PlatformTenantExport>>(
      `/companies/${companyId}/export`,
      { reason }
    ),
  audit: (companyId?: string) =>
    platformApiClient.get<PlatformApiResponse<PlatformAuditEvent[]>>("/audit", {
      params: companyId ? { company_id: companyId } : undefined
    })
};

export function platformErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (!error.response) return "เชื่อมต่อ Platform API ไม่ได้";
  }
  return error instanceof Error ? error.message : "ดำเนินการไม่สำเร็จ";
}
