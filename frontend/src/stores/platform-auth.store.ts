import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { PlatformOperator, PlatformTokenResponse } from "@/types/platform";

type PlatformAuthState = {
  accessToken: string | null;
  operator: PlatformOperator | null;
  setSession: (session: PlatformTokenResponse) => void;
  clearSession: () => void;
  isAuthenticated: () => boolean;
};

export const usePlatformAuthStore = create<PlatformAuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      operator: null,
      setSession: (session) => set({ accessToken: session.access_token, operator: session.operator }),
      clearSession: () => set({ accessToken: null, operator: null }),
      isAuthenticated: () => Boolean(get().accessToken && get().operator?.is_superuser)
    }),
    {
      name: "restaurant-platform-auth",
      storage: createJSONStorage(() => localStorage)
    }
  )
);
