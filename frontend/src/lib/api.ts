import axios, {
  AxiosError,
  type AxiosResponse,
  type InternalAxiosRequestConfig
} from "axios";
import { useAuthStore } from "@/stores/auth.store";
import { useDeviceStore } from "@/stores/device.store";
import type { ApiResponse } from "@/types/api";
import type { LoginRequest, MeResponse, TokenResponse } from "@/types/auth";
import type { Branch, Permission, User, UserBranch } from "@/types/user";
import type { SaasActionResponse, SaasBusiness, SaasMembership, SaasSignupResponse } from "@/types/membership";
import type { SaasBillingSummary } from "@/types/billing";
import type { PrivacyRequest, SupportAccessGrant, SupportMessage, SupportTicket } from "@/types/privacySupport";

type RetryableConfig = InternalAxiosRequestConfig & {
  _retry?: boolean;
};

type QueueItem = {
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
};

const configuredApiOrigin = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/$/, "");
const apiBaseUrl = configuredApiOrigin
  ? (configuredApiOrigin.endsWith("/api/v1") ? configuredApiOrigin : `${configuredApiOrigin}/api/v1`)
  : "/api/v1";

const api = axios.create({ baseURL: apiBaseUrl });

api.interceptors.request.use((config) => {
  const { accessToken, companyId, branchId } = useAuthStore.getState();
  const deviceState = useDeviceStore.getState();

  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  if (companyId) {
    config.headers["X-Company-ID"] = companyId;
  }
  if (branchId) {
    config.headers["X-Branch-ID"] = branchId;
  }
  if (
    window.location.pathname.startsWith("/counter")
    && deviceState.isAuthenticated()
    && deviceState.device?.device_type === "counter"
    && deviceState.device.branch_id === branchId
  ) {
    config.headers["X-Device-Authorization"] = `Bearer ${deviceState.accessToken}`;
  }

  return config;
});

let isRefreshing = false;
let failedQueue: QueueItem[] = [];

function loginRedirectForCurrentPage(): string {
  const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (window.location.pathname === "/login" || /^\/[a-z0-9][a-z0-9-]{1,61}[a-z0-9]\/login$/.test(window.location.pathname)) {
    return current;
  }

  const canonicalTenant = window.location.pathname.match(/^\/([a-z0-9][a-z0-9-]{1,61}[a-z0-9])\/admin(?:\/|$)/);
  if (canonicalTenant) {
    return `/${canonicalTenant[1]}/login?next=${encodeURIComponent(current)}`;
  }

  return `/login?next=${encodeURIComponent(current)}`;
}

function processQueue(error: unknown, token?: string): void {
  failedQueue.forEach((item) => {
    if (error) {
      item.reject(error);
      return;
    }

    item.resolve(token ?? "");
  });
  failedQueue = [];
}

api.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: AxiosError) => {
    const original = error.config as RetryableConfig | undefined;
    const isAuthRequest = original?.url?.includes("/auth/login") || original?.url?.includes("/auth/refresh");

    if (error.response?.status === 401 && original && !original._retry && !isAuthRequest) {
      original._retry = true;

      if (isRefreshing) {
        return new Promise<string>((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          original.headers.Authorization = `Bearer ${token}`;
          return api(original);
        });
      }

      isRefreshing = true;

      try {
        const { refreshToken, companyId } = useAuthStore.getState();
        if (!refreshToken || !companyId) {
          throw new Error("No refresh session");
        }

        const response = await axios.post<ApiResponse<TokenResponse>>(
          `${apiBaseUrl}/auth/refresh`,
          { refresh_token: refreshToken },
          { headers: { "X-Company-ID": companyId } }
        );

        const tokenData = response.data.data;
        useAuthStore.getState().setSession(tokenData, companyId);
        processQueue(null, tokenData.access_token);
        original.headers.Authorization = `Bearer ${tokenData.access_token}`;
        return api(original);
      } catch (refreshError) {
        processQueue(refreshError);
        if (axios.isAxiosError(refreshError) && !refreshError.response) {
          return Promise.reject(refreshError);
        }
        useAuthStore.getState().clearSession();
        window.location.href = loginRedirectForCurrentPage();
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default api;

export const authApi = Object.assign(api, {
  login: (data: LoginRequest, companyId: string) =>
    api.post<ApiResponse<TokenResponse>>("/auth/login", data, {
      headers: { "X-Company-ID": companyId }
    }),
  refresh: (refreshToken: string) =>
    api.post<ApiResponse<TokenResponse>>("/auth/refresh", { refresh_token: refreshToken }),
  logout: (refreshToken: string) =>
    api.post<ApiResponse<{ message: string }>>("/auth/logout", {
      refresh_token: refreshToken
    }),
  me: () => api.get<ApiResponse<MeResponse>>("/auth/me"),
  switchBranch: (branchId: string, stationKey?: string | null) =>
    api.post<ApiResponse<TokenResponse>>("/auth/switch-branch", {
      branch_id: branchId,
      station_key: stationKey || null
    }),
  myBranches: () => api.get<ApiResponse<UserBranch[]>>("/system/me/branches")
});

export const systemApi = {
  permissions: () => api.get<ApiResponse<Permission[]>>("/system/permissions"),
  users: (page = 1, limit = 20) =>
    api.get<ApiResponse<User[]>>("/system/users", { params: { page, limit } }),
  branches: () => api.get<ApiResponse<Branch[]>>("/system/branches")
};

export const membershipApi = {
  signup: (data: {
    company_name: string;
    business_slug?: string | null;
    owner_display_name: string;
    owner_email: string;
    username: string;
    password: string;
    phone?: string | null;
    terms_accepted: boolean;
    privacy_accepted: boolean;
  }) => api.post<ApiResponse<SaasSignupResponse>>("/membership/signup", data),
  business: (businessSlug: string) =>
    api.get<ApiResponse<SaasBusiness>>(`/membership/businesses/${encodeURIComponent(businessSlug)}`),
  requestVerification: (email: string) =>
    api.post<ApiResponse<SaasActionResponse>>("/membership/verification/request", { email }),
  verifyEmail: (token: string) =>
    api.post<ApiResponse<SaasActionResponse>>("/membership/verification/confirm", { token }),
  requestPasswordReset: (email: string) =>
    api.post<ApiResponse<SaasActionResponse>>("/membership/password-reset/request", { email }),
  resetPassword: (token: string, newPassword: string) =>
    api.post<ApiResponse<SaasActionResponse>>("/membership/password-reset/confirm", {
      token,
      new_password: newPassword
    }),
  me: () => api.get<ApiResponse<SaasMembership>>("/membership/me"),
  billing: () => api.get<ApiResponse<SaasBillingSummary>>("/membership/billing")
};

export const privacySupportApi = {
  privacyRequests: () => api.get<ApiResponse<PrivacyRequest[]>>("/privacy-support/privacy-requests"),
  createPrivacyRequest: (payload: { request_type: PrivacyRequest["request_type"]; description: string | null }) =>
    api.post<ApiResponse<PrivacyRequest>>("/privacy-support/privacy-requests", payload),
  tickets: () => api.get<ApiResponse<SupportTicket[]>>("/privacy-support/tickets"),
  createTicket: (payload: { category: SupportTicket["category"]; priority: SupportTicket["priority"]; subject: string; initial_message: string }) =>
    api.post<ApiResponse<SupportTicket>>("/privacy-support/tickets", payload),
  addMessage: (ticketId: string, body: string) =>
    api.post<ApiResponse<SupportMessage>>(`/privacy-support/tickets/${ticketId}/messages`, { body }),
  decideAccess: (grantId: string, decision: "approved" | "denied", reason: string) =>
    api.post<ApiResponse<SupportAccessGrant>>(`/privacy-support/access/${grantId}/decision`, { decision, reason }),
  revokeAccess: (grantId: string, reason: string) =>
    api.post<ApiResponse<SupportAccessGrant>>(`/privacy-support/access/${grantId}/revoke`, { reason }),
};
