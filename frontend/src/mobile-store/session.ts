import { create } from "zustand";
import { SecureStorage } from "@aparajita/capacitor-secure-storage";
import type { TokenResponse } from "@/types/auth";
import type { User } from "@/types/user";

const KEY = "foodchainservice.store.session.v1";
const DEVICE_KEY = "foodchainservice.store.device.v1";
type StoreClaims = { sub: string; company_id: string; brand_id: string; branch_id: string; station_key: string;
  client_surface: string; store_device_id: string; business_type: string; target_database: string;
  permissions: string[]; exp: number };
type Session = { tokens: TokenResponse; companyId: string; deviceId: string; companyName?: string; branchName?: string };
type State = {
  accessToken: string | null; refreshToken: string | null; user: User | null;
  companyId: string | null; brandId: string | null; branchId: string | null; stationKey: string | null;
  businessSlug: string | null; businessType: string | null; targetDatabase: string | null;
  deviceId: string | null; scopeTypes: string[]; permissions: string[];
  companyName: string | null; branchName: string | null;
  hasPermission: (code: string) => boolean; isAuthenticated: () => boolean;
};
const empty = { accessToken: null, refreshToken: null, user: null, companyId: null,
  brandId: null, branchId: null, stationKey: null, businessSlug: null, businessType: null,
  targetDatabase: null, deviceId: null, scopeTypes: [], permissions: [], companyName: null, branchName: null };
export const useAuthStore = create<State>((_set, get) => ({ ...empty,
  hasPermission: (code) => get().permissions.includes(code),
  isAuthenticated: () => Boolean(get().accessToken && get().user),
}));

export function sessionClaims(session: Session): StoreClaims {
  const claims = JSON.parse(atob(session.tokens.access_token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))) as StoreClaims;
  if (claims.client_surface !== "takeaway_store" || claims.business_type !== "takeaway"
      || claims.target_database !== "takeaway" || !claims.branch_id || !claims.brand_id || !claims.station_key
      || claims.company_id !== session.companyId || claims.store_device_id !== session.deviceId
      || session.tokens.user.company_id !== session.companyId
      || !claims.sub || claims.sub !== session.tokens.user.id
      || claims.permissions.includes("*") || !claims.permissions.includes("takeaway.store.access")) {
    throw new Error("บัญชีนี้ไม่ใช่สิทธิ์หน้าร้าน Takeaway กรุณาเข้าสู่ระบบใหม่");
  }
  return claims;
}
export async function saveSession(session: Session): Promise<void> {
  const claims = sessionClaims(session);
  await SecureStorage.setItem(KEY, JSON.stringify(session));
  useAuthStore.setState({ accessToken: session.tokens.access_token, refreshToken: session.tokens.refresh_token,
    user: session.tokens.user, companyId: session.companyId, brandId: claims.brand_id,
    branchId: claims.branch_id, stationKey: claims.station_key, businessSlug: session.tokens.business_slug,
    businessType: "takeaway", targetDatabase: "takeaway", deviceId: session.deviceId,
    scopeTypes: ["branch"], permissions: claims.permissions,
    companyName: session.companyName ?? null, branchName: session.branchName ?? null });
}
export async function clearSession(): Promise<void> {
  useAuthStore.setState(empty);
  await SecureStorage.removeItem(KEY);
}
export async function restoreSession(): Promise<void> {
  // uat.2 credentials must never be migrated into a Store session.
  localStorage.removeItem("erp-auth");
  const stored = await SecureStorage.getItem(KEY);
  if (typeof stored !== "string") return;
  try { await saveSession(JSON.parse(stored) as Session); }
  catch { await clearSession(); }
}
export async function installationId(): Promise<string> {
  const stored = await SecureStorage.getItem(DEVICE_KEY);
  if (typeof stored === "string" && /^[0-9a-f-]{36}$/.test(stored)) return stored;
  const id = crypto.randomUUID();
  await SecureStorage.setItem(DEVICE_KEY, id);
  return id;
}
