import type { StateCreator } from "zustand";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { immer } from "zustand/middleware/immer";
import type { TokenResponse } from "@/types/auth";
import type { User } from "@/types/user";

type JwtPayload = {
  brand_id?: string | null;
  branch_id?: string | null;
  business_type?: string | null;
  target_database?: string | null;
  scope_types?: string[];
  station_key?: string | null;
  permissions?: string[];
};

type AuthState = {
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  companyId: string | null;
  businessSlug: string | null;
  brandId: string | null;
  branchId: string | null;
  businessType: string | null;
  targetDatabase: string | null;
  scopeTypes: string[];
  stationKey: string | null;
  permissions: string[];
  setSession: (tokens: TokenResponse, companyId: string) => void;
  setBranchId: (branchId: string) => void;
  clearSession: () => void;
  hasPermission: (code: string) => boolean;
  isAuthenticated: () => boolean;
};

function parseJwtPayload(token: string): JwtPayload | null {
  try {
    const encodedPayload = token.split(".")[1];
    if (!encodedPayload) {
      return null;
    }
    const normalized = encodedPayload.replace(/-/g, "+").replace(/_/g, "/");
    const payload = window.atob(normalized);
    return JSON.parse(payload) as JwtPayload;
  } catch {
    return null;
  }
}

const authStore: StateCreator<AuthState, [["zustand/persist", unknown], ["zustand/immer", never]]> = (
  set,
  get
) => ({
  accessToken: null,
  refreshToken: null,
  user: null,
  companyId: null,
  businessSlug: null,
  brandId: null,
  branchId: null,
  businessType: null,
  targetDatabase: null,
  scopeTypes: [],
  stationKey: null,
  permissions: [],
  setSession: (tokens, companyId) => {
    const payload = parseJwtPayload(tokens.access_token);
    set((state) => {
      state.accessToken = tokens.access_token;
      state.refreshToken = tokens.refresh_token;
      state.user = tokens.user;
      state.companyId = companyId;
      state.businessSlug = tokens.business_slug ?? null;
      state.brandId = payload?.brand_id ?? null;
      state.branchId = payload?.branch_id ?? null;
      state.businessType = payload?.business_type ?? null;
      state.targetDatabase = payload?.target_database ?? null;
      state.scopeTypes = payload?.scope_types ?? [];
      state.stationKey = payload?.station_key ?? null;
      state.permissions = payload?.permissions ?? [];
    });
  },
  setBranchId: (branchId) => {
    set((state) => {
      state.branchId = branchId;
    });
  },
  clearSession: () => {
    set((state) => {
      state.accessToken = null;
      state.refreshToken = null;
      state.user = null;
      state.companyId = null;
      state.businessSlug = null;
      state.brandId = null;
      state.branchId = null;
      state.businessType = null;
      state.targetDatabase = null;
      state.scopeTypes = [];
      state.stationKey = null;
      state.permissions = [];
    });
    window.localStorage.removeItem("erp-auth");
  },
  hasPermission: (code) => {
    const permissions = get().permissions;
    return permissions.includes("*") || permissions.includes(code);
  },
  isAuthenticated: () => Boolean(get().accessToken && get().user)
});

export const useAuthStore = create<AuthState>()(
  persist(immer(authStore), {
    name: "erp-auth",
    storage: createJSONStorage(() => localStorage)
  })
);
