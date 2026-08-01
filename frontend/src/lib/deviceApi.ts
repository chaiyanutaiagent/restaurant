import axios, { AxiosError, type AxiosResponse } from "axios";
import { useDeviceStore } from "@/stores/device.store";

const configuredApiOrigin = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/$/, "");
const apiBaseUrl = configuredApiOrigin
  ? (configuredApiOrigin.endsWith("/api/v1") ? configuredApiOrigin : `${configuredApiOrigin}/api/v1`)
  : "/api/v1";

export const deviceApi = axios.create({ baseURL: apiBaseUrl });

deviceApi.interceptors.request.use((config) => {
  const token = useDeviceStore.getState().accessToken;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

deviceApi.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError) => {
    const isPairRequest = error.config?.url?.includes("/device-auth/pair");
    if (error.response?.status === 401 && !isPairRequest) {
      useDeviceStore.getState().clearSession();
      const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
      window.location.href = `/device/pair?next=${encodeURIComponent(current)}`;
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
