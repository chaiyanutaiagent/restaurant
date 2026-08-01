import axios, {
  AxiosError,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios";
import { useDeviceStore } from "@/stores/device.store";
import type { ApiResponse } from "@/types/api";
import type { DevicePairResponse } from "@/types/device";

type RetryableDeviceConfig = InternalAxiosRequestConfig & {
  _deviceRetry?: boolean;
};

const configuredApiOrigin = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/$/, "");
const apiBaseUrl = configuredApiOrigin
  ? (configuredApiOrigin.endsWith("/api/v1") ? configuredApiOrigin : `${configuredApiOrigin}/api/v1`)
  : "/api/v1";

const deviceRenewApi = axios.create({ baseURL: apiBaseUrl, timeout: 10_000 });
export const deviceApi = axios.create({ baseURL: apiBaseUrl });

let renewalPromise: Promise<string> | null = null;

function pairingRedirect(): void {
  const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  window.location.href = `/device/pair?next=${encodeURIComponent(current)}`;
}

export async function renewDeviceSession(): Promise<string> {
  if (renewalPromise) return renewalPromise;
  const refreshToken = useDeviceStore.getState().refreshToken;
  if (!refreshToken) throw new Error("Device refresh credential is unavailable");

  renewalPromise = (async () => {
    try {
      const response = await deviceRenewApi.post<ApiResponse<DevicePairResponse>>(
        "/device-auth/renew",
        { refresh_token: refreshToken },
      );
      await useDeviceStore.getState().setSession(response.data.data);
      return response.data.data.access_token;
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 401) {
        await useDeviceStore.getState().clearSession();
      }
      throw error;
    } finally {
      renewalPromise = null;
    }
  })();
  return renewalPromise;
}

deviceApi.interceptors.request.use((config) => {
  const token = useDeviceStore.getState().accessToken;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

deviceApi.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: AxiosError) => {
    const original = error.config as RetryableDeviceConfig | undefined;
    const isPairRequest = original?.url?.includes("/device-auth/pair");
    const isRenewRequest = original?.url?.includes("/device-auth/renew");
    if (
      error.response?.status === 401
      && original
      && !original._deviceRetry
      && !isPairRequest
      && !isRenewRequest
      && useDeviceStore.getState().refreshToken
    ) {
      original._deviceRetry = true;
      try {
        const token = await renewDeviceSession();
        original.headers.Authorization = `Bearer ${token}`;
        return deviceApi(original);
      } catch (renewError) {
        if (axios.isAxiosError(renewError) && !renewError.response) {
          return Promise.reject(renewError);
        }
        if (axios.isAxiosError(renewError) && renewError.response?.status === 401) {
          pairingRedirect();
        }
        return Promise.reject(renewError);
      }
    }
    if (error.response?.status === 401 && !isPairRequest && !isRenewRequest) {
      await useDeviceStore.getState().clearSession();
      pairingRedirect();
    }
    return Promise.reject(error);
  },
);

export function deviceErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail ?? error.response?.data?.error?.message;
    if (typeof detail === "string") return detail;
    if (!error.response) return "เชื่อมต่อระบบไม่ได้ กรุณาตรวจสอบเครือข่าย";
  }
  return error instanceof Error ? error.message : "ดำเนินการไม่สำเร็จ";
}
