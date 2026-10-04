import axios from "axios";
import type { ApiResponse } from "@/types/api";
import type { TokenResponse } from "@/types/auth";
import type { UserBranch } from "@/types/user";
import { clearSession, saveSession, sessionClaims, useAuthStore, type PosProduct } from "./session";
import { beginNativeWrite, endNativeWrite } from "../lib/nativePosWorkGuard";

export const productOrigins: Record<PosProduct, string> = {
  takeaway: "https://uat-takeaway.foodchainservice.com", restaurant: "https://uat-restaurant.foodchainservice.com",
  retail_pos: "https://uat-retail.foodchainservice.com",
};
export const onboardingApi = axios.create({ baseURL: "https://uat-pos.foodchainservice.com/api/v1", timeout: 15000 });
const api = axios.create({ timeout: 20000 });
function contextKey(): string {
  const s = useAuthStore.getState(); return JSON.stringify([s.companyId, s.branchId, s.businessType, s.user?.id, s.deviceId]);
}
declare module "axios" { interface InternalAxiosRequestConfig { posContext?: string; posRetry?: boolean; posWriteId?: string; } }
let refresh: Promise<void> | null = null;
api.interceptors.request.use((config) => {
  const state = useAuthStore.getState();
  if (!state.accessToken || !state.businessType) throw new Error("กรุณาเข้าสู่ระบบ");
  if (config.posContext && config.posContext !== contextKey()) throw new Error("บริบทเปลี่ยนแล้ว");
  if (!config.url?.startsWith("/") || config.url.startsWith("//") || config.url.includes("://")) throw new Error("API route ไม่ถูกต้อง");
  config.posContext = contextKey(); config.baseURL = productOrigins[state.businessType] + "/api/v1";
  if (config.url === "/crm/customers/search") config.url = "/mobile-pos/customers/search";
  if (config.url === "/products") config.params = { ...config.params, catalog_scope: state.businessType === "restaurant" ? "restaurant_menu" : "retail_sale" };
  config.headers.Authorization = `Bearer ${state.accessToken}`;
  config.headers["X-Company-ID"] = state.companyId; config.headers["X-Branch-ID"] = state.branchId;
  config.headers["X-Store-Device-ID"] = state.deviceId;
  if (!["get", "head", "options"].includes(config.method ?? "get")) {
    config.posWriteId = crypto.randomUUID(); beginNativeWrite(config.posWriteId);
  }
  return config;
});
api.interceptors.response.use((response) => {
  endNativeWrite(response.config.posWriteId);
  if (response.config.posContext !== contextKey()) throw new Error("บริบทเปลี่ยนแล้ว");
  return response;
}, async (error) => {
  const original = error.config;
  if (error.response?.status !== 401 || !original || original.posRetry) { endNativeWrite(original?.posWriteId); throw error; }
  if (original.posContext !== contextKey()) { endNativeWrite(original.posWriteId); throw new Error("บริบทเปลี่ยนแล้ว"); }
  original.posRetry = true;
  if (!refresh) {
    const state = useAuthStore.getState();
    refresh = (async () => {
      try {
        const response = await onboardingApi.post<ApiResponse<TokenResponse>>("/auth/refresh", { refresh_token: state.refreshToken });
        if (useAuthStore.getState().refreshToken !== state.refreshToken) throw new Error("Session changed");
        const candidate = { tokens: response.data.data, companyId: state.companyId!, deviceId: state.deviceId!, expectedProduct: state.businessType! };
        if (sessionClaims(candidate).branch_id !== state.branchId || candidate.tokens.user.id !== state.user?.id) throw new Error("Refresh context mismatch");
        await saveSession(candidate);
      } catch (failure) {
        if (axios.isAxiosError(failure) && failure.response && useAuthStore.getState().refreshToken === state.refreshToken) await clearSession();
        throw failure;
      }
    })().finally(() => { refresh = null; });
  }
  try { await refresh; } finally { endNativeWrite(original.posWriteId); }
  return api(original);
});
export default api;
export const authApi = Object.assign(api, {
  myBranches: () => api.get<ApiResponse<UserBranch[]>>("/mobile-pos/context"),
  me: () => api.get("/auth/me"),
  logout: (token: string) => onboardingApi.post("/auth/logout", { refresh_token: token }),
  switchBranch: async (): Promise<never> => { throw new Error("กรุณาจัดการรายการค้างและออกจากระบบก่อนเลือกสาขาใหม่"); },
});
