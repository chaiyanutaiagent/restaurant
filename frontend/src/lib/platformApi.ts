import axios, { type AxiosError } from "axios";
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
  companies: (search?: string) =>
    platformApiClient.get<PlatformApiResponse<PlatformCompanyListItem[]>>("/companies", {
      params: search ? { search } : undefined
    }),
  company: (companyId: string) =>
    platformApiClient.get<PlatformApiResponse<PlatformCompanyDetail>>(`/companies/${companyId}`),
  companyUsage: (companyId: string) =>
    platformApiClient.get<PlatformApiResponse<PlatformTenantUsage>>(`/companies/${companyId}/usage`),
  companyUsageHistory: (companyId: string) =>
    platformApiClient.get<PlatformApiResponse<PlatformTenantUsageSnapshot[]>>(`/companies/${companyId}/usage/history`),
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
