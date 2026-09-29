import axios from "axios";
import type { ApiResponse } from "@/types/api";
import type { TokenResponse } from "@/types/auth";
import { clearSession, saveSession, useAuthStore } from "./session";

declare module "axios" {
  interface InternalAxiosRequestConfig { storeContext?: string; }
}
function currentContext(): string {
  const state = useAuthStore.getState();
  return JSON.stringify([state.companyId, state.branchId, state.deviceId, state.user?.id]);
}
const baseURL = `${import.meta.env.VITE_API_BASE_URL}/api/v1`;
export const onboardingApi = axios.create({ baseURL, timeout: 15000 });
const api = axios.create({ baseURL, timeout: 20000 });
api.interceptors.request.use((config) => {
  const state = useAuthStore.getState();
  if (!state.accessToken) throw new Error("กรุณาเข้าสู่ระบบ");
  if (config.storeContext && config.storeContext !== currentContext()) throw new Error("Session changed");
  config.storeContext = currentContext();
  config.headers.Authorization = `Bearer ${state.accessToken}`;
  config.headers["X-Company-ID"] = state.companyId;
  config.headers["X-Branch-ID"] = state.branchId;
  config.headers["X-Store-Device-ID"] = state.deviceId;
  return config;
});
let refresh: Promise<void> | null = null;
api.interceptors.response.use((response) => {
  if (response.config.storeContext !== currentContext()) {
    throw new Error("บริบทสาขาเปลี่ยน กรุณาโหลดใหม่");
  }
  return response;
}, async (error) => {
  const original = error.config;
  if (error.response?.status !== 401 || !original || original._retry) throw error;
  if (original.storeContext !== currentContext()) throw new Error("Session changed");
  original._retry = true;
  if (!refresh) {
    const state = useAuthStore.getState();
    refresh = (async () => {
      try {
        const result = await onboardingApi.post<ApiResponse<TokenResponse>>("/auth/refresh", { refresh_token: state.refreshToken });
        if (useAuthStore.getState().refreshToken !== state.refreshToken) throw new Error("Session changed");
        await saveSession({ tokens: result.data.data, companyId: state.companyId!, deviceId: state.deviceId! });
      } catch (failure) {
        if (axios.isAxiosError(failure) && failure.response
            && useAuthStore.getState().refreshToken === state.refreshToken) await clearSession();
        throw failure;
      }
    })().finally(() => { refresh = null; });
  }
  await refresh;
  return api(original);
});
export default api;
