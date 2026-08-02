import axios, { type AxiosError } from "axios";
import { usePlatformAuthStore } from "@/stores/platform-auth.store";
import type {
  PlatformAuditEvent,
  PlatformCompanyCreate,
  PlatformCompanyDetail,
  PlatformCompanyListItem,
  PlatformDashboard,
  PlatformOperator,
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

const platformApiClient = axios.create({ baseURL: `${apiBaseUrl}/platform` });

platformApiClient.interceptors.request.use((config) => {
  const token = usePlatformAuthStore.getState().accessToken;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

platformApiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401 && !error.config?.url?.includes("/auth/login")) {
      usePlatformAuthStore.getState().clearSession();
      const current = `${window.location.pathname}${window.location.search}`;
      window.location.href = `/platform/login?next=${encodeURIComponent(current)}`;
    }
    return Promise.reject(error);
  }
);

export const platformApi = {
  login: (username: string, password: string) =>
    platformApiClient.post<PlatformApiResponse<PlatformTokenResponse>>("/auth/login", {
      username,
      password
    }),
  me: () => platformApiClient.get<PlatformApiResponse<PlatformOperator>>("/auth/me"),
  dashboard: () =>
    platformApiClient.get<PlatformApiResponse<PlatformDashboard>>("/dashboard"),
  companies: (search?: string) =>
    platformApiClient.get<PlatformApiResponse<PlatformCompanyListItem[]>>("/companies", {
      params: search ? { search } : undefined
    }),
  company: (companyId: string) =>
    platformApiClient.get<PlatformApiResponse<PlatformCompanyDetail>>(`/companies/${companyId}`),
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
