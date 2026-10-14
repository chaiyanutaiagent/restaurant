import { create } from "zustand";
import { SecureStorage } from "@aparajita/capacitor-secure-storage";
import type { TokenResponse } from "@/types/auth";
import type { User } from "@/types/user";
import { nativeProduct } from "./config";

const key = `foodchainservice.${nativeProduct}.uat.session.v1`;
type State = {
  accessToken: string | null; refreshToken: string | null; user: User | null;
  companyId: string | null; businessSlug: string | null; brandId: string | null;
  branchId: string | null; businessType: string | null; targetDatabase: string | null;
  stationKey: string | null; scopeTypes: string[]; permissions: string[]; qaMode: boolean; qaPersona: string | null;
  setSession: (tokens: TokenResponse, companyId: string) => void;
  setBranchId: (id: string) => void; clearSession: () => void;
  hasPermission: (permission: string) => boolean; isAuthenticated: () => boolean;
};
const empty = { accessToken: null, refreshToken: null, user: null, companyId: null,
  businessSlug: null, brandId: null, branchId: null, businessType: null, targetDatabase: null,
  stationKey: null, scopeTypes: [], permissions: [], qaMode: false, qaPersona: null };
let pending: Promise<void> = Promise.resolve();
let storageError: unknown;
function write(action: () => Promise<unknown>) {
  pending = pending.then(action).then(() => undefined).catch((error: unknown) => {
    storageError = error;
    window.dispatchEvent(new Event("native-pos-storage-error"));
  });
}
export async function flushNativeSession() {
  await pending;
  if (storageError) throw new Error("บันทึกข้อมูลเข้าสู่ระบบอย่างปลอดภัยไม่ได้ กรุณาปิดและเปิดแอปใหม่");
}
export const useAuthStore = create<State>((set, get) => ({ ...empty,
  setSession(tokens, companyId) {
    const encoded = tokens.access_token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const claims = JSON.parse(atob(encoded));
    if (claims.company_id !== companyId || tokens.user.company_id !== companyId
        || tokens.user.is_superuser || claims.qa_mode || claims.permissions?.includes("*")) {
      throw new Error("กรุณาใช้บัญชีพนักงานจริง ไม่ใช่บัญชี Super Admin หรือบัญชีข้ามระบบ");
    }
    write(() => SecureStorage.setItem(key, JSON.stringify({ tokens, companyId })));
    set({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token, user: tokens.user,
      companyId, businessSlug: tokens.business_slug, brandId: claims.brand_id ?? null,
      branchId: claims.branch_id ?? null, businessType: claims.business_type ?? null,
      targetDatabase: claims.target_database ?? null, stationKey: claims.station_key ?? null,
      scopeTypes: claims.scope_types ?? [], permissions: claims.permissions ?? [] });
  },
  setBranchId() { throw new Error("ต้องเปลี่ยนสาขาด้วยสิทธิ์ที่ Server ลงนามเท่านั้น"); },
  clearSession() { set(empty); write(() => SecureStorage.removeItem(key)); },
  hasPermission: (permission) => get().permissions.includes(permission),
  isAuthenticated: () => Boolean(get().accessToken && get().user),
}));
export async function restoreNativeSession() {
  const stored = await SecureStorage.getItem(key);
  if (typeof stored !== "string") return;
  try {
    const { tokens, companyId } = JSON.parse(stored);
    useAuthStore.getState().setSession(tokens, companyId);
  } catch { useAuthStore.getState().clearSession(); }
  await flushNativeSession();
}
