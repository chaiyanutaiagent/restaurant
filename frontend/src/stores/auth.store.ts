import type { StateCreator } from "zustand";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { immer } from "zustand/middleware/immer";
import type { TokenResponse } from "@/types/auth";
import type { User } from "@/types/user";

type JwtPayload = {
  branch_id?: string | null;
  permissions?: string[];
};

type AuthState = {
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  companyId: string | null;
  branchId: string | null;
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
  branchId: null,
  permissions: [],
  setSession: (tokens, companyId) => {
    const payload = parseJwtPayload(tokens.access_token);
    set((state) => {
      state.accessToken = tokens.access_token;
      state.refreshToken = tokens.refresh_token;
      state.user = tokens.user;
      state.companyId = companyId;
      state.branchId = payload?.branch_id ?? null;
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
      state.branchId = null;
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
