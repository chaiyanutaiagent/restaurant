import axios, {
  AxiosError,
  type AxiosResponse,
  type InternalAxiosRequestConfig
} from "axios";
import { useAuthStore } from "@/stores/auth.store";
import type { ApiResponse } from "@/types/api";
import type { LoginRequest, MeResponse, TokenResponse } from "@/types/auth";
import type { Branch, Permission, User, UserBranch } from "@/types/user";

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

  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  if (companyId) {
    config.headers["X-Company-ID"] = companyId;
  }
  if (branchId) {
    config.headers["X-Branch-ID"] = branchId;
  }

  return config;
});

let isRefreshing = false;
let failedQueue: QueueItem[] = [];

function loginRedirectForCurrentPage(): string {
  const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (window.location.pathname === "/login") {
    return current;
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
