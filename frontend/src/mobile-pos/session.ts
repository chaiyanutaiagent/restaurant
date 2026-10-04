import { create } from "zustand";
import { SecureStorage } from "@aparajita/capacitor-secure-storage";
import type { TokenResponse } from "@/types/auth";
import type { User } from "@/types/user";

export type PosProduct = "takeaway" | "restaurant" | "retail_pos";
const KEY = "foodchainservice.pos.uat.session.v1", DEVICE = "foodchainservice.pos.uat.device.v1";
const OWNER = "foodchainservice.pos.uat.data-owner.v1";
const surfaces: Record<PosProduct, string> = { takeaway: "takeaway_store", restaurant: "restaurant_pos", retail_pos: "retail_pos" };
type Session = { tokens: TokenResponse; companyId: string; deviceId: string; expectedProduct?: string };
type Claims = { sub: string; company_id: string; brand_id: string; branch_id: string; store_device_id: string;
  client_surface: string; business_type: PosProduct; target_database: string; station_key: string; permissions: string[]; exp: number };
const empty = { accessToken: null as string | null, refreshToken: null as string | null, user: null as User | null,
  companyId: null as string | null, branchId: null as string | null, brandId: null as string | null,
  businessType: null as PosProduct | null, targetDatabase: null as string | null, businessSlug: null as string | null,
  deviceId: null as string | null, stationKey: null as string | null, permissions: [] as string[], scopeTypes: [] as string[],
  qaMode: false, qaPersona: null };
export const useAuthStore = create<typeof empty & { hasPermission: (code: string) => boolean; isAuthenticated: () => boolean }>((_set, get) => ({
  ...empty, hasPermission: (code) => get().permissions.includes(code), isAuthenticated: () => Boolean(get().accessToken && get().user),
}));
export function sessionClaims(session: Session): Claims {
  const raw = session.tokens.access_token.split(".")[1];
  const claim = JSON.parse(atob(raw.replace(/-/g, "+").replace(/_/g, "/"))) as Claims;
  if (!Object.prototype.hasOwnProperty.call(surfaces, claim.business_type) || surfaces[claim.business_type] !== claim.client_surface
      || claim.target_database !== claim.business_type || !claim.branch_id || !claim.brand_id || !claim.station_key
      || claim.company_id !== session.companyId || session.tokens.user.company_id !== session.companyId
      || claim.sub !== session.tokens.user.id || claim.store_device_id !== session.deviceId
      || !Array.isArray(claim.permissions) || claim.permissions.includes("*") || !Number.isFinite(claim.exp)
      || (session.expectedProduct && session.expectedProduct !== claim.business_type)
      || (claim.business_type === "takeaway" && !claim.permissions.includes("takeaway.store.access"))) {
    throw new Error("สิทธิ์บริษัท สาขา หรือผลิตภัณฑ์ไม่ตรงกับระบบที่เลือก");
  }
  return claim;
}
export async function saveSession(session: Session): Promise<void> {
  const claim = sessionClaims(session);
  const owner = JSON.stringify([claim.company_id, claim.branch_id, claim.business_type, claim.sub]);
  const previous = await SecureStorage.getItem(OWNER);
  if (previous !== owner) {
    const { assertNoPendingData, cleanupStoreData } = await import("./storeDb");
    await assertNoPendingData(); await cleanupStoreData();
  }
  await SecureStorage.setItem(OWNER, owner);
  await SecureStorage.setItem(KEY, JSON.stringify(session));
  useAuthStore.setState({ accessToken: session.tokens.access_token, refreshToken: session.tokens.refresh_token,
    user: session.tokens.user, companyId: claim.company_id, branchId: claim.branch_id, brandId: claim.brand_id,
    businessType: claim.business_type, targetDatabase: claim.target_database, businessSlug: session.tokens.business_slug,
    deviceId: claim.store_device_id, stationKey: claim.station_key, permissions: claim.permissions, scopeTypes: ["branch"] });
}
export async function clearSession(): Promise<void> {
  await SecureStorage.removeItem(KEY); useAuthStore.setState(empty);
}
export async function restoreSession(): Promise<void> {
  const raw = await SecureStorage.getItem(KEY);
  if (typeof raw !== "string") return;
  try { await saveSession(JSON.parse(raw)); } catch { await clearSession(); }
}
export async function installationId(): Promise<string> {
  const raw = await SecureStorage.getItem(DEVICE);
  if (typeof raw === "string" && /^[0-9a-f-]{36}$/.test(raw)) return raw;
  const id = crypto.randomUUID(); await SecureStorage.setItem(DEVICE, id); return id;
}
